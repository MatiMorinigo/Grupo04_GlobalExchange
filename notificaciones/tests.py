from decimal import Decimal
from smtplib import SMTPException
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from cotizaciones.admin import TasaCambioAdmin
from cotizaciones.models import Moneda, TasaCambio

from .models import EstadoNotificacion, Notificacion
from .services import notificar_al_confirmar, notificar_cambio_tasa

MIDDLEWARE_SIN_OIDC = [m for m in settings.MIDDLEWARE if "oidc" not in m]
PERMISO_ANALISTA = "core.mixins.AnalistaCambiarioRequiredMixin.test_func"
CONEXION = "notificaciones.services.get_connection"
LOGGER = "notificaciones.services"


class HiloEnLinea:
    """Reemplaza a Thread para ejecutar la notificación dentro de la prueba."""

    def __init__(self, target, args, daemon):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class TasaBaseTestCase(TestCase):
    """Prepara una tasa USD/PYG vigente y un usuario activo con correo."""

    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )
        self.tasa = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7250.0000"),
            precio_venta=Decimal("7400.0000"),
        )
        self.usuario = User.objects.create_user(username="ana", email="ana@example.com")


class NotificarCambioTasaTests(TasaBaseTestCase):
    """Prueba el envío y el registro de las notificaciones de tasas."""

    def test_envia_moneda_y_nuevos_valores_y_registra_la_notificacion(self):
        notificar_cambio_tasa(self.tasa)

        correo = mail.outbox[0]
        self.assertEqual(correo.to, ["ana@example.com"])
        self.assertIn("USD/PYG", correo.subject)
        self.assertIn(self.usd.nombre, correo.body)
        self.assertIn("Compra: Gs 7.250", correo.body)
        self.assertIn("Venta: Gs 7.400", correo.body)

        notificacion = Notificacion.objects.get()
        self.assertEqual(notificacion.usuario, self.usuario)
        self.assertEqual(notificacion.tasa, self.tasa)
        self.assertEqual(notificacion.email, "ana@example.com")
        self.assertEqual(notificacion.precio_compra, Decimal("7250.0000"))
        self.assertEqual(notificacion.precio_venta, Decimal("7400.0000"))
        self.assertEqual(notificacion.estado, EstadoNotificacion.ENVIADA)
        self.assertEqual(notificacion.error, "")

    def test_excluye_usuarios_inactivos_y_sin_correo(self):
        User.objects.create_user(username="inactivo", email="inactivo@example.com", is_active=False)
        User.objects.create_user(username="sin_correo")

        notificar_cambio_tasa(self.tasa)

        self.assertEqual([correo.to for correo in mail.outbox], [["ana@example.com"]])
        self.assertEqual(Notificacion.objects.count(), 1)

    @override_settings(NOTIFICACIONES_PAUSA_ENVIO=2)
    def test_espera_la_pausa_configurada_entre_correos(self):
        User.objects.create_user(username="luis", email="luis@example.com")

        with patch("notificaciones.services.time.sleep") as sleep:
            notificar_cambio_tasa(self.tasa)

        sleep.assert_called_once_with(2)
        self.assertEqual(len(mail.outbox), 2)

    def test_sin_destinatarios_no_abre_conexion(self):
        self.usuario.delete()

        with patch(CONEXION) as get_connection:
            notificaciones = notificar_cambio_tasa(self.tasa)

        self.assertEqual(notificaciones, [])
        get_connection.assert_not_called()

    def test_fallo_de_conexion_registra_todas_como_fallidas(self):
        User.objects.create_user(username="luis", email="luis@example.com")

        with patch(CONEXION) as get_connection, self.assertLogs(LOGGER, level="ERROR"):
            get_connection.return_value.open.side_effect = OSError("servidor caído")
            notificar_cambio_tasa(self.tasa)

        self.assertEqual(mail.outbox, [])
        self.assertEqual(
            list(Notificacion.objects.values_list("estado", "error")),
            [(EstadoNotificacion.FALLIDA, "servidor caído")] * 2,
        )

    def test_fallo_de_un_destinatario_no_interrumpe_los_demas(self):
        User.objects.create_user(username="luis", email="luis@example.com")

        with patch(
            "notificaciones.services.EmailMessage.send",
            side_effect=[SMTPException("buzón rechazado"), 1],
        ), self.assertLogs(LOGGER, level="ERROR"):
            notificar_cambio_tasa(self.tasa)

        self.assertEqual(
            sorted(Notificacion.objects.values_list("estado", flat=True)),
            [EstadoNotificacion.ENVIADA, EstadoNotificacion.FALLIDA],
        )


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class PublicacionTasaNotificaTests(TasaBaseTestCase):
    """Prueba que publicar una tasa desde las vistas o el admin notifica."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario)
        # El hilo real usaría otra conexión y no vería los datos de la prueba.
        hilo_en_linea = patch.multiple("notificaciones.services", Thread=HiloEnLinea, connection=Mock())
        hilo_en_linea.start()
        self.addCleanup(hilo_en_linea.stop)

    def _editar(self, **extra):
        with patch(PERMISO_ANALISTA, return_value=True), self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("tasa-web-editar", kwargs={"id_tasa": self.tasa.id_tasa}),
                {"precio_compra": "7300.0000", "precio_venta": "7450.0000", **extra},
                HTTP_HOST="127.0.0.1",
            )

    def test_editar_tasa_confirmada_notifica_los_nuevos_valores(self):
        self._editar(confirmado="True")

        notificacion = Notificacion.objects.get()
        self.assertEqual(notificacion.tasa, TasaCambio.objects.get(vigente=True))
        self.assertEqual(notificacion.precio_compra, Decimal("7300.0000"))
        self.assertIn("Compra: Gs 7.300", mail.outbox[0].body)

    def test_editar_tasa_sin_confirmar_no_notifica(self):
        self._editar()

        self.assertEqual(mail.outbox, [])
        self.assertFalse(Notificacion.objects.exists())

    def test_crear_tasa_inicial_notifica(self):
        eur, _ = Moneda.objects.get_or_create(codigo="EUR", defaults={"nombre": "Euro", "simbolo": "€"})

        with patch(PERMISO_ANALISTA, return_value=True), self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("tasa-web-crear"),
                {"moneda_origen": "EUR", "precio_compra": "8000.0000", "precio_venta": "8200.0000"},
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(Notificacion.objects.get().tasa.moneda_origen, eur)
        self.assertIn("EUR/PYG", mail.outbox[0].subject)

    def test_error_de_envio_no_revierte_la_tasa(self):
        with patch(CONEXION) as get_connection, self.assertLogs(LOGGER, level="ERROR"):
            get_connection.return_value.open.side_effect = SMTPException("credenciales inválidas")
            response = self._editar(confirmado="True")

        self.assertRedirects(response, reverse("cotizacion-web-list"), fetch_redirect_response=False)
        self.assertEqual(TasaCambio.objects.get(vigente=True).precio_compra, Decimal("7300.0000"))
        self.assertEqual(Notificacion.objects.get().estado, EstadoNotificacion.FALLIDA)

    def test_error_inesperado_no_interrumpe_la_respuesta(self):
        with patch("notificaciones.services.render_to_string", side_effect=RuntimeError("bug")):
            with self.assertLogs(LOGGER, level="ERROR"):
                response = self._editar(confirmado="True")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TasaCambio.objects.get(vigente=True).precio_compra, Decimal("7300.0000"))

    def test_el_envio_se_lanza_en_un_hilo_despues_del_commit(self):
        with patch("notificaciones.services.Thread") as hilo:
            with self.captureOnCommitCallbacks(execute=True):
                notificar_al_confirmar(self.tasa)
                hilo.return_value.start.assert_not_called()

        hilo.return_value.start.assert_called_once_with()
        self.assertEqual(mail.outbox, [])

    def test_admin_notifica_solo_si_cambian_los_valores_publicados(self):
        tasa_admin = TasaCambioAdmin(TasaCambio, admin.site)

        for campos_modificados, correos_esperados in ((["modificado_por"], 0), (["precio_venta"], 1)):
            with self.subTest(campos_modificados=campos_modificados):
                with self.captureOnCommitCallbacks(execute=True):
                    tasa_admin.save_model(
                        request=None,
                        obj=self.tasa,
                        form=Mock(changed_data=campos_modificados),
                        change=True,
                    )

                self.assertEqual(len(mail.outbox), correos_esperados)
