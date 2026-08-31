from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import Cliente

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