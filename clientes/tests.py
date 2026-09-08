from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from decimal import Decimal
from django.core.exceptions import ValidationError
from .models import Cliente, ConfiguracionBeneficioCategoria



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