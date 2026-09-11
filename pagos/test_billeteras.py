from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from usuarios.models import UsuarioCliente

from .forms import MetodoPagoForm
from .models import AccionAuditoriaMetodoPago, AuditoriaMetodoPago, MetodoPago, TipoMetodoPago
from .serializers import MetodoPagoSerializer
from .tests import MIDDLEWARE_SIN_OIDC, TARJETA_VALIDA, _crear_cliente


DATOS_BILLETERA = {
    "tipo": TipoMetodoPago.BILLETERA_ELECTRONICA,
    "titular": "Ana Perez",
    "proveedor_billetera": "Tigo Money",
    "numero_billetera": "0981 123 456",
}


class BilleteraValidacionTests(SimpleTestCase):
    def test_formulario_y_api_exigen_campos_de_billetera(self):
        for campo in ("titular", "proveedor_billetera", "numero_billetera"):
            for valor in (None, "", "   "):
                with self.subTest(campo=campo, valor=valor):
                    datos = dict(DATOS_BILLETERA)
                    if valor is None:
                        datos.pop(campo)
                    else:
                        datos[campo] = valor
                    form = MetodoPagoForm(data=datos)
                    serializer = MetodoPagoSerializer(data=datos)
                    self.assertFalse(form.is_valid())
                    self.assertIn(campo, form.errors)
                    self.assertFalse(serializer.is_valid())
                    self.assertIn(campo, serializer.errors)

    def test_formulario_y_api_rechazan_celulares_invalidos(self):
        for numero in ("abc0981123456", "123", "1234567890123456", "++595981123456"):
            with self.subTest(numero=numero):
                datos = {**DATOS_BILLETERA, "numero_billetera": numero}
                form = MetodoPagoForm(data=datos)
                serializer = MetodoPagoSerializer(data=datos)
                self.assertFalse(form.is_valid())
                self.assertIn("numero_billetera", form.errors)
                self.assertFalse(serializer.is_valid())
                self.assertIn("numero_billetera", serializer.errors)

    def test_celular_se_normaliza_en_formulario_y_api(self):
        datos = {**DATOS_BILLETERA, "numero_billetera": "+595 (981) 123-456"}
        form = MetodoPagoForm(data=datos)
        serializer = MetodoPagoSerializer(data=datos)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save(commit=False).numero_billetera, "+595981123456")
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["numero_billetera"], "+595981123456")

    def test_tarjetas_siguen_exigiendo_numero_y_vencimiento(self):
        for tipo in (TipoMetodoPago.TARJETA_CREDITO, TipoMetodoPago.TARJETA_DEBITO):
            for campo in ("numero_tarjeta", "fecha_vencimiento"):
                with self.subTest(tipo=tipo, campo=campo):
                    datos = {"tipo": tipo, "titular": "Ana Perez", "numero_tarjeta": TARJETA_VALIDA,
                             "fecha_vencimiento": "12/30"}
                    datos.pop(campo)
                    form = MetodoPagoForm(data=datos)
                    serializer = MetodoPagoSerializer(data=datos)
                    self.assertFalse(form.is_valid())
                    self.assertIn(campo, form.errors)
                    self.assertFalse(serializer.is_valid())
                    self.assertIn(campo, serializer.errors)

    def test_billetera_ignora_campos_ocultos_del_formulario(self):
        form = MetodoPagoForm(data={**DATOS_BILLETERA, "numero_tarjeta": "invalido",
                                    "fecha_vencimiento": "01/20"})
        self.assertTrue(form.is_valid(), form.errors)
        metodo = form.save(commit=False)
        self.assertEqual(metodo.ultimos_cuatro_digitos, "")
        self.assertEqual(metodo.fecha_vencimiento, "")


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class BilleteraGestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="billeterauser", password="testpass123")
        self.client.force_login(self.user)
        self.cliente = _crear_cliente("81000001-1")
        UsuarioCliente.objects.create(usuario=self.user, cliente_activo=self.cliente)

    def crear_billetera(self):
        return MetodoPago.objects.create(cliente=self.cliente, **{
            **DATOS_BILLETERA, "numero_billetera": "0981123456",
        })

    def test_formulario_ofrece_billetera(self):
        response = self.client.get(reverse("metodopago-web-create"), HTTP_HOST="127.0.0.1")
        self.assertContains(response, "Billetera electrónica")
        self.assertContains(response, "Proveedor de la billetera")
        self.assertContains(response, "Celular asociado")

    def test_alta_web_guarda_billetera_y_auditoria(self):
        response = self.client.post(reverse("metodopago-web-create"), DATOS_BILLETERA,
                                    HTTP_HOST="127.0.0.1")
        self.assertRedirects(response, reverse("metodopago-web-list"))
        metodo = MetodoPago.objects.get(cliente=self.cliente)
        self.assertEqual(metodo.numero_billetera, "0981123456")
        self.assertEqual(metodo.fecha_vencimiento, "")
        self.assertEqual(metodo.ultimos_cuatro_digitos, "")
        auditoria = AuditoriaMetodoPago.objects.get(metodo_pago=metodo)
        self.assertEqual(auditoria.datos_nuevos["proveedor_billetera"], "Tigo Money")
        self.assertEqual(auditoria.datos_nuevos["numero_billetera"], "0981123456")

    def test_error_web_conserva_tipo_y_datos(self):
        response = self.client.post(reverse("metodopago-web-create"),
                                    {**DATOS_BILLETERA, "numero_billetera": "123"},
                                    HTTP_HOST="127.0.0.1")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].es_billetera)
        self.assertContains(response, 'value="Tigo Money"')
        self.assertFalse(MetodoPago.objects.exists())

    def test_edicion_web_conserva_tipo_y_audita_celular_anterior(self):
        metodo = self.crear_billetera()
        url = reverse("metodopago-web-update", args=[metodo.pk])
        response = self.client.get(url, HTTP_HOST="127.0.0.1")
        self.assertTrue(response.context["form"].es_billetera)
        self.assertTrue(response.context["form"].fields["tipo"].disabled)
        response = self.client.post(url, {**DATOS_BILLETERA, "tipo": TipoMetodoPago.TARJETA_CREDITO,
                                         "numero_billetera": "0982123456"}, HTTP_HOST="127.0.0.1")
        self.assertRedirects(response, reverse("metodopago-web-list"))
        metodo.refresh_from_db()
        self.assertEqual(metodo.tipo, TipoMetodoPago.BILLETERA_ELECTRONICA)
        self.assertEqual(metodo.numero_billetera, "0982123456")
        auditoria = AuditoriaMetodoPago.objects.get(metodo_pago=metodo)
        self.assertEqual(auditoria.datos_anteriores["numero_billetera"], "0981123456")
        self.assertEqual(auditoria.datos_nuevos["numero_billetera"], "0982123456")

    def test_listado_y_confirmacion_identifican_billetera(self):
        metodo = self.crear_billetera()
        for url in (reverse("metodopago-web-list"), reverse("metodopago-web-delete", args=[metodo.pk])):
            response = self.client.get(url, HTTP_HOST="127.0.0.1")
            self.assertContains(response, "Tigo Money")
            self.assertContains(response, "0981123456")
        self.assertIn("Tigo Money", str(metodo))

    def test_eliminacion_web_conserva_datos_billetera_en_auditoria(self):
        metodo = self.crear_billetera()
        response = self.client.post(reverse("metodopago-web-delete", args=[metodo.pk]),
                                    HTTP_HOST="127.0.0.1")
        self.assertRedirects(response, reverse("metodopago-web-list"))
        auditoria = AuditoriaMetodoPago.objects.get(accion=AccionAuditoriaMetodoPago.ELIMINACION)
        self.assertIsNone(auditoria.metodo_pago)
        self.assertEqual(auditoria.datos_anteriores["numero_billetera"], "0981123456")

    def test_api_crea_billetera_sin_tarjeta(self):
        response = self.client.post(reverse("metodopago-list-create"), DATOS_BILLETERA,
                                    HTTP_HOST="127.0.0.1")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["numero_billetera"], "0981123456")
        metodo = MetodoPago.objects.get(cliente=self.cliente)
        self.assertEqual(metodo.fecha_vencimiento, "")
        auditoria = AuditoriaMetodoPago.objects.get(metodo_pago=metodo)
        self.assertEqual(auditoria.datos_nuevos["numero_billetera"], "0981123456")

    def test_api_patch_conserva_tipo_y_campos_omitidos(self):
        metodo = self.crear_billetera()
        response = self.client.patch(reverse("metodopago-detail", args=[metodo.pk]),
                                     {"tipo": TipoMetodoPago.TARJETA_DEBITO, "titular": "Ana Actualizada"},
                                     content_type="application/json", HTTP_HOST="127.0.0.1")
        self.assertEqual(response.status_code, 200, response.content)
        metodo.refresh_from_db()
        self.assertEqual(metodo.tipo, TipoMetodoPago.BILLETERA_ELECTRONICA)
        self.assertEqual(metodo.numero_billetera, "0981123456")
        self.assertEqual(metodo.titular, "Ana Actualizada")

    def test_api_patch_no_permite_vaciar_campos_obligatorios(self):
        metodo = self.crear_billetera()
        for campo in ("proveedor_billetera", "numero_billetera"):
            response = self.client.patch(reverse("metodopago-detail", args=[metodo.pk]), {campo: ""},
                                         content_type="application/json", HTTP_HOST="127.0.0.1")
            self.assertEqual(response.status_code, 400)
            self.assertIn(campo, response.json())

    def test_otro_cliente_no_puede_editar_billetera(self):
        metodo = self.crear_billetera()
        metodo.cliente = _crear_cliente("81000002-2")
        metodo.save()
        for nombre in ("metodopago-web-update", "metodopago-detail"):
            response = self.client.get(reverse(nombre, args=[metodo.pk]), HTTP_HOST="127.0.0.1")
            self.assertEqual(response.status_code, 404)
