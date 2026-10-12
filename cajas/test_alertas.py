"""Pruebas de HU-32: tolerancia de arqueo y alertas por diferencias."""

from contextlib import ExitStack
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cotizaciones.models import Moneda
from . import alertas
from .alertas import (
    construir_mensaje,
    detectar_excedidos,
    enviar_alerta,
    evaluar_cierre,
    obtener_destinatarios,
)
from .forms import ToleranciasArqueoForm
from .keycloak_service import KeycloakServiceError
from .models import (
    AlertaArqueo,
    AperturaCaja,
    AsignacionCaja,
    Caja,
    DenominacionBillete,
    DetalleInventarioInicial,
    EnvioAlertaArqueo,
    Sucursal,
    ToleranciaArqueo,
)
from .services import cerrar_caja

D = Decimal


class DetectarExcedidosTests(SimpleTestCase):
    """Comparación pura: sin base de datos ni correo."""

    def test_diferencia_bajo_el_limite_no_alerta(self):
        self.assertEqual(
            detectar_excedidos({"USD": D("-5.00")}, {"USD": D("10.00")}), []
        )

    def test_diferencia_igual_al_limite_no_alerta(self):
        self.assertEqual(
            detectar_excedidos({"USD": D("-10.00")}, {"USD": D("10.00")}), []
        )

    def test_faltante_sobre_el_limite_alerta(self):
        self.assertEqual(
            detectar_excedidos({"USD": D("-10.01")}, {"USD": D("10.00")}),
            [{"moneda_id": "USD", "diferencia": D("-10.01"), "tolerancia": D("10.00")}],
        )

    def test_sobrante_sobre_el_limite_alerta(self):
        resultado = detectar_excedidos({"USD": D("10.01")}, {"USD": D("10.00")})
        self.assertEqual(resultado[0]["diferencia"], D("10.01"))

    def test_moneda_sin_tolerancia_usa_cero(self):
        self.assertEqual(len(detectar_excedidos({"EUR": D("0.01")}, {})), 1)
        self.assertEqual(detectar_excedidos({"EUR": D("0.00")}, {}), [])

    def test_varias_monedas_devuelve_solo_las_excedidas_ordenadas(self):
        resultado = detectar_excedidos(
            {"USD": D("-50.00"), "PYG": D("1000.00"), "EUR": D("1.00")},
            {"USD": D("10.00"), "PYG": D("5000.00"), "EUR": D("0.50")},
        )
        self.assertEqual([r["moneda_id"] for r in resultado], ["EUR", "USD"])

    def test_sin_diferencias_devuelve_lista_vacia(self):
        self.assertEqual(detectar_excedidos({}, {"USD": D("1.00")}), [])


class ToleranciaArqueoModeloTests(TestCase):
    def setUp(self):
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"}
        )

    def test_rechaza_negativo_en_validacion(self):
        tolerancia = ToleranciaArqueo(moneda=self.usd, monto_maximo=D("-0.01"))
        with self.assertRaises(ValidationError):
            tolerancia.full_clean()

    def test_acepta_cero(self):
        tolerancia = ToleranciaArqueo(moneda=self.usd, monto_maximo=D("0.00"))
        tolerancia.full_clean()
        tolerancia.save()

    def test_base_de_datos_rechaza_negativo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("-1.00"))

    def test_una_sola_tolerancia_por_moneda(self):
        ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("1.00"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("2.00"))


class ToleranciasArqueoFormTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="admin_user", email="admin@example.com"
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"}
        )

    def _datos(self, valor):
        form = ToleranciasArqueoForm()
        return {form.nombre_campo(m): valor for m in form.monedas}

    def test_monedas_sin_configurar_se_muestran_en_cero(self):
        form = ToleranciasArqueoForm()
        for moneda, campo in form.campos_por_moneda():
            self.assertEqual(campo.initial, D("0.00"))

    def test_rechaza_negativos(self):
        form = ToleranciasArqueoForm(data=self._datos("-1"))
        self.assertFalse(form.is_valid())
        self.assertIn("negativa", str(form.errors))

    def test_guarda_todas_las_monedas_y_quien_modifico(self):
        form = ToleranciasArqueoForm(data=self._datos("25.50"))
        self.assertTrue(form.is_valid(), form.errors)
        form.guardar(self.usuario)

        fila = ToleranciaArqueo.objects.get(moneda=self.usd)
        self.assertEqual(fila.monto_maximo, D("25.50"))
        self.assertEqual(fila.modificado_por, self.usuario)
        self.assertEqual(
            ToleranciaArqueo.objects.count(), len(ToleranciasArqueoForm().monedas)
        )

    def test_actualiza_sin_duplicar(self):
        ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("1.00"))
        form = ToleranciasArqueoForm(data=self._datos("0"))
        self.assertTrue(form.is_valid(), form.errors)
        form.guardar(self.usuario)
        self.assertEqual(ToleranciaArqueo.objects.filter(moneda=self.usd).count(), 1)
        self.assertEqual(ToleranciaArqueo.objects.get(moneda=self.usd).monto_maximo, D("0.00"))


class HiloSincrono:
    """Sustituye a Thread para ejecutar el envío en el mismo hilo del test."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class ArqueoBase(TestCase):
    """Apertura con USD 200 (2 billetes de 100) lista para cerrar."""

    def setUp(self):
        User = get_user_model()
        self.cajero = User.objects.create_user(username="cajero_user", email="cajero@example.com")
        self.admin = User.objects.create_user(username="admin_user", email="admin@example.com")
        self.tesorero = User.objects.create_user(username="tesorero_user", email="tesorero@example.com")
        self.cajero_id = uuid4()

        self.sucursal = Sucursal.objects.create(codigo="SUC-01", nombre="Casa Central")
        self.caja = Caja.objects.create(sucursal=self.sucursal, codigo="CAJA-01", nombre="Caja 1")
        ahora = timezone.now()
        self.asignacion = AsignacionCaja.objects.create(
            caja=self.caja,
            cajero_keycloak_id=self.cajero_id,
            cajero_username="cajero_user",
            turno="Mañana",
            fecha_inicio=ahora - timedelta(hours=2),
            fecha_fin=ahora + timedelta(hours=6),
            asignado_por=self.tesorero,
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"}
        )
        self.b100 = DenominacionBillete.objects.create(moneda=self.usd, valor=D("100.00"))
        self.b50 = DenominacionBillete.objects.create(moneda=self.usd, valor=D("50.00"))
        self.apertura = AperturaCaja.objects.create(
            caja=self.caja,
            asignacion=self.asignacion,
            cajero_keycloak_id=self.cajero_id,
            fecha_apertura=ahora - timedelta(hours=1),
            estado=AperturaCaja.Estado.ABIERTA,
        )
        DetalleInventarioInicial.objects.create(
            apertura=self.apertura,
            denominacion=self.b100,
            moneda_id="USD",
            valor_denominacion=D("100.00"),
            cantidad=2,
        )

    def cerrar(self, cantidad_100, cantidad_50=0):
        """Cierra con el conteo indicado; teórico = 200, físico = lo contado."""
        conteo = [{"denominacion_id": self.b100.pk, "cantidad": cantidad_100}]
        if cantidad_50:
            conteo.append({"denominacion_id": self.b50.pk, "cantidad": cantidad_50})
        return cerrar_caja(
            apertura_id=self.apertura.pk, conteo_billetes=conteo, usuario=self.cajero
        )


class RegistroDeAlertaTests(ArqueoBase):
    """El cierre compara contra la tolerancia y registra la alerta."""

    def setUp(self):
        super().setUp()
        # Evita lanzar hilos reales: el envío se prueba aparte.
        patcher = patch.object(alertas, "_programar_envio")
        self.programar = patcher.start()
        self.addCleanup(patcher.stop)

    def test_arqueo_cuadrado_no_crea_alerta(self):
        cierre = self.cerrar(2)
        self.assertFalse(AlertaArqueo.objects.filter(cierre=cierre).exists())
        self.programar.assert_not_called()

    def test_dentro_de_la_tolerancia_no_crea_alerta(self):
        ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("60.00"))
        self.cerrar(1, 1)  # físico 150, diferencia -50
        self.assertEqual(AlertaArqueo.objects.count(), 0)

    def test_diferencia_igual_al_limite_no_crea_alerta(self):
        ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("50.00"))
        self.cerrar(1, 1)  # diferencia -50
        self.assertEqual(AlertaArqueo.objects.count(), 0)

    def test_sobre_la_tolerancia_crea_alerta_con_detalle_y_copia_del_limite(self):
        ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("10.00"))
        cierre = self.cerrar(1, 1)  # diferencia -50

        alerta = AlertaArqueo.objects.get(cierre=cierre)
        detalle = alerta.detalles.get()
        self.assertEqual(detalle.moneda_id, "USD")
        self.assertEqual(detalle.diferencia, D("-50.00"))
        self.assertEqual(detalle.tolerancia_aplicada, D("10.00"))
        self.assertEqual(detalle.estado_arqueo, "FALTANTE")
        self.programar.assert_called_once_with(alerta.pk)

    def test_moneda_sin_tolerancia_alerta_con_cualquier_diferencia(self):
        cierre = self.cerrar(1, 1)
        alerta = AlertaArqueo.objects.get(cierre=cierre)
        self.assertEqual(alerta.detalles.get().tolerancia_aplicada, D("0.00"))

    def test_cambiar_la_tolerancia_despues_no_altera_alertas_viejas(self):
        tolerancia = ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("10.00"))
        cierre = self.cerrar(1, 1)
        tolerancia.monto_maximo = D("500.00")
        tolerancia.save()

        detalle = AlertaArqueo.objects.get(cierre=cierre).detalles.get()
        self.assertEqual(detalle.tolerancia_aplicada, D("10.00"))

    def test_la_alerta_se_guarda_aunque_el_correo_falle(self):
        # _programar_envio está mockeado: el cierre y la alerta no dependen del correo.
        cierre = self.cerrar(0)
        self.assertTrue(AlertaArqueo.objects.filter(cierre=cierre).exists())
        self.assertEqual(cierre.apertura.estado, AperturaCaja.Estado.CERRADA)

    def test_una_sola_alerta_por_cierre_con_varias_monedas(self):
        eur, _ = Moneda.objects.get_or_create(
            codigo="EUR", defaults={"nombre": "Euro", "simbolo": "€"}
        )
        b_eur = DenominacionBillete.objects.create(moneda=eur, valor=D("10.00"))
        conteo = [
            {"denominacion_id": self.b100.pk, "cantidad": 1},
            {"denominacion_id": b_eur.pk, "cantidad": 3},
        ]
        cierre = cerrar_caja(
            apertura_id=self.apertura.pk, conteo_billetes=conteo, usuario=self.cajero
        )
        alerta = AlertaArqueo.objects.get(cierre=cierre)
        self.assertEqual(AlertaArqueo.objects.count(), 1)
        self.assertEqual(
            sorted(d.moneda_id for d in alerta.detalles.all()), ["EUR", "USD"]
        )


class EnvioProgramadoTests(ArqueoBase):
    def test_el_envio_se_programa_para_despues_del_commit(self):
        with patch.object(alertas, "_enviar_en_segundo_plano") as envio, \
             patch.object(alertas, "Thread", HiloSincrono):
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                cierre = self.cerrar(1, 1)

            # Mientras la transacción no se confirma, nada se envía.
            self.assertEqual(len(callbacks), 1)
            envio.assert_not_called()

            callbacks[0]()  # simula el commit
            alerta = AlertaArqueo.objects.get(cierre=cierre)
            envio.assert_called_once_with(alerta.pk)

    def test_cierre_sin_alerta_no_programa_envio(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.cerrar(2)
        self.assertEqual(callbacks, [])


class DestinatariosTests(SimpleTestCase):
    def _usuarios(self, por_rol):
        def falso(rol):
            return por_rol[rol]
        return patch.object(alertas, "obtener_usuarios_por_rol", side_effect=falso)

    def test_une_administradores_y_tesoreros(self):
        with self._usuarios({
            "administrador": [{"email": "admin@x.com"}],
            "tesorero": [{"email": "tes@x.com"}],
        }):
            self.assertEqual(
                obtener_destinatarios(),
                [
                    {"email": "admin@x.com", "rol": "administrador"},
                    {"email": "tes@x.com", "rol": "tesorero"},
                ],
            )

    def test_elimina_duplicados_por_correo_sin_distinguir_mayusculas(self):
        with self._usuarios({
            "administrador": [{"email": "Jefe@x.com"}],
            "tesorero": [{"email": "jefe@x.com"}, {"email": "otro@x.com"}],
        }):
            correos = [d["email"] for d in obtener_destinatarios()]
        self.assertEqual(correos, ["Jefe@x.com", "otro@x.com"])

    def test_descarta_usuarios_sin_correo(self):
        with self._usuarios({
            "administrador": [{"email": ""}, {"email": None}, {}],
            "tesorero": [{"email": "tes@x.com"}],
        }):
            self.assertEqual([d["email"] for d in obtener_destinatarios()], ["tes@x.com"])

    def test_keycloak_caido_propaga_el_error(self):
        with patch.object(
            alertas, "obtener_usuarios_por_rol", side_effect=KeycloakServiceError("caído")
        ):
            with self.assertRaises(KeycloakServiceError):
                obtener_destinatarios()


@override_settings(NOTIFICACIONES_PAUSA_ENVIO=0)
class EnvioDeAlertaTests(ArqueoBase):
    def setUp(self):
        super().setUp()
        ToleranciaArqueo.objects.create(moneda=self.usd, monto_maximo=D("10.00"))
        with patch.object(alertas, "_programar_envio"):
            self.cierre = self.cerrar(1, 1)  # faltante de 50
        self.alerta = AlertaArqueo.objects.get(cierre=self.cierre)

    def _destinatarios(self):
        return patch.object(
            alertas,
            "obtener_destinatarios",
            return_value=[
                {"email": "admin@x.com", "rol": "administrador"},
                {"email": "tes@x.com", "rol": "tesorero"},
            ],
        )

    def test_envia_un_correo_por_destinatario_y_lo_registra(self):
        with self._destinatarios():
            envios = enviar_alerta(self.alerta.pk)

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            sorted(m.to[0] for m in mail.outbox), ["admin@x.com", "tes@x.com"]
        )
        self.assertEqual({e.estado for e in envios}, {EnvioAlertaArqueo.Estado.ENVIADA})
        self.assertEqual(self.alerta.envios.count(), 2)

    def test_contenido_del_correo(self):
        with self._destinatarios():
            enviar_alerta(self.alerta.pk)
        mensaje = mail.outbox[0]
        self.assertIn("Caja 1", mensaje.subject)
        self.assertIn(f"#{self.cierre.pk}", mensaje.subject)
        for texto in ("Caja 1", "Casa Central", "cajero_user", "USD", "faltante", "límite"):
            self.assertIn(texto, mensaje.body)

    def test_un_solo_correo_por_arqueo_con_todas_las_monedas(self):
        asunto, cuerpo = construir_mensaje(self.alerta)
        self.assertEqual(cuerpo.count("USD"), 1)
        self.assertTrue(asunto)

    def test_fallo_de_smtp_queda_registrado_y_la_alerta_existe(self):
        with self._destinatarios(), \
             patch.object(alertas, "_abrir_conexion", return_value=(MagicMock(), "")), \
             patch.object(alertas, "_enviar", return_value="SMTP rechazó el mensaje"):
            envios = enviar_alerta(self.alerta.pk)

        self.assertEqual({e.estado for e in envios}, {EnvioAlertaArqueo.Estado.FALLIDA})
        self.assertIn("SMTP", envios[0].error)
        self.assertTrue(AlertaArqueo.objects.filter(pk=self.alerta.pk).exists())

    def test_sin_conexion_con_el_servidor_de_correo_todos_fallan(self):
        with self._destinatarios(), \
             patch.object(alertas, "_abrir_conexion", return_value=(None, "sin red")):
            envios = enviar_alerta(self.alerta.pk)
        self.assertEqual(len(envios), 2)
        self.assertTrue(all(e.error == "sin red" for e in envios))

    def test_keycloak_caido_registra_un_envio_fallido(self):
        causa = ValueError("403 Forbidden")
        error = KeycloakServiceError("falló")
        error.__cause__ = causa
        with patch.object(alertas, "obtener_destinatarios", side_effect=error):
            envios = enviar_alerta(self.alerta.pk)

        self.assertEqual(len(envios), 1)
        self.assertEqual(envios[0].estado, EnvioAlertaArqueo.Estado.FALLIDA)
        self.assertIn("403", envios[0].error)
        self.assertEqual(mail.outbox, [])

    def test_sin_destinatarios_registra_un_envio_fallido(self):
        with patch.object(alertas, "obtener_destinatarios", return_value=[]):
            envios = enviar_alerta(self.alerta.pk)
        self.assertEqual(len(envios), 1)
        self.assertEqual(envios[0].estado, EnvioAlertaArqueo.Estado.FALLIDA)

    def test_flujo_completo_cierre_a_correo(self):
        """Cierre con diferencia -> alerta -> correo, con Keycloak simulado."""
        self.apertura2 = None
        # Nueva apertura: se cierra la actual y se abre otra desde la misma asignación.
        AperturaCaja.objects.filter(pk=self.apertura.pk).update(
            estado=AperturaCaja.Estado.CERRADA, fecha_cierre=timezone.now()
        )
        apertura = AperturaCaja.objects.create(
            caja=self.caja,
            asignacion=self.asignacion,
            cajero_keycloak_id=self.cajero_id,
            estado=AperturaCaja.Estado.ABIERTA,
        )
        DetalleInventarioInicial.objects.create(
            apertura=apertura,
            denominacion=self.b100,
            moneda_id="USD",
            valor_denominacion=D("100.00"),
            cantidad=2,
        )
        mail.outbox.clear()

        with patch.object(alertas, "Thread", HiloSincrono), \
             patch.object(alertas, "connection", MagicMock()), \
             patch.object(
                 alertas,
                 "obtener_usuarios_por_rol",
                 side_effect=lambda rol: [{"email": f"{rol}@x.com"}],
             ):
            with self.captureOnCommitCallbacks(execute=True):
                cierre = cerrar_caja(
                    apertura_id=apertura.pk,
                    conteo_billetes=[{"denominacion_id": self.b100.pk, "cantidad": 0}],
                    usuario=self.cajero,
                )

        alerta = AlertaArqueo.objects.get(cierre=cierre)
        self.assertEqual(alerta.detalles.get().diferencia, D("-200.00"))
        self.assertEqual(
            sorted(m.to[0] for m in mail.outbox),
            ["administrador@x.com", "tesorero@x.com"],
        )
        self.assertEqual(alerta.envios.filter(estado="ENVIADA").count(), 2)


class VistasTests(ArqueoBase):
    def _roles(self, roles):
        pila = ExitStack()
        claims = {"realm_access": {"roles": roles}, "sub": str(uuid4())}
        pila.enter_context(patch("core.keycloak.obtener_roles", return_value=roles))
        pila.enter_context(patch("core.context_processors.obtener_roles", return_value=roles))
        pila.enter_context(patch("core.keycloak.obtener_claims_verificados", return_value=claims))
        return pila

    def _cliente(self, usuario):
        client = Client()
        client.force_login(usuario)
        session = client.session
        session["oidc_id_token_expiration"] = (timezone.now() + timedelta(hours=1)).timestamp()
        session.save()
        return client

    def _post_tolerancias(self, valor):
        form = ToleranciasArqueoForm()
        return {form.nombre_campo(m): valor for m in form.monedas}

    def test_administrador_ve_y_guarda_tolerancias(self):
        client = self._cliente(self.admin)
        with self._roles(["administrador"]):
            self.assertEqual(client.get(reverse("tolerancia-arqueo")).status_code, 200)
            respuesta = client.post(
                reverse("tolerancia-arqueo"), self._post_tolerancias("12.50")
            )
        self.assertRedirects(
            respuesta, reverse("tolerancia-arqueo"), fetch_redirect_response=False
        )
        self.assertEqual(
            ToleranciaArqueo.objects.get(moneda=self.usd).monto_maximo, D("12.50")
        )

    def test_valor_negativo_no_se_guarda(self):
        client = self._cliente(self.admin)
        with self._roles(["administrador"]):
            respuesta = client.post(
                reverse("tolerancia-arqueo"), self._post_tolerancias("-5")
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(ToleranciaArqueo.objects.count(), 0)

    def test_tesorero_y_cajero_no_configuran_tolerancias(self):
        for usuario, rol in ((self.tesorero, "tesorero"), (self.cajero, "cajero")):
            client = self._cliente(usuario)
            with self._roles([rol]):
                self.assertEqual(client.get(reverse("tolerancia-arqueo")).status_code, 403)
                self.assertEqual(
                    client.post(reverse("tolerancia-arqueo"), self._post_tolerancias("1")).status_code,
                    403,
                )
        self.assertEqual(ToleranciaArqueo.objects.count(), 0)

    def test_administrador_y_tesorero_consultan_alertas(self):
        with patch.object(alertas, "_programar_envio"):
            cierre = self.cerrar(1, 1)
        alerta = AlertaArqueo.objects.get(cierre=cierre)
        EnvioAlertaArqueo.objects.create(
            alerta=alerta, email="admin@x.com", rol="administrador", estado="ENVIADA"
        )

        for usuario, rol in ((self.admin, "administrador"), (self.tesorero, "tesorero")):
            client = self._cliente(usuario)
            with self._roles([rol]):
                respuesta = client.get(reverse("alerta-arqueo-list"))
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, "Caja 1")
            self.assertContains(respuesta, "admin@x.com")

    def test_cajero_no_consulta_alertas(self):
        client = self._cliente(self.cajero)
        with self._roles(["cajero"]):
            self.assertEqual(client.get(reverse("alerta-arqueo-list")).status_code, 403)
