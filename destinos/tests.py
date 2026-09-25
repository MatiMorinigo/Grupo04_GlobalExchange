from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import CategoriaCliente, Cliente, TipoCliente
from cotizaciones.models import Moneda
from usuarios.models import UsuarioCliente

from .models import (
    AccionAuditoriaDestino,
    AuditoriaDestinoAcreditacion,
    DestinoAcreditacion,
    TipoCuentaBancaria,
    TipoDestinoAcreditacion,
)

MIDDLEWARE_SIN_OIDC = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


def _crear_cliente(ruc, nombre="Cliente de prueba"):
    return Cliente.objects.create(
        ruc=ruc,
        nombre=nombre,
        categoria=CategoriaCliente.MINORISTA,
        tipo=TipoCliente.FISICA,
        activo=True,
    )


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class DestinoAcreditacionModelTests(TestCase):
    """Prueba la coherencia de los datos según el tipo de destino."""

    @classmethod
    def setUpTestData(cls):
        cls.cliente = _crear_cliente("80000010-1", "Cliente Modelo")
        cls.usd = Moneda.objects.get(codigo="USD")
        cls.pyg = Moneda.objects.get(codigo="PYG")

    def _cuenta(self, **cambios):
        datos = {
            "cliente": self.cliente,
            "tipo": TipoDestinoAcreditacion.CUENTA_BANCARIA,
            "titular": "Juan Perez",
            "documento_titular": "1234567",
            "moneda": self.usd,
            "banco": "Banco Continental",
            "tipo_cuenta": TipoCuentaBancaria.CAJA_AHORRO,
            "numero_cuenta": "1234567890",
        }
        datos.update(cambios)
        return DestinoAcreditacion(**datos)

    def _billetera(self, **cambios):
        datos = {
            "cliente": self.cliente,
            "tipo": TipoDestinoAcreditacion.BILLETERA_ELECTRONICA,
            "titular": "Juan Perez",
            "documento_titular": "1234567",
            "moneda": self.pyg,
            "proveedor_billetera": "Tigo Money",
            "numero_billetera": "0981123456",
        }
        datos.update(cambios)
        return DestinoAcreditacion(**datos)

    def test_cuenta_bancaria_valida_se_guarda(self):
        destino = self._cuenta()

        destino.full_clean()
        destino.save()

        self.assertTrue(destino.activo)
        self.assertEqual(destino.moneda_id, "USD")

    def test_cuenta_bancaria_exige_banco_y_numero(self):
        destino = self._cuenta(banco="", numero_cuenta="")

        with self.assertRaises(ValidationError) as contexto:
            destino.full_clean()

        self.assertIn("banco", contexto.exception.message_dict)
        self.assertIn("numero_cuenta", contexto.exception.message_dict)

    def test_billetera_exige_proveedor_y_numero(self):
        destino = self._billetera(proveedor_billetera="", numero_billetera="")

        with self.assertRaises(ValidationError) as contexto:
            destino.full_clean()

        self.assertIn("proveedor_billetera", contexto.exception.message_dict)
        self.assertIn("numero_billetera", contexto.exception.message_dict)

    def test_billetera_descarta_los_campos_de_cuenta_bancaria(self):
        destino = self._billetera(
            banco="Banco Continental",
            tipo_cuenta=TipoCuentaBancaria.CAJA_AHORRO,
            numero_cuenta="1234567890",
        )

        destino.full_clean()

        self.assertEqual(destino.banco, "")
        self.assertEqual(destino.tipo_cuenta, "")
        self.assertEqual(destino.numero_cuenta, "")

    def test_cuenta_bancaria_descarta_los_campos_de_billetera(self):
        destino = self._cuenta(
            proveedor_billetera="Tigo Money",
            numero_billetera="0981123456",
        )

        destino.full_clean()

        self.assertEqual(destino.proveedor_billetera, "")
        self.assertEqual(destino.numero_billetera, "")

    def test_rechaza_moneda_deshabilitada(self):
        moneda = Moneda.objects.create(
            codigo="JPY", nombre="Yen", simbolo="¥", activa=False
        )
        destino = self._cuenta(moneda=moneda)

        with self.assertRaises(ValidationError) as contexto:
            destino.full_clean()

        self.assertIn("moneda", contexto.exception.message_dict)

    def test_rechaza_numero_de_cuenta_no_numerico(self):
        destino = self._cuenta(numero_cuenta="ABC123")

        with self.assertRaises(ValidationError) as contexto:
            destino.full_clean()

        self.assertIn("numero_cuenta", contexto.exception.message_dict)

    def test_identificacion_oculta_el_numero_de_cuenta(self):
        destino = self._cuenta()

        self.assertEqual(destino.identificacion, "Banco Continental · ••••7890")

    def test_etiqueta_prefiere_el_alias(self):
        destino = self._cuenta(alias="Mi cuenta en dólares")

        self.assertEqual(destino.etiqueta, "Mi cuenta en dólares")


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class DestinoWebViewTests(TestCase):
    """Prueba el CRUD web de destinos y su aislamiento por cliente activo."""

    def setUp(self):
        self.user = User.objects.create_user(username="clientedestino", password="testpass123")
        self.client.force_login(self.user)

        self.cliente = _crear_cliente("80000011-1", "Cliente Uno")
        self.otro_cliente = _crear_cliente("80000012-2", "Cliente Dos")
        self.perfil = UsuarioCliente.objects.create(
            usuario=self.user, cliente_activo=self.cliente
        )

        self.usd = Moneda.objects.get(codigo="USD")
        self.eur = Moneda.objects.get(codigo="EUR")

    def _crear_destino(self, cliente=None, **cambios):
        datos = {
            "cliente": cliente or self.cliente,
            "tipo": TipoDestinoAcreditacion.CUENTA_BANCARIA,
            "titular": "Juan Perez",
            "documento_titular": "1234567",
            "moneda": self.usd,
            "banco": "Banco Continental",
            "tipo_cuenta": TipoCuentaBancaria.CAJA_AHORRO,
            "numero_cuenta": "1234567890",
            "activo": True,
        }
        datos.update(cambios)
        return DestinoAcreditacion.objects.create(**datos)

    def test_sin_cliente_activo_redirige_a_home(self):
        self.perfil.cliente_activo = None
        self.perfil.save(update_fields=["cliente_activo"])

        response = self.client.get(reverse("destino-web-list"), HTTP_HOST="127.0.0.1")

        self.assertRedirects(response, reverse("home"))

    def test_listado_muestra_solo_destinos_del_cliente_activo(self):
        self._crear_destino(alias="Propio")
        self._crear_destino(cliente=self.otro_cliente, alias="Ajeno", numero_cuenta="9999999999")

        response = self.client.get(reverse("destino-web-list"), HTTP_HOST="127.0.0.1")

        self.assertContains(response, "Propio")
        self.assertNotContains(response, "Ajeno")

    def test_listado_filtra_por_moneda(self):
        self._crear_destino(alias="EnDolares", moneda=self.usd)
        self._crear_destino(alias="EnEuros", moneda=self.eur, numero_cuenta="5555555555")

        response = self.client.get(
            reverse("destino-web-list"), {"moneda": "EUR"}, HTTP_HOST="127.0.0.1"
        )

        self.assertContains(response, "EnEuros")
        self.assertNotContains(response, "EnDolares")

    def test_crear_destino_lo_asocia_al_cliente_activo_y_audita(self):
        datos = {
            "tipo": TipoDestinoAcreditacion.CUENTA_BANCARIA,
            "alias": "Mi cuenta",
            "moneda": "USD",
            "titular": "Juan Perez",
            "documento_titular": "1234567",
            "banco": "Banco Continental",
            "tipo_cuenta": TipoCuentaBancaria.CAJA_AHORRO,
            "numero_cuenta": "1234567890",
        }

        response = self.client.post(
            reverse("destino-web-create"), datos, HTTP_HOST="127.0.0.1"
        )

        self.assertRedirects(response, reverse("destino-web-list"))
        destino = DestinoAcreditacion.objects.get(alias="Mi cuenta")
        self.assertEqual(destino.cliente, self.cliente)
        self.assertTrue(
            AuditoriaDestinoAcreditacion.objects.filter(
                destino=destino, accion=AccionAuditoriaDestino.CREACION
            ).exists()
        )

    def test_crear_billetera_sin_proveedor_muestra_error(self):
        datos = {
            "tipo": TipoDestinoAcreditacion.BILLETERA_ELECTRONICA,
            "moneda": "USD",
            "titular": "Juan Perez",
            "documento_titular": "1234567",
            "proveedor_billetera": "",
            "numero_billetera": "",
        }

        response = self.client.post(
            reverse("destino-web-create"), datos, HTTP_HOST="127.0.0.1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(DestinoAcreditacion.objects.exists())

    def test_no_puede_editar_destino_de_otro_cliente(self):
        ajeno = self._crear_destino(cliente=self.otro_cliente, numero_cuenta="9999999999")

        response = self.client.get(
            reverse("destino-web-update", args=[ajeno.id_destino]), HTTP_HOST="127.0.0.1"
        )

        self.assertEqual(response.status_code, 404)

    def test_desactivar_destino_registra_auditoria(self):
        destino = self._crear_destino()

        response = self.client.post(
            reverse("destino-web-deactivate", args=[destino.id_destino]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("destino-web-list"))
        destino.refresh_from_db()
        self.assertFalse(destino.activo)
        self.assertTrue(
            AuditoriaDestinoAcreditacion.objects.filter(
                destino=destino, accion=AccionAuditoriaDestino.DESACTIVACION
            ).exists()
        )

    def test_activar_destino_registra_auditoria(self):
        destino = self._crear_destino(activo=False)

        response = self.client.post(
            reverse("destino-web-activate", args=[destino.id_destino]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("destino-web-list"))
        destino.refresh_from_db()
        self.assertTrue(destino.activo)
        self.assertTrue(
            AuditoriaDestinoAcreditacion.objects.filter(
                destino=destino, accion=AccionAuditoriaDestino.ACTIVACION
            ).exists()
        )

    def test_confirmacion_de_eliminacion_se_renderiza(self):
        destino = self._crear_destino(alias="Mi cuenta")

        response = self.client.get(
            reverse("destino-web-delete", args=[destino.id_destino]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "destinos/destino_confirm_delete.html")
        self.assertContains(response, "Banco Continental")

    def test_eliminar_destino_conserva_la_auditoria(self):
        destino = self._crear_destino()

        response = self.client.post(
            reverse("destino-web-delete", args=[destino.id_destino]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("destino-web-list"))
        self.assertFalse(DestinoAcreditacion.objects.filter(pk=destino.pk).exists())
        auditoria = AuditoriaDestinoAcreditacion.objects.get(
            accion=AccionAuditoriaDestino.ELIMINACION
        )
        self.assertIsNone(auditoria.destino_id)
        self.assertEqual(auditoria.datos_anteriores["numero_cuenta"], "1234567890")
