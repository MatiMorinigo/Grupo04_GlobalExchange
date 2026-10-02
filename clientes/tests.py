from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from decimal import Decimal
from django.core.exceptions import ValidationError
from datetime import timedelta, datetime
from django.utils import timezone
from .models import (
    CategoriaCliente,
    Cliente,
    ConfiguracionBeneficioCategoria,
    ConfiguracionVIP,
    TipoCliente,
)
from cotizaciones.models import Moneda, TasaCambio
from transacciones.models import (
    EstadoTransaccion,
    EtapaCancelacion,
    TipoOperacion,
    Transaccion,
)

from .services import evaluar_vip_temporal


MIDDLEWARE_SIN_OIDC = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class ClienteWebViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123"
        )
        self.client.force_login(self.user)

    def test_clientes_list_renders(self):
        Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Demo",
            categoria="MINORISTA",
            tipo="FISICA",
        )
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(reverse("cliente-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cliente Demo", content)

    def test_clientes_list_shows_empty_state(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(reverse("cliente-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("No hay clientes para mostrar", content)

    def test_clientes_create_inserts_record(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("cliente-web-create"),
                {
                    "ruc": "80012345-6",
                    "nombre": "Cliente Demo",
                    "categoria": "MINORISTA",
                    "tipo": "FISICA",
                },
                HTTP_HOST="127.0.0.1",
            )
        self.assertTrue(Cliente.objects.filter(ruc="80012345-6").exists())

    def test_clientes_detail_renders_registered_data(self):
        cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Demo",
            categoria="CORPORATIVO",
            tipo="JURIDICA",
        )
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(
                reverse("cliente-web-detail", kwargs={"id_cliente": cliente.id_cliente}),
                HTTP_HOST="127.0.0.1",
            )
        content = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cliente Demo", content)

    def test_clientes_update_changes_record(self):
        cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Demo",
            categoria="MINORISTA",
            tipo="FISICA",
        )
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("cliente-web-update", kwargs={"id_cliente": cliente.id_cliente}),
                {
                    "ruc": "80012345-6",
                    "nombre": "Cliente Actualizado",
                    "categoria": "VIP",
                    "tipo": "FISICA",
                },
                HTTP_HOST="127.0.0.1",
            )
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre, "Cliente Actualizado")
        self.assertEqual(cliente.categoria, "VIP")

    def test_clientes_deactivate_marks_record_inactive(self):
        cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Demo",
            categoria="MINORISTA",
            tipo="FISICA",
        )
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("cliente-web-deactivate", kwargs={"id_cliente": cliente.id_cliente}),
                HTTP_HOST="127.0.0.1",
            )
        cliente.refresh_from_db()
        self.assertFalse(cliente.activo)

class ConfiguracionBeneficioCategoriaTests(TestCase):
    """Prueba las reglas de validación de beneficios por categoría."""

    def setUp(self):
        self.configuracion, _ = ConfiguracionBeneficioCategoria.objects.get_or_create(
            categoria="VIP",
            defaults={
                "porcentaje_beneficio": Decimal("5.00"),
                "limite_mensual_pyg": Decimal("50000000.00"),
            },
        )

    def test_configuracion_valida(self):
        self.configuracion.porcentaje_beneficio = Decimal("5.00")
        self.configuracion.limite_mensual_pyg = Decimal("50000000.00")

        self.configuracion.full_clean()

    def test_rechaza_beneficio_negativo(self):
        self.configuracion.porcentaje_beneficio = Decimal("-1.00")

        with self.assertRaises(ValidationError):
            self.configuracion.full_clean()

    def test_rechaza_beneficio_superior_a_30(self):
        self.configuracion.porcentaje_beneficio = Decimal("30.01")

        with self.assertRaises(ValidationError):
            self.configuracion.full_clean()

    def test_acepta_beneficio_maximo_de_30(self):
        self.configuracion.porcentaje_beneficio = Decimal("30.00")

        self.configuracion.full_clean()

    def test_rechaza_limite_mensual_negativo(self):
        self.configuracion.limite_mensual_pyg = Decimal("-1.00")

        with self.assertRaises(ValidationError):
            self.configuracion.full_clean()

@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class ConfiguracionBeneficioWebViewTests(TestCase):
    """Prueba la consulta y modificación web de beneficios por categoría."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="adminbeneficios",
            password="testpass123",
        )
        self.client.force_login(self.user)

        self.configuracion, _ = ConfiguracionBeneficioCategoria.objects.get_or_create(
            categoria="VIP",
            defaults={
                "porcentaje_beneficio": Decimal("5.00"),
                "limite_mensual_pyg": Decimal("50000000.00"),
            },
        )

    def test_listado_configuraciones_renders(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(
                reverse("configuracion_beneficios"),
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "VIP")
        self.assertContains(response, "Configuración de beneficios por categoría")

    def test_actualizar_configuracion(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.post(
                reverse(
                    "configuracion_beneficios_editar",
                    kwargs={"pk": self.configuracion.pk},
                ),
                {
                    "porcentaje_beneficio": "10.00",
                    "limite_mensual_pyg": "60000000.00",
                },
                HTTP_HOST="127.0.0.1",
            )

        self.configuracion.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.configuracion.porcentaje_beneficio,
            Decimal("10.00"),
        )
        self.assertEqual(
            self.configuracion.limite_mensual_pyg,
            Decimal("60000000.00"),
        )

    def test_usuario_sin_permiso_recibe_403(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=False):
            response = self.client.get(
                reverse("configuracion_beneficios"),
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(response.status_code, 403)

class CategoriaEfectivaTests(TestCase):
    """Prueba la categoría efectiva considerando promociones VIP temporales."""

    def test_cliente_sin_promocion_mantiene_categoria_base(self):
        cliente = Cliente.objects.create(
            ruc="TEST-CAT-001",
            nombre="Cliente Minorista",
            categoria=CategoriaCliente.MINORISTA,
            tipo=TipoCliente.FISICA,
        )

        self.assertEqual(
            cliente.categoria_efectiva,
            CategoriaCliente.MINORISTA,
        )

    def test_cliente_con_vip_temporal_vigente_es_vip(self):
        cliente = Cliente.objects.create(
            ruc="TEST-CAT-002",
            nombre="Cliente VIP Temporal",
            categoria=CategoriaCliente.CORPORATIVO,
            tipo=TipoCliente.JURIDICA,
            vip_vigente_hasta=timezone.localdate() + timedelta(days=1),
        )

        self.assertEqual(
            cliente.categoria_efectiva,
            CategoriaCliente.VIP,
        )

    def test_cliente_con_vip_temporal_vencido_vuelve_a_categoria_base(self):
        cliente = Cliente.objects.create(
            ruc="TEST-CAT-003",
            nombre="Cliente VIP Vencido",
            categoria=CategoriaCliente.MINORISTA,
            tipo=TipoCliente.FISICA,
            vip_vigente_hasta=timezone.localdate() - timedelta(days=1),
        )

        self.assertEqual(
            cliente.categoria_efectiva,
            CategoriaCliente.MINORISTA,
        )

    def test_cliente_vip_base_siempre_es_vip(self):
        cliente = Cliente.objects.create(
            ruc="TEST-CAT-004",
            nombre="Cliente VIP Permanente",
            categoria=CategoriaCliente.VIP,
            tipo=TipoCliente.FISICA,
        )

        self.assertEqual(
            cliente.categoria_efectiva,
            CategoriaCliente.VIP,
        )

class EvaluacionVIPTemporalTests(TestCase):
    """Prueba la evaluación mensual para asignar y renovar VIP temporal."""

    def setUp(self):
        self.configuracion = ConfiguracionVIP.obtener()
        self.configuracion.umbral_mensual_pyg = Decimal("50000000.00")
        self.configuracion.duracion_meses = 2
        self.configuracion.save()

        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={
                "nombre": "Guaraní",
                "simbolo": "Gs.",
                "activa": True,
            },
        )

        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={
                "nombre": "Dólar estadounidense",
                "simbolo": "$",
                "activa": True,
            },
        )

        self.tasa = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7500.0000"),
            precio_venta=Decimal("7600.0000"),
            vigente=True,
        )

    def crear_cliente(self, ruc, categoria=CategoriaCliente.MINORISTA):
        return Cliente.objects.create(
            ruc=ruc,
            nombre=f"Cliente {ruc}",
            categoria=categoria,
            tipo=TipoCliente.FISICA,
        )

    def crear_transaccion(
        self,
        cliente,
        subtotal,
        fecha,
        estado=EstadoTransaccion.COMPLETADA,
        tipo=TipoOperacion.COMPRA,
    ):
        datos = {
            "cliente": cliente,
            "tipo_operacion": tipo,
            "moneda": self.usd,
            "tasa_cambio": self.tasa,
            "tasa_aplicada": Decimal("7600.0000"),
            "fecha_vigencia_tasa": self.tasa.fecha_vigencia,
            "monto_divisa": Decimal("1.00"),
            "subtotal_pyg": Decimal(str(subtotal)),
            "categoria_aplicada": cliente.categoria,
            "beneficio_porcentaje": Decimal("0.00"),
            "limite_beneficio_pyg": Decimal("0.00"),
            "monto_beneficiado_pyg": Decimal("0.00"),
            "beneficio_monto_pyg": Decimal("0.00"),
            "comision_porcentaje": Decimal("0.00"),
            "comision_monto_pyg": Decimal("0.00"),
            "total_pyg": Decimal(str(subtotal)),
            "estado": estado,
        }

        if estado == EstadoTransaccion.COMPLETADA:
            datos["completada_en"] = fecha

        elif estado == EstadoTransaccion.ANULADA:
            datos["completada_en"] = fecha

        elif estado == EstadoTransaccion.CANCELADA:
            datos["cancelada_en"] = fecha
            datos["etapa_cancelacion"] = EtapaCancelacion.PREVIA_PAGO

        return Transaccion.objects.create(**datos)

    def test_superar_umbral_asigna_vip_temporal(self):
        cliente = self.crear_cliente("TEST-VIP-101")

        fecha = timezone.make_aware(
            datetime(2026, 9, 15, 12, 0)
        )

        self.crear_transaccion(
            cliente,
            "50000000.00",
            fecha,
        )

        evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 10, 1).date()
        )

        cliente.refresh_from_db()

        self.assertEqual(
            cliente.vip_vigente_hasta,
            datetime(2026, 11, 30).date(),
        )

        self.assertEqual(
            cliente.categoria,
            CategoriaCliente.MINORISTA,
        )

    def test_no_superar_umbral_no_asigna_vip(self):
        cliente = self.crear_cliente("TEST-VIP-102")

        fecha = timezone.make_aware(
            datetime(2026, 9, 15, 12, 0)
        )

        self.crear_transaccion(
            cliente,
            "49999999.99",
            fecha,
        )

        evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 10, 1).date()
        )

        cliente.refresh_from_db()

        self.assertIsNone(cliente.vip_vigente_hasta)

    def test_vip_permanente_no_recibe_promocion_temporal(self):
        cliente = self.crear_cliente(
            "TEST-VIP-103",
            CategoriaCliente.VIP,
        )

        fecha = timezone.make_aware(
            datetime(2026, 9, 15, 12, 0)
        )

        self.crear_transaccion(
            cliente,
            "100000000.00",
            fecha,
        )

        evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 10, 1).date()
        )

        cliente.refresh_from_db()

        self.assertEqual(cliente.categoria, CategoriaCliente.VIP)
        self.assertIsNone(cliente.vip_vigente_hasta)

    def test_solo_transacciones_completadas_suman_volumen(self):
        cliente = self.crear_cliente("TEST-VIP-104")

        fecha = timezone.make_aware(
            datetime(2026, 9, 15, 12, 0)
        )

        self.crear_transaccion(
            cliente,
            "10000000.00",
            fecha,
            EstadoTransaccion.COMPLETADA,
        )

        self.crear_transaccion(
            cliente,
            "50000000.00",
            fecha,
            EstadoTransaccion.PENDIENTE,
        )

        self.crear_transaccion(
            cliente,
            "50000000.00",
            fecha,
            EstadoTransaccion.CANCELADA,
        )

        self.crear_transaccion(
            cliente,
            "50000000.00",
            fecha,
            EstadoTransaccion.ANULADA,
        )

        evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 10, 1).date()
        )

        cliente.refresh_from_db()

        self.assertIsNone(cliente.vip_vigente_hasta)

    def test_compra_y_venta_completadas_suman_juntas(self):
        cliente = self.crear_cliente("TEST-VIP-105")

        fecha = timezone.make_aware(
            datetime(2026, 9, 15, 12, 0)
        )

        self.crear_transaccion(
            cliente,
            "30000000.00",
            fecha,
            tipo=TipoOperacion.COMPRA,
        )

        self.crear_transaccion(
            cliente,
            "25000000.00",
            fecha,
            tipo=TipoOperacion.VENTA,
        )

        evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 10, 1).date()
        )

        cliente.refresh_from_db()

        self.assertEqual(
            cliente.vip_vigente_hasta,
            datetime(2026, 11, 30).date(),
        )

    def test_nueva_evaluacion_renueva_vigencia_desde_el_nuevo_mes(self):
        cliente = self.crear_cliente("TEST-VIP-106")

        fecha_septiembre = timezone.make_aware(
            datetime(2026, 9, 15, 12, 0)
        )

        self.crear_transaccion(
            cliente,
            "50000000.00",
            fecha_septiembre,
        )

        evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 10, 1).date()
        )

        cliente.refresh_from_db()

        self.assertEqual(
            cliente.vip_vigente_hasta,
            datetime(2026, 11, 30).date(),
        )

        fecha_octubre = timezone.make_aware(
            datetime(2026, 10, 15, 12, 0)
        )

        self.crear_transaccion(
            cliente,
            "50000000.00",
            fecha_octubre,
        )

        evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 11, 1).date()
        )

        cliente.refresh_from_db()

        self.assertEqual(
            cliente.vip_vigente_hasta,
            datetime(2026, 12, 31).date(),
        )

    def test_sin_nuevo_umbral_no_extiende_vigencia(self):
        cliente = self.crear_cliente("TEST-VIP-107")
        cliente.vip_vigente_hasta = datetime(2026, 12, 31).date()
        cliente.save(update_fields=["vip_vigente_hasta"])

        evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 12, 1).date()
        )

        cliente.refresh_from_db()

        self.assertEqual(
            cliente.vip_vigente_hasta,
            datetime(2026, 12, 31).date(),
        )

    def test_umbral_cero_desactiva_evaluacion(self):
        self.configuracion.umbral_mensual_pyg = Decimal("0.00")
        self.configuracion.save()

        cliente = self.crear_cliente("TEST-VIP-108")

        fecha = timezone.make_aware(
            datetime(2026, 9, 15, 12, 0)
        )

        self.crear_transaccion(
            cliente,
            "100000000.00",
            fecha,
        )

        resultado = evaluar_vip_temporal(
            fecha_referencia=datetime(2026, 10, 1).date()
        )

        cliente.refresh_from_db()

        self.assertIsNone(cliente.vip_vigente_hasta)
        self.assertEqual(resultado["evaluados"], 0)
        self.assertEqual(resultado["actualizados"], 0)

@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class ConfiguracionVIPWebViewTests(TestCase):
    """Prueba la consulta y modificación de la configuración VIP temporal."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="adminvip",
            password="testpass123",
        )
        self.client.force_login(self.user)

    def test_configuracion_vip_renders(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(
                reverse("configuracion-vip"),
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configuración VIP temporal")
        self.assertContains(response, "Umbral mensual")
        self.assertContains(response, "Duración")

    def test_actualizar_configuracion_vip(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.post(
                reverse("configuracion-vip"),
                {
                    "umbral_mensual_pyg": "50000000.00",
                    "duracion_meses": "2",
                },
                HTTP_HOST="127.0.0.1",
            )

        configuracion = ConfiguracionVIP.obtener()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            configuracion.umbral_mensual_pyg,
            Decimal("50000000.00"),
        )
        self.assertEqual(configuracion.duracion_meses, 2)
        self.assertEqual(configuracion.modificado_por, self.user)

    def test_usuario_sin_permiso_recibe_403(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=False):
            response = self.client.get(
                reverse("configuracion-vip"),
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(response.status_code, 403)