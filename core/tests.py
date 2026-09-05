from django.contrib import messages
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse

from core.context_processors import app_environment
from core.views import home


class HomeViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def render_home(self, user):
        request = self.factory.get("/")
        request.user = user
        request.session = {}
        request._messages = FallbackStorage(request)
        return home(request)

    def test_home_renders_for_anonymous_user(self):
        response = self.client.get("/", HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Iniciar sesión", content)
        self.assertIn('id="main-content"', content)
        self.assertIn("Menú principal", content)
        self.assertIn("Disponible", content)
        self.assertIn("Próximamente", content)

    def test_authenticated_user_sees_full_name_and_logout(self):
        user = User(username="jperez", first_name="Juan", last_name="Pérez")
        response = self.render_home(user)
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Juan Pérez", content)
        self.assertIn("J", content)
        self.assertIn("Cerrar sesión", content)
        self.assertNotIn("Iniciar sesión", content)

    def test_authenticated_user_falls_back_to_username(self):
        user = User(username="jperez")
        response = self.render_home(user)
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("jperez", content)
        self.assertIn("Cerrar sesión", content)

    def test_oidc_routes_used_by_navbar_exist(self):
        self.assertEqual(reverse("oidc_authentication_init"), "/oidc/authenticate/")
        self.assertEqual(reverse("oidc_logout"), "/oidc/logout/")
        self.assertEqual(resolve("/oidc/authenticate/").url_name, "oidc_authentication_init")
        self.assertEqual(resolve("/oidc/logout/").url_name, "oidc_logout")

    def test_cotizaciones_is_available_for_anonymous_users(self):
        response = self.render_home(AnonymousUser())
        content = response.content.decode("utf-8")

        self.assertIn(reverse("cotizacion-web-list"), content)
        self.assertIn("Ver Cotizaciones", content)
        self.assertNotIn(reverse("cliente-web-list"), content)

    def test_upcoming_modules_are_not_keyboard_links(self):
        response = self.render_home(AnonymousUser())
        content = response.content.decode("utf-8")

        self.assertIn("Operaciones de cambio", content)
        self.assertIn("Módulo aún no disponible", content)
        self.assertEqual(content.count('<span class="small-box-footer'), 1)
        self.assertEqual(content.count('aria-disabled="true"'), 2)
        self.assertNotIn("Placeholder", content)
        self.assertNotIn("Invitado", content)

    @override_settings(APP_ENV="Producción")
    def test_environment_indicator_is_hidden_in_production(self):
        self.assertEqual(app_environment(None), {"app_environment": "", "es_administrador": False})

    @override_settings(APP_ENV="Desarrollo")
    def test_environment_indicator_is_visible_outside_production(self):
        self.assertEqual(app_environment(None), {"app_environment": "Desarrollo", "es_administrador": False})

    def test_error_messages_use_bootstrap_danger_class(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.session = {}
        request._messages = FallbackStorage(request)
        messages.error(request, "Error visible")

        content = render_to_string(
            "base.html",
            {"active_menu": "home", "app_environment": "Desarrollo"},
            request=request,
        )

        self.assertIn("alert-danger", content)
        self.assertIn("Error visible", content)


class LogoutViewTests(TestCase):
    @override_settings(
        OIDC_RP_CLIENT_ID="global-exchange-web",
        OIDC_OP_AUTHORIZATION_ENDPOINT=(
            "http://localhost:8080/realms/global-exchange/protocol/openid-connect/auth"
        ),
        OIDC_OP_LOGOUT_ENDPOINT=None,
    )
    def test_oidc_logout_get_logs_out_and_redirects_to_keycloak_logout(self):
        user = User.objects.create_user(username="jperez")
        self.client.force_login(user)
        session = self.client.session
        session["oidc_id_token"] = "id-token-demo"
        session.save()

        response = self.client.get(reverse("oidc_logout"), HTTP_HOST="localhost:8000")

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "http://localhost:8080/realms/global-exchange/protocol/openid-connect/logout",
            response["Location"],
        )
        self.assertIn("client_id=global-exchange-web", response["Location"])
        self.assertIn("post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A8000%2F", response["Location"])
        self.assertIn("id_token_hint=id-token-demo", response["Location"])
        self.assertNotIn("_auth_user_id", self.client.session)
