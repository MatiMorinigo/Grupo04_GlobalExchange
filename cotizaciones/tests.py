import json
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import AuditoriaMoneda, Moneda, TasaCambio
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory

from clientes.models import (
    CategoriaCliente,
    Cliente,
    ConfiguracionBeneficioCategoria,
)
from usuarios.models import UsuarioCliente

from .services import SimulacionConversionError, simular_conversion
from .views import obtener_categoria_para_simulacion


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

class CotizacionWebViewTests(TestCase):
    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )

    def test_cotizaciones_list_renders_empty_state(self):
        response = self.client.get(reverse("cotizacion-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Cotizaciones", content)
        self.assertIn("No hay tasas vigentes para mostrar", content)

    def test_cotizaciones_list_renders_current_rates(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(reverse("cotizacion-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("USD/PYG", content)
        self.assertIn("Gs 7200", content)
        self.assertIn("Gs 7350", content)
        self.assertNotIn("7200,0000", content)
        self.assertNotIn("7350,0000", content)
        self.assertNotIn(",0000", content)

    def test_cotizaciones_list_shows_variation(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7000.0000"),
            precio_venta=Decimal("7100.0000"),
            vigente=False,
            fecha_vigencia=timezone.now() - timezone.timedelta(days=1),
        )
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(reverse("cotizacion-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Subió", content)

    def test_cotizaciones_list_excludes_pairs_with_disabled_currency(self):
        self.usd.activa = False
        self.usd.save(update_fields=["activa"])
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(reverse("cotizacion-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("USD/PYG", content)
        self.assertIn("No hay tasas vigentes para mostrar", content)


class CotizacionApiTests(TestCase):
    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )

    def test_api_returns_current_rates(self):
        tasa = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(reverse("cotizacion-tasa-list"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id_tasa"], tasa.id_tasa)
        self.assertEqual(response.json()[0]["moneda_origen"], "USD")

    def test_api_pair_endpoint_returns_current_rate(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(
            reverse(
                "cotizacion-tasa-par-vigente",
                kwargs={"moneda_origen": "USD", "moneda_destino": "PYG"},
            ),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["moneda_destino"], "PYG")

    def test_api_filters_by_origin_currency(self):
        brl, _ = Moneda.objects.get_or_create(
            codigo="BRL",
            defaults={"nombre": "Real brasileño", "simbolo": "R$"},
        )
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )
        TasaCambio.objects.create(
            moneda_origen=brl,
            moneda_destino=self.pyg,
            precio_compra=Decimal("1300.0000"),
            precio_venta=Decimal("1450.0000"),
        )

        response = self.client.get(
            reverse("cotizacion-tasa-list"),
            {"moneda_origen": "BRL"},
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["moneda_origen"], "BRL")


class SimulacionConversionWebTests(TestCase):
    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )
        self.eur, _ = Moneda.objects.get_or_create(
            codigo="EUR",
            defaults={"nombre": "Euro", "simbolo": "€"},
        )

    def test_simulador_renders_form(self):
        response = self.client.get(reverse("cotizacion-simulador"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Simulador de conversión", content)
        self.assertIn("Moneda de origen", content)
        self.assertIn("Moneda de destino", content)
        self.assertIn("Seleccione una moneda", content)
        self.assertNotIn("Select an option", content)

    def test_simulador_calculates_foreign_currency_to_pyg(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.post(
            reverse("cotizacion-simulador"),
            {
                "moneda_origen": "USD",
                "moneda_destino": "PYG",
                "monto": "100.00",
            },
            HTTP_HOST="127.0.0.1",
        )
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Total estimado a recibir", content)
        self.assertIn("PYG", content)
        self.assertIn("720000", content)
        self.assertIn("Compra", content)

    def test_simulador_shows_error_without_current_rate(self):
        response = self.client.post(
            reverse("cotizacion-simulador"),
            {
                "moneda_origen": "EUR",
                "moneda_destino": "PYG",
                "monto": "100.00",
            },
            HTTP_HOST="127.0.0.1",
        )
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("No existe una tasa vigente", content)


class SimulacionConversionApiTests(TestCase):
    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )
        self.eur, _ = Moneda.objects.get_or_create(
            codigo="EUR",
            defaults={"nombre": "Euro", "simbolo": "€"},
        )

    def test_api_simulates_foreign_currency_to_pyg(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.post(
            reverse("cotizacion-simulacion-create"),
            data=json.dumps(
                {
                    "moneda_origen": "USD",
                    "moneda_destino": "PYG",
                    "monto": "100.00",
                }
            ),
            content_type="application/json",
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tipo_tasa"], "compra")
        self.assertEqual(response.json()["total_final"], 720000.0)

    def test_api_simulates_pyg_to_foreign_currency(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.post(
            reverse("cotizacion-simulacion-create"),
            data=json.dumps(
                {
                    "moneda_origen": "PYG",
                    "moneda_destino": "USD",
                    "monto": "100000.00",
                }
            ),
            content_type="application/json",
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tipo_tasa"], "venta")
        self.assertEqual(response.json()["total_final"], 13.61)

    def test_api_rejects_conversion_without_pyg(self):
        response = self.client.post(
            reverse("cotizacion-simulacion-create"),
            data=json.dumps(
                {
                    "moneda_origen": "USD",
                    "moneda_destino": "EUR",
                    "monto": "100.00",
                }
            ),
            content_type="application/json",
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("guaraníes", str(response.json()))

    def test_simulacion_rechaza_conversion_con_moneda_deshabilitada(self):
        """El servicio no debe usar tasas de una moneda deshabilitada, aunque
        se lo invoque directamente sin pasar por la validación del serializer."""
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )
        self.usd.activa = False
        self.usd.save(update_fields=["activa"])

        with self.assertRaises(SimulacionConversionError):
            simular_conversion("USD", "PYG", Decimal("100.00"))

class SimulacionBeneficiosTests(TestCase):
    """Prueba la aplicación de beneficios por categoría en el simulador."""

    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={
                "nombre": "Guaraní paraguayo",
                "simbolo": "Gs",
            },
        )

        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={
                "nombre": "Dólar estadounidense",
                "simbolo": "US$",
            },
        )

        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7500.0000"),
            precio_venta=Decimal("7600.0000"),
        )

        self.configuracion_vip, _ = (
            ConfiguracionBeneficioCategoria.objects.update_or_create(
                categoria=CategoriaCliente.VIP,
                defaults={
                    "porcentaje_beneficio": Decimal("5.00"),
                    "limite_mensual_pyg": Decimal("50000000.00"),
                },
            )
        )

        ConfiguracionBeneficioCategoria.objects.update_or_create(
            categoria=CategoriaCliente.MINORISTA,
            defaults={
                "porcentaje_beneficio": Decimal("0.00"),
                "limite_mensual_pyg": Decimal("0.00"),
            },
        )

    def test_vip_aplica_beneficio_completo_usd_a_pyg(self):
        resultado = simular_conversion(
            "USD",
            "PYG",
            Decimal("100.00"),
            categoria=CategoriaCliente.VIP,
        )

        self.assertEqual(
            resultado["subtotal"],
            Decimal("750000.00"),
        )
        self.assertEqual(
            resultado["beneficio_porcentaje"],
            Decimal("5.00"),
        )
        self.assertEqual(
            resultado["beneficio_monto"],
            Decimal("37500.00"),
        )
        self.assertEqual(
            resultado["total_final"],
            Decimal("787500.00"),
        )

    def test_vip_aplica_beneficio_parcial_al_superar_limite(self):
        resultado = simular_conversion(
            "USD",
            "PYG",
            Decimal("10000.00"),
            categoria=CategoriaCliente.VIP,
        )

        self.assertEqual(
            resultado["subtotal"],
            Decimal("75000000.00"),
        )
        self.assertEqual(
            resultado["monto_beneficiado_pyg"],
            Decimal("50000000.00"),
        )
        self.assertEqual(
            resultado["beneficio_monto"],
            Decimal("2500000.00"),
        )
        self.assertEqual(
            resultado["total_final"],
            Decimal("77500000.00"),
        )
        self.assertIn(
            "parcialmente",
            resultado["mensaje_beneficio"],
        )

    def test_vip_aplica_beneficio_pyg_a_usd(self):
        resultado = simular_conversion(
            "PYG",
            "USD",
            Decimal("7600000.00"),
            categoria=CategoriaCliente.VIP,
        )

        self.assertEqual(
            resultado["subtotal"],
            Decimal("1000.00"),
        )

        self.assertEqual(
            resultado["beneficio_porcentaje"],
            Decimal("5.00"),
        )

        self.assertEqual(
            resultado["total_final"],
            Decimal("1052.63"),
        )

    def test_minorista_sin_beneficio(self):
        resultado = simular_conversion(
            "USD",
            "PYG",
            Decimal("100.00"),
            categoria=CategoriaCliente.MINORISTA,
        )

        self.assertEqual(
            resultado["subtotal"],
            Decimal("750000.00"),
        )
        self.assertEqual(
            resultado["beneficio_monto"],
            Decimal("0.00"),
        )
        self.assertEqual(
            resultado["total_final"],
            Decimal("750000.00"),
        )

    def test_simulacion_no_consume_limite_mensual(self):
        limite_original = self.configuracion_vip.limite_mensual_pyg

        simular_conversion(
            "USD",
            "PYG",
            Decimal("10000.00"),
            categoria=CategoriaCliente.VIP,
        )

        simular_conversion(
            "USD",
            "PYG",
            Decimal("10000.00"),
            categoria=CategoriaCliente.VIP,
        )

        self.configuracion_vip.refresh_from_db()

        self.assertEqual(
            self.configuracion_vip.limite_mensual_pyg,
            limite_original,
        )

class CategoriaSimulacionTests(TestCase):
    """Prueba la selección automática de categoría para el simulador."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_visitante_utiliza_categoria_minorista(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()

        categoria = obtener_categoria_para_simulacion(request)

        self.assertEqual(
            categoria,
            CategoriaCliente.MINORISTA,
        )

    def test_usuario_utiliza_categoria_de_cliente_activo(self):
        user = User.objects.create_user(
            username="usuario_vip",
            password="testpass123",
        )

        cliente = Cliente.objects.create(
            ruc="80099999-1",
            nombre="Cliente VIP",
            categoria=CategoriaCliente.VIP,
            tipo="FISICA",
        )

        UsuarioCliente.objects.create(
            usuario=user,
            cliente_activo=cliente,
        )

        request = self.factory.get("/")
        request.user = user

        categoria = obtener_categoria_para_simulacion(request)

        self.assertEqual(
            categoria,
            CategoriaCliente.VIP,
        )

    def test_usuario_sin_cliente_activo_utiliza_minorista(self):
        user = User.objects.create_user(
            username="usuario_sin_cliente",
            password="testpass123",
        )

        request = self.factory.get("/")
        request.user = user

        categoria = obtener_categoria_para_simulacion(request)

        self.assertEqual(
            categoria,
            CategoriaCliente.MINORISTA,
        )


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class MonedaWebViewTests(TestCase):
    """Prueba la gestión web de monedas admitidas y su registro de auditoría."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="adminmonedas",
            password="testpass123",
        )
        self.client.force_login(self.user)

        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )

    def test_moneda_list_renders_currencies(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(reverse("moneda-web-list"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "USD")
        self.assertContains(response, "Dólar estadounidense")

    def test_moneda_list_requires_admin(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=False):
            response = self.client.get(reverse("moneda-web-list"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 403)

    def test_moneda_create_inserts_record_and_logs_auditoria(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("moneda-web-create"),
                {
                    "codigo": "gbp",
                    "nombre": "Libra esterlina",
                    "simbolo": "£",
                },
                HTTP_HOST="127.0.0.1",
            )

        moneda = Moneda.objects.get(codigo="GBP")
        self.assertEqual(moneda.nombre, "Libra esterlina")

        auditoria = AuditoriaMoneda.objects.get(moneda=moneda)
        self.assertEqual(auditoria.accion, "CREACION")
        self.assertEqual(auditoria.realizado_por, self.user)
        self.assertEqual(auditoria.datos_nuevos["codigo"], "GBP")

    def test_moneda_update_changes_fields_and_logs_auditoria(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("moneda-web-update", kwargs={"codigo": "USD"}),
                {
                    "codigo": "USD",
                    "nombre": "Dólar de Estados Unidos",
                    "simbolo": "US$",
                },
                HTTP_HOST="127.0.0.1",
            )

        self.usd.refresh_from_db()
        self.assertEqual(self.usd.nombre, "Dólar de Estados Unidos")

        auditoria = AuditoriaMoneda.objects.get(moneda=self.usd, accion="MODIFICACION")
        self.assertEqual(auditoria.datos_anteriores["nombre"], "Dólar estadounidense")
        self.assertEqual(auditoria.datos_nuevos["nombre"], "Dólar de Estados Unidos")

    def test_moneda_update_does_not_allow_changing_codigo(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("moneda-web-update", kwargs={"codigo": "USD"}),
                {
                    "codigo": "XXX",
                    "nombre": "Dólar estadounidense",
                    "simbolo": "US$",
                },
                HTTP_HOST="127.0.0.1",
            )

        self.assertTrue(Moneda.objects.filter(codigo="USD").exists())
        self.assertFalse(Moneda.objects.filter(codigo="XXX").exists())

    def test_moneda_deactivate_disables_currency_and_logs_auditoria(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("moneda-web-deactivate", kwargs={"codigo": "USD"}),
                HTTP_HOST="127.0.0.1",
            )

        self.usd.refresh_from_db()
        self.assertFalse(self.usd.activa)

        auditoria = AuditoriaMoneda.objects.get(moneda=self.usd, accion="DESHABILITACION")
        self.assertEqual(auditoria.realizado_por, self.user)

    def test_moneda_deactivate_twice_shows_info_message_without_duplicate_log(self):
        self.usd.activa = False
        self.usd.save(update_fields=["activa"])

        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("moneda-web-deactivate", kwargs={"codigo": "USD"}),
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(
            AuditoriaMoneda.objects.filter(moneda=self.usd, accion="DESHABILITACION").count(),
            0,
        )

    def test_moneda_activate_enables_currency_and_logs_auditoria(self):
        self.usd.activa = False
        self.usd.save(update_fields=["activa"])

        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("moneda-web-activate", kwargs={"codigo": "USD"}),
                HTTP_HOST="127.0.0.1",
            )

        self.usd.refresh_from_db()
        self.assertTrue(self.usd.activa)

        auditoria = AuditoriaMoneda.objects.get(moneda=self.usd, accion="HABILITACION")
        self.assertEqual(auditoria.realizado_por, self.user)

    def test_moneda_activate_twice_shows_info_message_without_duplicate_log(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            self.client.post(
                reverse("moneda-web-activate", kwargs={"codigo": "USD"}),
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(
            AuditoriaMoneda.objects.filter(moneda=self.usd, accion="HABILITACION").count(),
            0,
        )

    def test_moneda_list_default_filters_only_active(self):
        eur, _ = Moneda.objects.get_or_create(
            codigo="EUR", defaults={"nombre": "Euro", "simbolo": "€"}
        )
        eur.activa = False
        eur.save(update_fields=["activa"])

        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(reverse("moneda-web-list"), HTTP_HOST="127.0.0.1")

        self.assertContains(response, "USD")
        self.assertNotContains(response, "EUR")

    def test_moneda_list_estado_todas_shows_all(self):
        eur, _ = Moneda.objects.get_or_create(
            codigo="EUR", defaults={"nombre": "Euro", "simbolo": "€"}
        )
        eur.activa = False
        eur.save(update_fields=["activa"])

        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(
                reverse("moneda-web-list"), {"estado": "todas"}, HTTP_HOST="127.0.0.1"
            )

        self.assertContains(response, "USD")
        self.assertContains(response, "EUR")

    def test_moneda_list_estado_deshabilitadas_shows_only_inactive(self):
        eur, _ = Moneda.objects.get_or_create(
            codigo="EUR", defaults={"nombre": "Euro", "simbolo": "€"}
        )
        eur.activa = False
        eur.save(update_fields=["activa"])

        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.get(
                reverse("moneda-web-list"), {"estado": "deshabilitadas"}, HTTP_HOST="127.0.0.1"
            )

        self.assertNotContains(response, "USD")
        self.assertContains(response, "EUR")

    def test_moneda_form_rejects_duplicate_codigo(self):
        with patch("core.mixins.AdminRequiredMixin.test_func", return_value=True):
            response = self.client.post(
                reverse("moneda-web-create"),
                {
                    "codigo": "USD",
                    "nombre": "Otro dólar",
                    "simbolo": "US$",
                },
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe una moneda registrada con este código.")
