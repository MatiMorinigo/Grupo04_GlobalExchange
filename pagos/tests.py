from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import CategoriaCliente, Cliente, TipoCliente
from usuarios.models import UsuarioCliente

from .models import AccionAuditoriaMetodoPago, AuditoriaMetodoPago, MetodoPago, TipoMetodoPago

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

TARJETA_VALIDA = "4539578763621486"
TARJETA_VALIDA_ALTERNATIVA = "5555555555554444"


def _crear_cliente(ruc, nombre="Cliente de prueba"):
    return Cliente.objects.create(
        ruc=ruc,
        nombre=nombre,
        categoria=CategoriaCliente.MINORISTA,
        tipo=TipoCliente.FISICA,
        activo=True,
    )


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class MetodoPagoWebViewTests(TestCase):
    """Prueba la gestión web de métodos de pago del cliente activo y su auditoría."""

    def setUp(self):
        self.user = User.objects.create_user(username="clienteuser", password="testpass123")
        self.client.force_login(self.user)

        self.cliente = _crear_cliente("80000001-1", "Cliente Uno")
        self.otro_cliente = _crear_cliente("80000002-2", "Cliente Dos")

        self.perfil = UsuarioCliente.objects.create(usuario=self.user, cliente_activo=self.cliente)

    def _crear_metodo(self, cliente=None, **kwargs):
        datos = {
            "cliente": cliente or self.cliente,
            "tipo": TipoMetodoPago.TARJETA_CREDITO,
            "titular": "Juan Perez",
            "ultimos_cuatro_digitos": "1486",
            "fecha_vencimiento": "12/30",
            "activo": True,
        }
        datos.update(kwargs)
        return MetodoPago.objects.create(**datos)

    def test_sin_cliente_activo_redirige_a_home(self):
        self.perfil.cliente_activo = None
        self.perfil.save(update_fields=["cliente_activo"])

        response = self.client.get(reverse("metodopago-web-list"), HTTP_HOST="127.0.0.1")

        self.assertRedirects(response, reverse("home"))

    def test_list_muestra_solo_metodos_del_cliente_activo(self):
        propio = self._crear_metodo()
        self._crear_metodo(cliente=self.otro_cliente, ultimos_cuatro_digitos="9999")

        response = self.client.get(reverse("metodopago-web-list"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, propio.ultimos_cuatro_digitos)
        self.assertNotContains(response, "9999")

    def test_list_default_filtra_solo_activos(self):
        self._crear_metodo(ultimos_cuatro_digitos="1111", activo=True)
        self._crear_metodo(ultimos_cuatro_digitos="2222", activo=False)

        response = self.client.get(reverse("metodopago-web-list"), HTTP_HOST="127.0.0.1")

        self.assertContains(response, "1111")
        self.assertNotContains(response, "2222")

    def test_create_asocia_cliente_activo_y_registra_auditoria(self):
        response = self.client.post(
            reverse("metodopago-web-create"),
            {
                "tipo": TipoMetodoPago.TARJETA_CREDITO,
                "titular": "Juan Perez",
                "numero_tarjeta": TARJETA_VALIDA,
                "fecha_vencimiento": "12/30",
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("metodopago-web-list"))

        metodo = MetodoPago.objects.get(cliente=self.cliente)
        self.assertEqual(metodo.ultimos_cuatro_digitos, TARJETA_VALIDA[-4:])
        self.assertEqual(metodo.titular, "Juan Perez")

        auditoria = AuditoriaMetodoPago.objects.get(metodo_pago=metodo)
        self.assertEqual(auditoria.accion, AccionAuditoriaMetodoPago.CREACION)
        self.assertEqual(auditoria.realizado_por, self.user)

    def test_create_rechaza_numero_de_tarjeta_invalido(self):
        response = self.client.post(
            reverse("metodopago-web-create"),
            {
                "tipo": TipoMetodoPago.TARJETA_CREDITO,
                "titular": "Juan Perez",
                "numero_tarjeta": "1234567890123456",
                "fecha_vencimiento": "12/30",
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MetodoPago.objects.exists())

    def test_create_rechaza_vencimiento_pasado(self):
        response = self.client.post(
            reverse("metodopago-web-create"),
            {
                "tipo": TipoMetodoPago.TARJETA_CREDITO,
                "titular": "Juan Perez",
                "numero_tarjeta": TARJETA_VALIDA,
                "fecha_vencimiento": "01/20",
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MetodoPago.objects.exists())

    def test_update_permite_modificar_titular_numero_y_vencimiento(self):
        metodo = self._crear_metodo()

        response = self.client.post(
            reverse("metodopago-web-update", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            {
                "tipo": TipoMetodoPago.TARJETA_DEBITO,
                "titular": "Juan Perez Actualizado",
                "numero_tarjeta": TARJETA_VALIDA_ALTERNATIVA,
                "fecha_vencimiento": "11/31",
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("metodopago-web-list"))
        metodo.refresh_from_db()
        self.assertEqual(metodo.titular, "Juan Perez Actualizado")
        self.assertEqual(metodo.ultimos_cuatro_digitos, TARJETA_VALIDA_ALTERNATIVA[-4:])
        self.assertEqual(metodo.fecha_vencimiento, "11/31")

        auditoria = AuditoriaMetodoPago.objects.get(
            metodo_pago=metodo, accion=AccionAuditoriaMetodoPago.MODIFICACION
        )
        self.assertEqual(auditoria.datos_anteriores["titular"], "Juan Perez")

    def test_update_no_permite_cambiar_tipo(self):
        metodo = self._crear_metodo(tipo=TipoMetodoPago.TARJETA_CREDITO)

        self.client.post(
            reverse("metodopago-web-update", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            {
                "tipo": TipoMetodoPago.TARJETA_DEBITO,
                "titular": metodo.titular,
                "numero_tarjeta": "",
                "fecha_vencimiento": metodo.fecha_vencimiento,
            },
            HTTP_HOST="127.0.0.1",
        )

        metodo.refresh_from_db()
        self.assertEqual(metodo.tipo, TipoMetodoPago.TARJETA_CREDITO)

    def test_update_numero_en_blanco_conserva_tarjeta_actual(self):
        metodo = self._crear_metodo(ultimos_cuatro_digitos="1486")

        self.client.post(
            reverse("metodopago-web-update", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            {
                "tipo": metodo.tipo,
                "titular": "Nuevo Titular",
                "numero_tarjeta": "",
                "fecha_vencimiento": metodo.fecha_vencimiento,
            },
            HTTP_HOST="127.0.0.1",
        )

        metodo.refresh_from_db()
        self.assertEqual(metodo.ultimos_cuatro_digitos, "1486")
        self.assertEqual(metodo.titular, "Nuevo Titular")

    def test_update_no_permite_editar_metodo_de_otro_cliente(self):
        metodo_ajeno = self._crear_metodo(cliente=self.otro_cliente)

        response = self.client.post(
            reverse("metodopago-web-update", kwargs={"id_metodo_pago": metodo_ajeno.id_metodo_pago}),
            {
                "tipo": metodo_ajeno.tipo,
                "titular": "Hackeado",
                "numero_tarjeta": "",
                "fecha_vencimiento": metodo_ajeno.fecha_vencimiento,
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)
        metodo_ajeno.refresh_from_db()
        self.assertNotEqual(metodo_ajeno.titular, "Hackeado")

    def test_deactivate_desactiva_y_registra_auditoria(self):
        metodo = self._crear_metodo(activo=True)

        response = self.client.post(
            reverse("metodopago-web-deactivate", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("metodopago-web-list"))
        metodo.refresh_from_db()
        self.assertFalse(metodo.activo)
        self.assertTrue(
            AuditoriaMetodoPago.objects.filter(
                metodo_pago=metodo, accion=AccionAuditoriaMetodoPago.DESACTIVACION
            ).exists()
        )

    def test_deactivate_dos_veces_no_duplica_auditoria(self):
        metodo = self._crear_metodo(activo=False)

        self.client.post(
            reverse("metodopago-web-deactivate", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(
            AuditoriaMetodoPago.objects.filter(
                metodo_pago=metodo, accion=AccionAuditoriaMetodoPago.DESACTIVACION
            ).count(),
            0,
        )

    def test_activate_activa_y_registra_auditoria(self):
        metodo = self._crear_metodo(activo=False)

        response = self.client.post(
            reverse("metodopago-web-activate", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("metodopago-web-list"))
        metodo.refresh_from_db()
        self.assertTrue(metodo.activo)
        self.assertTrue(
            AuditoriaMetodoPago.objects.filter(
                metodo_pago=metodo, accion=AccionAuditoriaMetodoPago.ACTIVACION
            ).exists()
        )

    def test_activate_dos_veces_no_duplica_auditoria(self):
        metodo = self._crear_metodo(activo=True)

        self.client.post(
            reverse("metodopago-web-activate", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(
            AuditoriaMetodoPago.objects.filter(
                metodo_pago=metodo, accion=AccionAuditoriaMetodoPago.ACTIVACION
            ).count(),
            0,
        )

    def test_no_puede_desactivar_metodo_de_otro_cliente(self):
        metodo_ajeno = self._crear_metodo(cliente=self.otro_cliente, activo=True)

        response = self.client.post(
            reverse("metodopago-web-deactivate", kwargs={"id_metodo_pago": metodo_ajeno.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)
        metodo_ajeno.refresh_from_db()
        self.assertTrue(metodo_ajeno.activo)

    def test_delete_confirmacion_muestra_datos_de_la_tarjeta(self):
        metodo = self._crear_metodo()

        response = self.client.get(
            reverse("metodopago-web-delete", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, metodo.ultimos_cuatro_digitos)

    def test_delete_elimina_y_conserva_auditoria_con_fk_nulo(self):
        metodo = self._crear_metodo()
        metodo_id = metodo.id_metodo_pago

        response = self.client.post(
            reverse("metodopago-web-delete", kwargs={"id_metodo_pago": metodo_id}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("metodopago-web-list"))
        self.assertFalse(MetodoPago.objects.filter(id_metodo_pago=metodo_id).exists())

        auditoria = AuditoriaMetodoPago.objects.get(accion=AccionAuditoriaMetodoPago.ELIMINACION)
        self.assertIsNone(auditoria.metodo_pago)
        self.assertEqual(auditoria.datos_anteriores["ultimos_cuatro_digitos"], "1486")

    def test_no_puede_eliminar_metodo_de_otro_cliente(self):
        metodo_ajeno = self._crear_metodo(cliente=self.otro_cliente)

        response = self.client.post(
            reverse("metodopago-web-delete", kwargs={"id_metodo_pago": metodo_ajeno.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(MetodoPago.objects.filter(pk=metodo_ajeno.pk).exists())

    def test_metodos_de_pago_persisten_al_cambiar_cliente_activo(self):
        metodo = self._crear_metodo()

        self.perfil.cliente_activo = self.otro_cliente
        self.perfil.save(update_fields=["cliente_activo"])

        self.assertTrue(MetodoPago.objects.filter(pk=metodo.pk, cliente=self.cliente).exists())

        response = self.client.get(reverse("metodopago-web-list"), HTTP_HOST="127.0.0.1")
        self.assertNotContains(response, metodo.ultimos_cuatro_digitos)


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class MetodoPagoAPITests(TestCase):
    """Prueba los endpoints de API de métodos de pago y su alcance por cliente activo."""

    def setUp(self):
        self.user = User.objects.create_user(username="apiuser", password="testpass123")
        self.client.force_login(self.user)

        self.cliente = _crear_cliente("90000001-1", "Cliente API Uno")
        self.otro_cliente = _crear_cliente("90000002-2", "Cliente API Dos")
        self.perfil = UsuarioCliente.objects.create(usuario=self.user, cliente_activo=self.cliente)

    def _crear_metodo(self, cliente=None, **kwargs):
        datos = {
            "cliente": cliente or self.cliente,
            "tipo": TipoMetodoPago.TARJETA_CREDITO,
            "titular": "Juan Perez",
            "ultimos_cuatro_digitos": "1486",
            "fecha_vencimiento": "12/30",
            "activo": True,
        }
        datos.update(kwargs)
        return MetodoPago.objects.create(**datos)

    def test_list_solo_incluye_metodos_del_cliente_activo(self):
        propio = self._crear_metodo()
        self._crear_metodo(cliente=self.otro_cliente, ultimos_cuatro_digitos="9999")

        response = self.client.get(reverse("metodopago-list-create"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        ids = [item["id_metodo_pago"] for item in response.json()]
        self.assertEqual(ids, [propio.id_metodo_pago])

    def test_create_asigna_cliente_activo_automaticamente(self):
        response = self.client.post(
            reverse("metodopago-list-create"),
            {
                "tipo": TipoMetodoPago.TARJETA_CREDITO,
                "titular": "Juan Perez",
                "numero_tarjeta": TARJETA_VALIDA,
                "fecha_vencimiento": "12/30",
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 201)
        metodo = MetodoPago.objects.get(cliente=self.cliente)
        self.assertEqual(metodo.ultimos_cuatro_digitos, TARJETA_VALIDA[-4:])
        self.assertNotIn("numero_tarjeta", response.json())

    def test_detail_no_permite_acceder_a_metodo_de_otro_cliente(self):
        metodo_ajeno = self._crear_metodo(cliente=self.otro_cliente)

        response = self.client.get(
            reverse("metodopago-detail", kwargs={"id_metodo_pago": metodo_ajeno.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)

    def test_delete_via_api_registra_auditoria_con_fk_nulo(self):
        metodo = self._crear_metodo()
        metodo_id = metodo.id_metodo_pago

        response = self.client.delete(
            reverse("metodopago-detail", kwargs={"id_metodo_pago": metodo_id}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 204)
        auditoria = AuditoriaMetodoPago.objects.get(accion=AccionAuditoriaMetodoPago.ELIMINACION)
        self.assertIsNone(auditoria.metodo_pago)

    def test_desactivar_endpoint_es_idempotente(self):
        metodo = self._crear_metodo(activo=True)

        self.client.post(
            reverse("metodopago-desactivar", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )
        self.client.post(
            reverse("metodopago-desactivar", kwargs={"id_metodo_pago": metodo.id_metodo_pago}),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(
            AuditoriaMetodoPago.objects.filter(
                metodo_pago=metodo, accion=AccionAuditoriaMetodoPago.DESACTIVACION
            ).count(),
            1,
        )
