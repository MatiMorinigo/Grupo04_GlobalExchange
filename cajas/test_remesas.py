"""Pruebas unitarias e integrales para HU-36: Registro de remesas de efectivo."""

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
)
from .services import (
    registrar_remesa, RemesaError, abrir_caja, AperturaCajaError,
)


class RemesaTestCase(TestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.tesorero = User.objects.create_user(
            username="tesorero_user", email="tesorero@example.com"
        )
        self.cajero = User.objects.create_user(
            username="cajero_user", email="cajero@example.com"
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
        self.billete_pyg_100k = DenominacionBillete.objects.create(moneda=self.pyg, valor=Decimal("100000.00"))

        # Crear apertura activa con USD 100 inicial (1 billete de 100)
        self.apertura = AperturaCaja.objects.create(
            caja=self.caja,
            asignacion=self.asignacion,
            cajero_keycloak_id=self.cajero_id,
            estado=AperturaCaja.Estado.ABIERTA,
        )
        DetalleInventarioInicial.objects.create(
            apertura=self.apertura,
            denominacion=self.billete_usd_100,
            moneda=self.usd,
            valor_denominacion=self.billete_usd_100.valor,
            cantidad=1,
        )

    def test_entrega_remesa_actualiza_saldo_e_inventario(self):
        """Una entrega de Tesorería a Caja aumenta el saldo e inventario teórico."""
        desglose = [
            {"denominacion_id": self.billete_usd_50.pk, "cantidad": 2},  # 2 x 50 = 100
            {"denominacion_id": self.billete_usd_20.pk, "cantidad": 5},  # 5 x 20 = 100
        ]

        remesa = registrar_remesa(
            usuario=self.tesorero,
            caja_id=self.caja.pk,
            tipo=Remesa.Tipo.ENTREGA,
            moneda_id=self.usd.pk,
            desglose=desglose,
            observaciones="Abastecimiento de media tarde",
        )

        self.assertEqual(remesa.tipo, Remesa.Tipo.ENTREGA)
        self.assertEqual(remesa.origen, "Tesorería")
        self.assertIn("Caja CAJA-01", remesa.destino)
        self.assertEqual(remesa.monto_total, Decimal("200.00"))
        self.assertEqual(remesa.usuario_responsable, self.tesorero)
        self.assertEqual(remesa.detalles.count(), 2)

        # Verificar actualización del saldo teórico: 100 inicial + 200 remesa = 300
        saldos = self.apertura.saldos_actuales
        self.assertEqual(saldos[self.usd.pk], Decimal("300.00"))
        self.assertEqual(self.apertura.obtener_saldo_actual(self.usd.pk), Decimal("300.00"))

        # Verificar inventario teórico actualizado
        inventario = self.apertura.obtener_inventario_actual(self.usd.pk)
        self.assertEqual(inventario[self.billete_usd_100.pk]["cantidad"], 1)
        self.assertEqual(inventario[self.billete_usd_50.pk]["cantidad"], 2)
        self.assertEqual(inventario[self.billete_usd_20.pk]["cantidad"], 5)

    def test_devolucion_remesa_actualiza_saldo_e_inventario(self):
        """Una devolución de Caja a Tesorería descuenta el saldo e inventario."""
        # Se tiene 1 billete de USD 100 en caja. Se devuelve a Tesorería.
        desglose = [
            {"denominacion_id": self.billete_usd_100.pk, "cantidad": 1},
        ]

        remesa = registrar_remesa(
            usuario=self.tesorero,
            caja_id=self.caja.pk,
            tipo=Remesa.Tipo.DEVOLUCION,
            moneda_id=self.usd.pk,
            desglose=desglose,
            observaciones="Devolución de excedente",
        )

        self.assertEqual(remesa.tipo, Remesa.Tipo.DEVOLUCION)
        self.assertIn("Caja CAJA-01", remesa.origen)
        self.assertEqual(remesa.destino, "Tesorería")
        self.assertEqual(remesa.monto_total, Decimal("100.00"))

        # El saldo en USD queda en 0.00
        self.assertEqual(self.apertura.obtener_saldo_actual(self.usd.pk), Decimal("0.00"))
        inventario = self.apertura.obtener_inventario_actual(self.usd.pk)
        self.assertEqual(inventario[self.billete_usd_100.pk]["cantidad"], 0)

    def test_rechaza_egreso_superior_al_saldo_disponible(self):
        """Criterio 6: El sistema no debe permitir registrar egresos superiores al efectivo disponible."""
        # La caja tiene 100 USD. Intentamos devolver 200 USD (abasteciendo primero con billetes de 50).
        # Agregamos 2 billetes de 50 para que existan las denominaciones, pero queremos devolver más del total
        desglose_exceso = [
            {"denominacion_id": self.billete_usd_100.pk, "cantidad": 2},  # 200 USD > 100 USD disponibles
        ]

        with self.assertRaisesMessage(RemesaError, "supera el saldo disponible en caja"):
            registrar_remesa(
                usuario=self.tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.DEVOLUCION,
                moneda_id=self.usd.pk,
                desglose=desglose_exceso,
            )

    def test_rechaza_egreso_superior_al_inventario_de_billetes_disponible(self):
        """Criterio 6: No permite devolver billetes que no se encuentran en el inventario físico de la caja."""
        # La caja tiene 100 USD en 1 billete de 100.
        # No tiene billetes de 50. Si intenta devolver 2 billetes de 50 (100 USD en monto),
        # debe ser rechazado por falta de stock de esa denominación.
        desglose = [
            {"denominacion_id": self.billete_usd_50.pk, "cantidad": 2},
        ]

        with self.assertRaisesMessage(RemesaError, "supera la cantidad disponible en el inventario"):
            registrar_remesa(
                usuario=self.tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.DEVOLUCION,
                moneda_id=self.usd.pk,
                desglose=desglose,
            )

    def test_rechaza_remesa_si_caja_no_tiene_apertura_activa(self):
        """No permite remesas en cajas cerradas o sin apertura activa."""
        self.apertura.estado = AperturaCaja.Estado.CERRADA
        self.apertura.fecha_cierre = timezone.now()
        self.apertura.save()

        desglose = [{"denominacion_id": self.billete_usd_100.pk, "cantidad": 1}]
        with self.assertRaisesMessage(RemesaError, "La caja no tiene una apertura activa."):
            registrar_remesa(
                usuario=self.tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.ENTREGA,
                moneda_id=self.usd.pk,
                desglose=desglose,
            )

    def test_rechaza_denominaciones_de_distinta_moneda(self):
        """Rechaza si se incluye una denominación que no pertenece a la moneda de la remesa."""
        desglose = [
            {"denominacion_id": self.billete_pyg_100k.pk, "cantidad": 1},  # PYG en remesa USD
        ]
        with self.assertRaisesMessage(RemesaError, "no pertenecen a la moneda seleccionada"):
            registrar_remesa(
                usuario=self.tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.ENTREGA,
                moneda_id=self.usd.pk,
                desglose=desglose,
            )

    def test_rechaza_denominaciones_duplicadas(self):
        """Rechaza líneas repetidas de la misma denominación."""
        desglose = [
            {"denominacion_id": self.billete_usd_50.pk, "cantidad": 1},
            {"denominacion_id": self.billete_usd_50.pk, "cantidad": 2},
        ]
        with self.assertRaisesMessage(RemesaError, "No repita denominaciones"):
            registrar_remesa(
                usuario=self.tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.ENTREGA,
                moneda_id=self.usd.pk,
                desglose=desglose,
            )

    def test_rechaza_cantidades_invalidas(self):
        """Rechaza desglose vacío o con cantidades cero o negativas."""
        with self.assertRaisesMessage(RemesaError, "Debe indicar el desglose"):
            registrar_remesa(
                usuario=self.tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.ENTREGA,
                moneda_id=self.usd.pk,
                desglose=[],
            )

        with self.assertRaisesMessage(RemesaError, "debe ser mayor a cero"):
            registrar_remesa(
                usuario=self.tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.ENTREGA,
                moneda_id=self.usd.pk,
                desglose=[{"denominacion_id": self.billete_usd_50.pk, "cantidad": 0}],
            )

    def test_control_permisos_tesorero_y_administrador(self):
        """Solo usuarios con rol tesorero o administrador pueden registrar remesas."""
        rf = RequestFactory()
        req_cajero = rf.post("/")
        req_cajero.user = self.cajero

        desglose = [{"denominacion_id": self.billete_usd_100.pk, "cantidad": 1}]

        # Cajero sin rol tesorero ni administrador es rechazado
        with patch("cajas.services.tiene_rol", return_value=False):
            with self.assertRaises(PermissionDenied):
                registrar_remesa(
                    request=req_cajero,
                    caja_id=self.caja.pk,
                    tipo=Remesa.Tipo.ENTREGA,
                    moneda_id=self.usd.pk,
                    desglose=desglose,
                )

        # Usuario con rol tesorero es aceptado
        req_tesorero = rf.post("/")
        req_tesorero.user = self.tesorero
        with patch("cajas.services.tiene_rol", side_effect=lambda req, rol: rol == "tesorero"):
            rem = registrar_remesa(
                request=req_tesorero,
                caja_id=self.caja.pk,
                tipo=Remesa.Tipo.ENTREGA,
                moneda_id=self.usd.pk,
                desglose=desglose,
            )
            self.assertIsNotNone(rem.pk)

    def test_historial_y_detalle_de_remesas(self):
        """Criterio 7: Las remesas realizadas deben permanecer disponibles para consulta histórica."""
        remesa = registrar_remesa(
            usuario=self.tesorero,
            caja_id=self.caja.pk,
            tipo=Remesa.Tipo.ENTREGA,
            moneda_id=self.usd.pk,
            desglose=[{"denominacion_id": self.billete_usd_100.pk, "cantidad": 2}],
            observaciones="Remesa de prueba para historial",
        )

        client = Client()
        client.force_login(self.tesorero)
        session = client.session
        session["oidc_id_token_expiration"] = (timezone.now() + timedelta(hours=1)).timestamp()
        session.save()

        with patch("core.keycloak.obtener_roles", return_value=["tesorero"]), \
             patch("core.context_processors.obtener_roles", return_value=["tesorero"]):
            # Historial list view
            resp_list = client.get(reverse("remesa-list"))
            self.assertEqual(resp_list.status_code, 200)
            self.assertContains(resp_list, f"/cajas/remesas/{remesa.pk}/")
            self.assertContains(resp_list, "Tesorería")
            self.assertContains(resp_list, "200")

            # Filtro por tipo
            resp_filtro = client.get(reverse("remesa-list"), {"tipo": "ENTREGA"})
            self.assertEqual(resp_filtro.status_code, 200)
            self.assertContains(resp_filtro, f"/cajas/remesas/{remesa.pk}/")

            # Detalle view
            resp_det = client.get(reverse("remesa-detail", kwargs={"id_remesa": remesa.pk}))
            self.assertEqual(resp_det.status_code, 200)
            self.assertContains(resp_det, f"Remesa #{remesa.pk}")
            self.assertContains(resp_det, "Remesa de prueba para historial")
            self.assertContains(resp_det, "Desglose de billetes")
            self.assertContains(resp_det, "100")
            self.assertContains(resp_det, "2")
