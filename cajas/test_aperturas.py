"""HU-34: negocio, vistas, identidad OIDC e integridad real en PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.keycloak import obtener_claims_verificados, obtener_roles
from cotizaciones.models import Moneda
from .models import AperturaCaja, AsignacionCaja, Caja, DenominacionBillete, DetalleInventarioInicial, Sucursal
from .services import AperturaCajaError, abrir_caja, apertura_para_movimiento, obtener_apertura_activa


class AperturaFixture:
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_user(username="cajero_apertura")
        self.cajero_id = uuid4()
        self.claims = {"sub": str(self.cajero_id), "realm_access": {"roles": ["cajero"]}}
        for target in ("cajas.services.obtener_claims_verificados", "core.keycloak.obtener_claims_verificados"):
            mock = patch(target, return_value=self.claims)
            mock.start()
            self.addCleanup(mock.stop)
        self.sucursal = Sucursal.objects.create(codigo="AP-SUC", nombre="Central")
        self.caja = Caja.objects.create(sucursal=self.sucursal, codigo="AP-CAJA", nombre="Principal")
        self.ahora = timezone.now()
        self.asignacion = AsignacionCaja.objects.create(
            caja=self.caja, cajero_keycloak_id=self.cajero_id, cajero_username="nombre_antiguo",
            turno="Diurno", fecha_inicio=self.ahora - timedelta(hours=1),
            fecha_fin=self.ahora + timedelta(hours=1), asignado_por=self.usuario,
        )
        self.usd, _ = Moneda.objects.get_or_create(codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"})
        self.pyg, _ = Moneda.objects.get_or_create(codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"})
        self.billete = DenominacionBillete.objects.create(moneda=self.usd, valor=Decimal("20.00"))
        self.otro_billete = DenominacionBillete.objects.create(moneda=self.pyg, valor=Decimal("10000.00"))
        self.inventario = [{"denominacion_id": self.billete.pk, "cantidad": 3}]
        self.request = RequestFactory().post("/")
        self.request.user = self.usuario
        self.request.session = {}

    def abrir(self, inventario=None):
        return abrir_caja(
            request=self.request, asignacion_id=self.asignacion.pk,
            inventario=self.inventario if inventario is None else inventario,
        )


class AperturaServicioTests(AperturaFixture, TestCase):
    def test_apertura_valida_registra_identidad_hora_real_y_saldos_separados(self):
        denominacion = DenominacionBillete.objects.create(moneda=self.usd, valor=Decimal("0.50"))
        inventario = self.inventario + [
            {"denominacion_id": self.otro_billete.pk, "cantidad": 2},
            {"denominacion_id": denominacion.pk, "cantidad": 3},
        ]
        with patch("cajas.services.timezone.now", return_value=self.ahora):
            apertura = self.abrir(inventario)
        self.assertEqual(apertura.saldos_iniciales, {"USD": Decimal("61.50"), "PYG": Decimal("20000.00")})
        self.assertEqual(apertura.cajero_keycloak_id, self.cajero_id)
        self.assertEqual(apertura.fecha_apertura, self.ahora)
        self.assertNotEqual(apertura.fecha_apertura, self.asignacion.fecha_inicio)
        self.assertEqual(apertura.asignacion, self.asignacion)
        self.assertIsNone(apertura.fecha_cierre)

    def test_rechaza_cajero_no_asignado(self):
        self.claims["sub"] = str(uuid4())
        with self.assertRaisesMessage(AperturaCajaError, "No está asignado"):
            self.abrir()
        self.assertFalse(AperturaCaja.objects.exists())

    def test_exige_rol_cajero_incluso_para_administrador(self):
        for roles in ([], ["administrador"], ["tesorero"], "cajero"):
            with self.subTest(roles=roles):
                self.claims["realm_access"]["roles"] = roles
                with self.assertRaises(PermissionDenied):
                    self.abrir()

    def test_exige_sub_uuid_valido(self):
        for sub in (None, "", "nombre", 123):
            with self.subTest(sub=sub):
                self.claims["sub"] = sub
                with self.assertRaises(PermissionDenied):
                    self.abrir()

    def test_turno_excluye_instante_final_y_antes_del_inicio(self):
        for fecha in (self.asignacion.fecha_inicio - timedelta(seconds=1), self.asignacion.fecha_fin):
            with self.subTest(fecha=fecha), patch("cajas.services.timezone.now", return_value=fecha):
                with self.assertRaisesMessage(AperturaCajaError, "no está vigente"):
                    self.abrir()
        self.assertFalse(AperturaCaja.objects.exists())

    def test_turno_incluye_instante_inicial(self):
        with patch("cajas.services.timezone.now", return_value=self.asignacion.fecha_inicio):
            self.assertIsNotNone(self.abrir().pk)

    def test_rechaza_caja_y_sucursal_deshabilitadas(self):
        for objeto in (self.caja, self.sucursal):
            with self.subTest(modelo=type(objeto).__name__):
                objeto.activa = False
                objeto.save()
                with self.assertRaisesMessage(AperturaCajaError, "deben estar activas"):
                    self.abrir()
                objeto.activa = True
                objeto.save()

    def test_rechaza_segunda_apertura_activa(self):
        self.abrir()
        with self.assertRaisesMessage(AperturaCajaError, "ya tiene una apertura"):
            self.abrir()
        self.assertEqual(AperturaCaja.objects.count(), 1)

    def test_cantidades_cero_son_validas(self):
        apertura = self.abrir([{"denominacion_id": self.billete.pk, "cantidad": 0}])
        self.assertEqual(apertura.saldos_iniciales, {"USD": Decimal("0.00")})

    def test_rechaza_cantidades_invalidas(self):
        for cantidad in (-1, 1.5, "3", True, None, 2147483648):
            with self.subTest(cantidad=cantidad), self.assertRaises(AperturaCajaError):
                self.abrir([{"denominacion_id": self.billete.pk, "cantidad": cantidad}])
        self.assertFalse(AperturaCaja.objects.exists())

    def test_rechaza_inventarios_inconsistentes(self):
        for inventario in ([], self.inventario * 2, self.inventario * 101,
                           [{"cantidad": 1}], [{"denominacion_id": 999999, "cantidad": 1}], [None]):
            with self.subTest(inventario=inventario), self.assertRaises(AperturaCajaError):
                self.abrir(inventario)
        self.assertFalse(AperturaCaja.objects.exists())

    def test_rechaza_moneda_o_denominacion_inactiva(self):
        for objeto in (self.usd, self.billete):
            with self.subTest(modelo=type(objeto).__name__):
                objeto.activa = False
                objeto.save()
                with self.assertRaises(AperturaCajaError):
                    self.abrir()
                objeto.activa = True
                objeto.save()

    def test_rollback_si_falla_segundo_detalle(self):
        original = DetalleInventarioInicial.save
        def guardar(detalle, *args, **kwargs):
            if detalle.denominacion_id == self.otro_billete.pk:
                self.assertEqual(DetalleInventarioInicial.objects.count(), 1)
                raise IntegrityError("Error simulado de persistencia")
            return original(detalle, *args, **kwargs)
        with patch.object(DetalleInventarioInicial, "save", guardar), self.assertRaises(IntegrityError):
            self.abrir(self.inventario + [{"denominacion_id": self.otro_billete.pk, "cantidad": 4}])
        self.assertFalse(AperturaCaja.objects.exists())
        self.assertFalse(DetalleInventarioInicial.objects.exists())

    def test_conflicto_bd_esperado_se_traduce_a_error_de_negocio(self):
        causa = Exception("unique violation")
        causa.diag = SimpleNamespace(constraint_name="caja_apertura_activa_unica")
        error = IntegrityError("conflicto")
        error.__cause__ = causa
        with patch.object(AperturaCaja.objects, "create", side_effect=error):
            with self.assertRaisesMessage(AperturaCajaError, "ya tiene una apertura activa"):
                self.abrir()

    def test_historial_no_cambia_al_editar_catalogo(self):
        apertura = self.abrir()
        self.billete.valor = Decimal("50.00")
        self.billete.moneda = self.pyg
        self.billete.save()
        self.assertEqual(apertura.saldos_iniciales, {"USD": Decimal("60.00")})

    def test_movimiento_sin_apertura_es_rechazado(self):
        with self.assertRaises(AperturaCajaError):
            obtener_apertura_activa(self.caja.pk)
        with self.assertRaises(AperturaCajaError), apertura_para_movimiento(self.caja.pk):
            self.fail("No debe entrar al bloque del movimiento")

    def test_turno_vencido_no_cierra_apertura(self):
        apertura = self.abrir()
        with patch("cajas.services.timezone.now", return_value=self.asignacion.fecha_fin + timedelta(days=1)):
            self.assertEqual(obtener_apertura_activa(self.caja.pk), apertura)
            with apertura_para_movimiento(self.caja.pk) as activa:
                self.assertEqual(activa, apertura)
                self.assertTrue(connection.in_atomic_block)

    def test_cierre_preparado_y_reapertura(self):
        apertura = self.abrir()
        apertura.estado = AperturaCaja.Estado.CERRADA
        apertura.fecha_cierre = timezone.now()
        apertura.save()
        with self.assertRaises(AperturaCajaError):
            obtener_apertura_activa(self.caja.pk)
        self.assertNotEqual(self.abrir().pk, apertura.pk)

    def test_bd_impide_apertura_duplicada_sin_full_clean(self):
        self.abrir()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AperturaCaja.objects.create(caja=self.caja, asignacion=self.asignacion, cajero_keycloak_id=self.cajero_id)

    def test_bd_exige_cierre_coherente(self):
        apertura = self.abrir()
        for campos in ({"estado": "OTRO"}, {"estado": "CERRADA"},
                       {"fecha_cierre": timezone.now()},
                       {"estado": "CERRADA", "fecha_cierre": self.ahora - timedelta(days=1)}):
            with self.subTest(campos=campos), self.assertRaises(IntegrityError), transaction.atomic():
                AperturaCaja.objects.filter(pk=apertura.pk).update(**campos)

    def test_bd_impide_denominacion_invalida_o_duplicada(self):
        for valor in (Decimal("0"), Decimal("-1"), self.billete.valor):
            with self.subTest(valor=valor), self.assertRaises(IntegrityError), transaction.atomic():
                DenominacionBillete.objects.create(moneda=self.usd, valor=valor)

    def test_bd_impide_detalles_negativos_y_duplicados(self):
        apertura = self.abrir()
        detalle = apertura.detalles_inventario.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DetalleInventarioInicial.objects.filter(pk=detalle.pk).update(cantidad=-1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DetalleInventarioInicial.objects.filter(pk=detalle.pk).update(valor_denominacion=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            detalle.pk = None
            detalle.save()

    def test_modelo_valida_correspondencia_con_asignacion(self):
        apertura = AperturaCaja(caja=self.caja, asignacion=self.asignacion, cajero_keycloak_id=uuid4())
        with self.assertRaises(ValidationError):
            apertura.full_clean()


class AperturaWebTests(AperturaFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario)
        session = self.client.session
        session["oidc_id_token_expiration"] = (timezone.now() + timedelta(hours=1)).timestamp()
        session.save()
        self.url = reverse("apertura-create", args=[self.asignacion.pk])
        self.datos = {
            "inventario-TOTAL_FORMS": "1", "inventario-INITIAL_FORMS": "0",
            "inventario-0-moneda": "USD", "inventario-0-denominacion": str(self.billete.pk),
            "inventario-0-cantidad": "3",
        }

    def test_lista_formulario_y_resumen(self):
        respuesta = self.client.get(reverse("apertura-list"))
        self.assertContains(respuesta, self.caja.nombre)
        self.assertContains(respuesta, self.url)
        self.assertEqual(respuesta.context["active_submenu"], "aperturas")
        self.assertContains(respuesta, "Apertura de caja")
        self.assertContains(self.client.get(self.url), 'id="agregar-linea"')
        respuesta = self.client.post(self.url, self.datos)
        apertura = AperturaCaja.objects.get()
        self.assertRedirects(respuesta, reverse("apertura-detail", args=[apertura.pk]))
        resumen = self.client.get(respuesta.url)
        self.assertContains(resumen, str(self.cajero_id))
        self.assertEqual(resumen.context["apertura"].saldos_iniciales, {"USD": Decimal("60.00")})
        self.assertContains(resumen, "<td>60</td>", html=True)
        lista = self.client.get(reverse("apertura-list"))
        self.assertContains(lista, "Apertura activa")
        self.assertNotContains(lista, self.url)

    def test_ignora_identidad_fecha_y_totales_del_cliente(self):
        self.datos.update(cajero_keycloak_id=str(uuid4()), fecha_apertura="2000-01-01",
                          saldo_inicial="99999", caja="99999", estado="CERRADA")
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 302)
        apertura = AperturaCaja.objects.get()
        self.assertEqual(apertura.cajero_keycloak_id, self.cajero_id)
        self.assertEqual(apertura.caja, self.caja)
        self.assertGreaterEqual(apertura.fecha_apertura, self.ahora)
        self.assertEqual(apertura.saldos_iniciales, {"USD": Decimal("60.00")})

    def test_rechaza_moneda_inconsistente_cantidad_negativa_y_denominacion_inexistente(self):
        for campo, valor in (("moneda", "PYG"), ("cantidad", "-1"),
                             ("cantidad", "1.5"), ("denominacion", "999999")):
            with self.subTest(campo=campo, valor=valor):
                datos = {**self.datos, f"inventario-0-{campo}": valor}
                respuesta = self.client.post(self.url, datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertFalse(respuesta.context["formset"].is_valid())
                self.assertFalse(AperturaCaja.objects.exists())

    def test_formset_rechaza_duplicados_vacio_y_management_alterado(self):
        duplicados = {**self.datos, "inventario-TOTAL_FORMS": "2",
                      "inventario-1-moneda": "USD", "inventario-1-denominacion": str(self.billete.pk),
                      "inventario-1-cantidad": "0"}
        for datos in (duplicados, {}, {**self.datos, "inventario-TOTAL_FORMS": "101"},
                      {**self.datos, "inventario-0-DELETE": "on"}):
            with self.subTest(datos=datos):
                respuesta = self.client.post(self.url, datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertFalse(respuesta.context["formset"].is_valid())
        self.assertFalse(AperturaCaja.objects.exists())

    def test_varias_lineas_y_omitir_linea_invalida(self):
        datos = {**self.datos, "inventario-TOTAL_FORMS": "3", "inventario-1-moneda": "PYG",
                 "inventario-1-denominacion": str(self.otro_billete.pk), "inventario-1-cantidad": "0",
                 "inventario-2-cantidad": "-1", "inventario-2-DELETE": "on"}
        self.assertEqual(self.client.post(self.url, datos).status_code, 302)
        self.assertEqual(AperturaCaja.objects.get().saldos_iniciales, {"USD": Decimal("60.00"), "PYG": Decimal("0.00")})

    def test_conflicto_de_apertura_muestra_error_sin_500(self):
        self.abrir()
        self.assertContains(self.client.post(self.url, self.datos), "ya tiene una apertura activa")

    def test_turno_vencido_muestra_error_y_conserva_resumen(self):
        apertura = self.abrir()
        with patch("cajas.services.timezone.now", return_value=self.asignacion.fecha_fin):
            respuesta = self.client.get(reverse("apertura-list"))
            self.assertEqual(len(respuesta.context["asignaciones"]), 0)
            self.assertContains(respuesta, reverse("apertura-detail", args=[apertura.pk]))
        apertura.estado = "CERRADA"
        apertura.fecha_cierre = timezone.now()
        apertura.save()
        with patch("cajas.services.timezone.now", return_value=self.asignacion.fecha_fin):
            self.assertContains(self.client.post(self.url, self.datos), "no está vigente")

    def test_permisos_en_todas_las_vistas(self):
        apertura = self.abrir()
        urls = (reverse("apertura-list"), self.url, reverse("apertura-detail", args=[apertura.pk]))
        for rol in ("usuario", "tesorero", "administrador"):
            self.claims["realm_access"]["roles"] = [rol]
            for url in urls:
                for metodo in (self.client.get, self.client.post):
                    with self.subTest(rol=rol, url=url, metodo=metodo.__name__):
                        self.assertEqual(metodo(url).status_code, 403)
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url).status_code, 302)

    def test_otro_cajero_no_puede_ver_ni_abrir_asignacion_ajena(self):
        apertura = self.abrir()
        self.claims["sub"] = str(uuid4())
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 404)
        self.assertEqual(self.client.get(reverse("apertura-detail", args=[apertura.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("apertura-list")), self.caja.nombre)

    def test_csrf_obligatorio(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(self.url, self.datos).status_code, 403)


@skipUnless(connection.vendor == "postgresql", "Requiere restricciones y bloqueos reales de PostgreSQL")
class AperturaConcurrenciaTests(AperturaFixture, TransactionTestCase):
    def ejecutar_en_paralelo(self, operacion):
        barrera = Barrier(2)
        def tarea(_):
            try:
                barrera.wait(timeout=10)
                return operacion()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(tarea, range(2)))
        self.assertCountEqual(resultados, ["creada", "rechazada"])
        self.assertEqual(AperturaCaja.objects.count(), 1)

    def test_indice_unico_impide_inserciones_concurrentes_sin_servicio(self):
        def insertar():
            try:
                with transaction.atomic():
                    AperturaCaja.objects.create(
                        caja_id=self.caja.pk, asignacion_id=self.asignacion.pk,
                        cajero_keycloak_id=self.cajero_id,
                    )
                return "creada"
            except IntegrityError as error:
                self.assertEqual(error.__cause__.diag.constraint_name, "caja_apertura_activa_unica")
                return "rechazada"
        self.ejecutar_en_paralelo(insertar)

    def test_servicio_serializa_aperturas_y_conserva_inventario_completo(self):
        def insertar():
            try:
                self.abrir()
                return "creada"
            except AperturaCajaError:
                return "rechazada"
        self.ejecutar_en_paralelo(insertar)
        self.assertEqual(DetalleInventarioInicial.objects.count(), 1)


@override_settings(
    OIDC_RP_CLIENT_ID="global-exchange",
    OIDC_OP_AUTHORIZATION_ENDPOINT="https://keycloak.test/realms/ge/protocol/openid-connect/auth",
    OIDC_OP_JWKS_ENDPOINT="https://keycloak.test/realms/ge/protocol/openid-connect/certs",
)
class IdentidadOIDCTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.payload = {"sub": str(uuid4()), "iss": "https://keycloak.test/realms/ge",
                        "azp": "global-exchange", "exp": timezone.now() + timedelta(minutes=5),
                        "realm_access": {"roles": ["cajero"]}}
        mock = patch("core.keycloak.jwt.PyJWKClient")
        self.jwks = mock.start()
        self.addCleanup(mock.stop)
        self.jwks.return_value.get_signing_key_from_jwt.return_value.key = self.clave.public_key()

    def request(self, payload=None, clave=None):
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_authenticated=True)
        request.session = {"oidc_access_token": jwt.encode(
            self.payload if payload is None else payload, clave or self.clave, algorithm="RS256"
        )}
        return request

    def test_verifica_firma_sub_rol_y_reutiliza_claims_en_la_solicitud(self):
        request = self.request()
        self.assertEqual(obtener_claims_verificados(request)["sub"], self.payload["sub"])
        self.assertEqual(obtener_roles(request), ["cajero"])
        self.jwks.return_value.get_signing_key_from_jwt.assert_called_once()

    def test_rechaza_token_vencido_emisor_cliente_y_firma_invalidos(self):
        for cambios in ({"exp": timezone.now() - timedelta(minutes=1)},
                        {"iss": "https://otro.test"}, {"azp": "otro-cliente"}):
            with self.subTest(cambios=cambios):
                self.assertEqual(obtener_claims_verificados(self.request({**self.payload, **cambios})), {})
        otra_clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.assertEqual(obtener_claims_verificados(self.request(clave=otra_clave)), {})

    def test_rechaza_claims_requeridos_ausentes(self):
        for campo in ("exp", "sub", "iss", "azp"):
            payload = {k: v for k, v in self.payload.items() if k != campo}
            with self.subTest(campo=campo):
                self.assertEqual(obtener_claims_verificados(self.request(payload)), {})

    def test_sin_sesion_sin_token_y_fallo_jwks_denegan_acceso(self):
        request = self.request()
        request.user.is_authenticated = False
        self.assertEqual(obtener_claims_verificados(request), {})
        request = self.request()
        request.session = {}
        self.assertEqual(obtener_claims_verificados(request), {})
        self.jwks.return_value.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientError("sin conexión")
        self.assertEqual(obtener_claims_verificados(self.request()), {})

    def test_roles_malformados_no_producen_500(self):
        for realm in (None, "cajero", {"roles": "cajero"}):
            with self.subTest(realm=realm):
                self.assertEqual(obtener_roles(self.request({**self.payload, "realm_access": realm})), [])
