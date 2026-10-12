"""Pruebas unitarias e integrales para HU-37: Cierre y arqueo de caja."""

from decimal import Decimal
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from cotizaciones.models import Moneda
from .models import (
    AperturaCaja, AsignacionCaja, Caja, DenominacionBillete,
    DetalleInventarioInicial, Remesa, DetalleRemesa, Sucursal,
    CierreCaja, DetalleCierreCaja, ConteoBilleteCierre,
)
from .services import (
    cerrar_caja, CierreCajaError, registrar_remesa, RemesaError,
    apertura_para_movimiento, AperturaCajaError,
)


class CierreCajaTestCase(TestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.cajero = User.objects.create_user(
            username="cajero_user", email="cajero@example.com"
        )
        self.tesorero = User.objects.create_user(
            username="tesorero_user", email="tesorero@example.com"
        )
        self.cajero_id = uuid4()

        self.sucursal = Sucursal.objects.create(codigo="SUC-01", nombre="Casa Central")
        self.caja = Caja.objects.create(sucursal=self.sucursal, codigo="CAJA-01", nombre="Caja 1")

        self.ahora = timezone.now()
        self.asignacion = AsignacionCaja.objects.create(
            caja=self.caja,
            cajero_keycloak_id=self.cajero_id,
            cajero_username="cajero_user",
            turno="Mañana",
            fecha_inicio=self.ahora - timedelta(hours=2),
            fecha_fin=self.ahora + timedelta(hours=6),
            asignado_por=self.tesorero,
        )

        self.usd, _ = Moneda.objects.get_or_create(codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"})
        self.pyg, _ = Moneda.objects.get_or_create(codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"})

        self.billete_usd_100 = DenominacionBillete.objects.create(moneda=self.usd, valor=Decimal("100.00"))
        self.billete_usd_50 = DenominacionBillete.objects.create(moneda=self.usd, valor=Decimal("50.00"))
        self.billete_usd_20 = DenominacionBillete.objects.create(moneda=self.usd, valor=Decimal("20.00"))

        # Apertura con USD 200 inicial (2 billetes de 100)
        self.apertura = AperturaCaja.objects.create(
            caja=self.caja,
            asignacion=self.asignacion,
            cajero_keycloak_id=self.cajero_id,
            fecha_apertura=self.ahora - timedelta(hours=1),
            estado=AperturaCaja.Estado.ABIERTA,
        )
        DetalleInventarioInicial.objects.create(
            apertura=self.apertura,
            denominacion=self.billete_usd_100,
            moneda_id="USD",
            valor_denominacion=Decimal("100.00"),
            cantidad=2,
        )

        self.factory = RequestFactory()

    def _request_cajero(self, path="/", method="get", data=None):
        req = getattr(self.factory, method)(path, data=data or {})
        req.user = self.cajero
        req.user_claims = {
            "sub": str(self.cajero_id),
            "preferred_username": "cajero_user",
            "realm_access": {"roles": ["cajero"]},
        }
        return req

    def test_criterio_1_solo_permite_cerrar_apertura_activa(self):
        """Criterio 1: El sistema debe permitir cerrar únicamente una caja que tenga una apertura activa."""
        # Marcar la apertura como cerrada
        self.apertura.estado = AperturaCaja.Estado.CERRADA
        self.apertura.fecha_cierre = timezone.now()
        self.apertura.save()

        conteo = [{"denominacion_id": self.billete_usd_100.pk, "cantidad": 2}]
        with self.assertRaisesMessage(CierreCajaError, "Solo se puede cerrar una caja con apertura activa"):
            cerrar_caja(
                apertura_id=self.apertura.pk,
                conteo_billetes=conteo,
                usuario=self.cajero,
            )

    def test_criterio_2_3_4_5_arqueo_cuadrado(self):
        """Calcula saldo físico, saldo teórico y diferencia de un arqueo cuadrado (diferencia 0)."""
        # Saldo teórico inicial: USD 200.00 (2 billetes de 100)
        conteo = [
            {"denominacion_id": self.billete_usd_100.pk, "cantidad": 1},  # 100
            {"denominacion_id": self.billete_usd_50.pk, "cantidad": 2},   # 100
        ]
        # Total físico = 100 + 100 = 200.00
        cierre = cerrar_caja(
            apertura_id=self.apertura.pk,
            conteo_billetes=conteo,
            observaciones="Arqueo exacto",
            usuario=self.cajero,
        )

        self.assertIsNotNone(cierre)
        self.assertEqual(cierre.apertura.estado, AperturaCaja.Estado.CERRADA)
        self.assertFalse(cierre.hay_diferencias)

        det = cierre.detalles.get(moneda_id="USD")
        self.assertEqual(det.saldo_teorico, Decimal("200.00"))
        self.assertEqual(det.saldo_fisico, Decimal("200.00"))
        self.assertEqual(det.diferencia, Decimal("0.00"))
        self.assertEqual(det.estado_arqueo, "CUADRADO")

        # Verificar desglose de billetes
        conteos = list(cierre.conteos_billetes.order_by("denominacion__valor"))
        self.assertEqual(len(conteos), 2)
        self.assertEqual(conteos[0].denominacion, self.billete_usd_50)
        self.assertEqual(conteos[0].cantidad, 2)
        self.assertEqual(conteos[0].subtotal, Decimal("100.00"))

    def test_criterio_6_identificar_faltante(self):
        """Criterio 6: Identificar y registrar faltante cuando físico < teórico."""
        # Teórico = 200.00, Físico = 100.00 (1 billete de 100) -> Faltante de 100.00
        conteo = [{"denominacion_id": self.billete_usd_100.pk, "cantidad": 1}]
        cierre = cerrar_caja(
            apertura_id=self.apertura.pk,
            conteo_billetes=conteo,
            observaciones="Faltante por billete dañado",
            usuario=self.cajero,
        )

        self.assertTrue(cierre.hay_diferencias)
        det = cierre.detalles.get(moneda_id="USD")
        self.assertEqual(det.saldo_teorico, Decimal("200.00"))
        self.assertEqual(det.saldo_fisico, Decimal("100.00"))
        self.assertEqual(det.diferencia, Decimal("-100.00"))
        self.assertEqual(det.estado_arqueo, "FALTANTE")

    def test_criterio_6_identificar_sobrante(self):
        """Criterio 6: Identificar y registrar sobrante cuando físico > teórico."""
        # Teórico = 200.00, Físico = 250.00 (2 de 100 + 1 de 50) -> Sobrante de 50.00
        conteo = [
            {"denominacion_id": self.billete_usd_100.pk, "cantidad": 2},
            {"denominacion_id": self.billete_usd_50.pk, "cantidad": 1},
        ]
        cierre = cerrar_caja(
            apertura_id=self.apertura.pk,
            conteo_billetes=conteo,
            observaciones="Sobrante registrado",
            usuario=self.cajero,
        )

        self.assertTrue(cierre.hay_diferencias)
        det = cierre.detalles.get(moneda_id="USD")
        self.assertEqual(det.saldo_teorico, Decimal("200.00"))
        self.assertEqual(det.saldo_fisico, Decimal("250.00"))
        self.assertEqual(det.diferencia, Decimal("50.00"))
        self.assertEqual(det.estado_arqueo, "SOBRANTE")

    def test_criterio_4_saldo_teorico_con_remesas(self):
        """Criterio 4: Calcula el saldo teórico considerando remesas entregadas y devueltas."""
        # Registrar una entrega de USD 100 (1 billete de 100)
        registrar_remesa(
            usuario=self.tesorero,
            caja_id=self.caja.pk,
            tipo=Remesa.Tipo.ENTREGA,
            moneda_id="USD",
            desglose=[{"denominacion_id": self.billete_usd_100.pk, "cantidad": 1}],
        )
        # Saldo teórico ahora: 200 inicial + 100 entrega = 300.00

        # Conteo físico: 3 de 100 = 300.00
        conteo = [{"denominacion_id": self.billete_usd_100.pk, "cantidad": 3}]
        cierre = cerrar_caja(
            apertura_id=self.apertura.pk,
            conteo_billetes=conteo,
            usuario=self.cajero,
        )
        det = cierre.detalles.get(moneda_id="USD")
        self.assertEqual(det.saldo_teorico, Decimal("300.00"))
        self.assertEqual(det.saldo_fisico, Decimal("300.00"))
        self.assertEqual(det.diferencia, Decimal("0.00"))

    def test_criterio_7_conservar_saldo_teorico_fisico_diferencia(self):
        """Criterio 7: El cierre debe conservar el saldo teórico, saldo físico y diferencia."""
        conteo = [{"denominacion_id": self.billete_usd_100.pk, "cantidad": 2}]
        cierre = cerrar_caja(
            apertura_id=self.apertura.pk,
            conteo_billetes=conteo,
            usuario=self.cajero,
        )
        # Recargar desde la BD
        cierre_db = CierreCaja.objects.get(pk=cierre.pk)
        det = cierre_db.detalles.first()
        self.assertIsNotNone(det.saldo_teorico)
        self.assertIsNotNone(det.saldo_fisico)
        self.assertIsNotNone(det.diferencia)

    def test_criterio_8_caja_cerrada_no_acepta_nuevos_movimientos(self):
        """Criterio 8: Una caja cerrada no debe aceptar nuevos movimientos correspondientes a ese turno."""
        conteo = [{"denominacion_id": self.billete_usd_100.pk, "cantidad": 2}]
        cerrar_caja(
            apertura_id=self.apertura.pk,
            conteo_billetes=conteo,
            usuario=self.cajero,
        )

        # Intentar registrar una remesa para la caja cerrada debe fallar
        with self.assertRaises(RemesaError):
            registrar_remesa(
                usuario=self.tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.ENTREGA,
                moneda_id="USD",
                desglose=[{"denominacion_id": self.billete_usd_100.pk, "cantidad": 1}],
            )

        # Intentar adquirir apertura_para_movimiento debe lanzar AperturaCajaError
        with self.assertRaises(AperturaCajaError):
            with apertura_para_movimiento(self.caja.pk):
                pass

    def test_criterio_9_cierre_registra_fecha_hora_y_usuario_responsable(self):
        """Criterio 9: El cierre debe registrar fecha, hora y usuario responsable."""
        conteo = [{"denominacion_id": self.billete_usd_100.pk, "cantidad": 2}]
        cierre = cerrar_caja(
            apertura_id=self.apertura.pk,
            conteo_billetes=conteo,
            usuario=self.cajero,
        )
        self.assertIsNotNone(cierre.fecha_cierre)
        self.assertEqual(cierre.usuario_responsable, self.cajero)

    def test_no_repetir_denominaciones_en_conteo(self):
        """El conteo rechaza denominaciones duplicadas."""
        conteo = [
            {"denominacion_id": self.billete_usd_100.pk, "cantidad": 1},
            {"denominacion_id": self.billete_usd_100.pk, "cantidad": 1},
        ]
        with self.assertRaisesMessage(CierreCajaError, "No repita denominaciones"):
            cerrar_caja(
                apertura_id=self.apertura.pk,
                conteo_billetes=conteo,
                usuario=self.cajero,
            )

    def test_cierre_create_view_flujo_completo(self):
        """Prueba de integración de la vista CierreCajaCreateView con POST válido."""
        client = Client()
        client.force_login(self.cajero)
        session = client.session
        session["oidc_id_token_expiration"] = (timezone.now() + timedelta(hours=1)).timestamp()
        session.save()

        with patch("cajas.mixins.obtener_cajero_autenticado", return_value=self.cajero_id), \
             patch("cajas.services.obtener_cajero_autenticado", return_value=self.cajero_id), \
             patch("cajas.views.obtener_cajero_autenticado", return_value=self.cajero_id), \
             patch("core.keycloak.obtener_roles", return_value=["cajero"]), \
             patch("core.context_processors.obtener_roles", return_value=["cajero"]), \
             patch("core.keycloak.obtener_claims_verificados", return_value={"realm_access": {"roles": ["cajero"]}, "sub": str(self.cajero_id)}):

            url = reverse("cierre-create", kwargs={"id_apertura": self.apertura.pk})
            resp_get = client.get(url)
            self.assertEqual(resp_get.status_code, 200)

            post_data = {
                "observaciones": "Cierre de prueba vía vista",
                "conteo-TOTAL_FORMS": "1",
                "conteo-INITIAL_FORMS": "0",
                "conteo-MIN_NUM_FORMS": "1",
                "conteo-MAX_NUM_FORMS": "100",
                "conteo-0-denominacion": str(self.billete_usd_100.pk),
                "conteo-0-cantidad": "2",
            }
            resp_post = client.post(url, data=post_data)
            self.assertEqual(resp_post.status_code, 302)

            cierre = CierreCaja.objects.get(apertura=self.apertura)
            self.assertRedirects(resp_post, reverse("cierre-detail", kwargs={"id_cierre": cierre.pk}))

            # Verificar detalle
            resp_det = client.get(reverse("cierre-detail", kwargs={"id_cierre": cierre.pk}))
            self.assertEqual(resp_det.status_code, 200)
            self.assertContains(resp_det, "Comprobante oficial")

            # Verificar lista de cierres
            resp_list = client.get(reverse("cierre-list"))
            self.assertEqual(resp_list.status_code, 200)
            self.assertContains(resp_list, f"#{cierre.pk}")
