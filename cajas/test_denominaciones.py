from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from cotizaciones.models import Moneda
from .models import (
    AperturaCaja, AsignacionCaja, Caja, DenominacionBillete,
    DetalleInventarioInicial, Sucursal,
)


class DenominacionWebTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="gestor_denominaciones")
        self.client.force_login(self.usuario)
        session = self.client.session
        session["oidc_id_token_expiration"] = (timezone.now() + timedelta(hours=1)).timestamp()
        session.save()
        self.roles = ["tesorero"]
        for target in ("core.keycloak.obtener_roles", "core.context_processors.obtener_roles"):
            mock = patch(target, side_effect=lambda request: self.roles if request.user.is_authenticated else [])
            mock.start()
            self.addCleanup(mock.stop)
        self.usd = Moneda.objects.get(codigo="USD")
        self.pyg = Moneda.objects.get(codigo="PYG")
        self.denominacion = DenominacionBillete.objects.create(moneda=self.usd, valor=Decimal("20"))
        self.lista = reverse("denominacion-list")
        self.crear = reverse("denominacion-create")
        self.editar = reverse("denominacion-update", args=[self.denominacion.pk])
        self.activar = reverse("denominacion-activate", args=[self.denominacion.pk])
        self.desactivar = reverse("denominacion-deactivate", args=[self.denominacion.pk])

    def test_listado_ordenado_por_moneda_y_valor_incluye_inactivas(self):
        menor = DenominacionBillete.objects.create(moneda=self.usd, valor=Decimal("5"), activa=False)
        guarani = DenominacionBillete.objects.create(moneda=self.pyg, valor=Decimal("10000"))
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Inactiva")
        self.assertContains(respuesta, "Activa")
        self.assertContains(respuesta, "USD")
        self.assertContains(respuesta, "10.000")
        self.assertEqual(list(respuesta.context["denominaciones"]), [guarani, menor, self.denominacion])

    def test_navegacion_y_acceso_para_administrador_y_tesorero(self):
        for rol in ("administrador", "tesorero"):
            self.roles = [rol]
            for url in (self.lista, self.crear, self.editar):
                with self.subTest(rol=rol, url=url):
                    respuesta = self.client.get(url)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertEqual(respuesta.context["active_menu"], "cajas")
                    self.assertEqual(respuesta.context["active_submenu"], "denominaciones")
                    sidebar = respuesta.content.decode().split('<aside class="app-sidebar', 1)[1].split("</aside>", 1)[0]
                    self.assertInHTML(
                        f'<a href="{self.lista}" class="nav-link active">'
                        '<i class="nav-icon bi bi-cash-coin"></i><p>Denominaciones de billetes</p></a>', sidebar,
                    )
                    self.assertEqual(sidebar.count('class="nav-link active"'), 2)

    def test_otros_roles_no_pueden_acceder_incluso_con_privilegios_django(self):
        self.usuario.is_staff = self.usuario.is_superuser = True
        self.usuario.save()
        for roles in ([], ["cajero"], ["usuario"], ["analista_cambiario"]):
            self.roles = roles
            for url in (self.lista, self.crear, self.editar, self.activar, self.desactivar):
                for metodo in (self.client.get, self.client.post):
                    with self.subTest(roles=roles, url=url, metodo=metodo.__name__):
                        self.assertEqual(metodo(url).status_code, 403)

    def test_anonimo_es_redirigido_al_login(self):
        self.client.logout()
        for url in (self.lista, self.crear, self.editar, self.activar, self.desactivar):
            for metodo in (self.client.get, self.client.post):
                with self.subTest(url=url, metodo=metodo.__name__):
                    respuesta = metodo(url)
                    self.assertEqual(respuesta.status_code, 302)
                    self.assertIn("/oidc/authenticate/", respuesta.url)

    def test_ambos_roles_pueden_crear_modificar_y_cambiar_estado(self):
        for indice, rol in enumerate(("administrador", "tesorero"), start=1):
            self.roles = [rol]
            with self.subTest(rol=rol):
                respuesta = self.client.post(self.crear, {"moneda": "USD", "valor": str(indice)})
                self.assertRedirects(respuesta, self.lista)
                denominacion = DenominacionBillete.objects.get(moneda=self.usd, valor=indice)
                self.assertTrue(denominacion.activa)
                respuesta = self.client.post(reverse("denominacion-update", args=[denominacion.pk]),
                                             {"moneda": "PYG", "valor": str(1000 * indice)})
                self.assertRedirects(respuesta, self.lista)
                denominacion.refresh_from_db()
                self.assertEqual(denominacion.moneda, self.pyg)
                self.assertEqual(denominacion.valor, Decimal(1000 * indice))
                for ruta, estado in (("denominacion-deactivate", False), ("denominacion-activate", True)):
                    self.assertRedirects(self.client.post(reverse(ruta, args=[denominacion.pk])), self.lista)
                    denominacion.refresh_from_db()
                    self.assertEqual(denominacion.activa, estado)
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.is_staff)
        self.assertFalse(self.usuario.is_superuser)

    def test_edicion_no_reactiva_ni_acepta_estado_desde_formulario(self):
        self.client.post(self.desactivar)
        self.assertRedirects(self.client.post(self.editar, {"moneda": "USD", "valor": "50", "activa": "on"}), self.lista)
        self.denominacion.refresh_from_db()
        self.assertFalse(self.denominacion.activa)
        self.assertEqual(self.denominacion.valor, Decimal("50"))

    def test_rechaza_valores_invalidos_en_alta_y_edicion(self):
        for valor in ("0", "-1", "1.001", "NaN", "Infinity", "texto", "", "10000000000000000"):
            for url in (self.crear, self.editar):
                with self.subTest(valor=valor, url=url):
                    respuesta = self.client.post(url, {"moneda": "USD", "valor": valor})
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertIn("valor", respuesta.context["form"].errors)
        self.assertEqual(DenominacionBillete.objects.count(), 1)
        self.denominacion.refresh_from_db()
        self.assertEqual(self.denominacion.valor, Decimal("20"))

    def test_rechaza_moneda_inexistente(self):
        respuesta = self.client.post(self.crear, {"moneda": "ZZZ", "valor": "10"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("moneda", respuesta.context["form"].errors)
        self.assertEqual(DenominacionBillete.objects.count(), 1)

    def test_unicidad_tambien_con_inactivas_y_al_modificar(self):
        self.client.post(self.desactivar)
        respuesta = self.client.post(self.crear, {"moneda": "USD", "valor": "20.00"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].non_field_errors())
        otra = DenominacionBillete.objects.create(moneda=self.usd, valor=Decimal("50"))
        respuesta = self.client.post(reverse("denominacion-update", args=[otra.pk]), {"moneda": "USD", "valor": "20"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].non_field_errors())
        otra.refresh_from_db()
        self.assertEqual(otra.valor, Decimal("50"))
        self.assertRedirects(self.client.post(self.crear, {"moneda": "PYG", "valor": "20"}), self.lista)

    def test_conflicto_unico_al_guardar_muestra_error_sin_500(self):
        causa = Exception("unique violation")
        causa.diag = SimpleNamespace(constraint_name="billete_moneda_valor_unico")
        error = IntegrityError("duplicado concurrente")
        error.__cause__ = causa
        for url in (self.crear, self.editar):
            with self.subTest(url=url), patch.object(DenominacionBillete, "save", side_effect=error):
                respuesta = self.client.post(url, {"moneda": "USD", "valor": "50"})
                self.assertContains(respuesta, "Ya existe una denominación con esa moneda y valor.")
        self.assertEqual(DenominacionBillete.objects.count(), 1)

    def test_estado_solo_por_post_y_con_csrf(self):
        for url in (self.activar, self.desactivar):
            self.assertEqual(self.client.get(url).status_code, 405)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        for url in (self.crear, self.editar, self.activar, self.desactivar):
            self.assertEqual(cliente.post(url, {"moneda": "USD", "valor": "50"}).status_code, 403)
        self.denominacion.refresh_from_db()
        self.assertTrue(self.denominacion.activa)
        self.assertEqual(self.denominacion.valor, Decimal("20"))

    def test_recursos_inexistentes_responden_404(self):
        for ruta in ("denominacion-update", "denominacion-activate", "denominacion-deactivate"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.post(reverse(ruta, args=[999999])).status_code, 404)

    def test_edicion_y_deshabilitacion_conservan_historial_y_proteccion_de_borrado(self):
        ahora = timezone.now()
        sucursal = Sucursal.objects.create(codigo="HIST", nombre="Central")
        caja = Caja.objects.create(sucursal=sucursal, codigo="HIST", nombre="Caja")
        asignacion = AsignacionCaja.objects.create(
            caja=caja, cajero_keycloak_id=uuid4(), cajero_username="cajero", turno="Diurno",
            fecha_inicio=ahora - timedelta(hours=1), fecha_fin=ahora + timedelta(hours=1),
            asignado_por=self.usuario,
        )
        apertura = AperturaCaja.objects.create(
            caja=caja, asignacion=asignacion, cajero_keycloak_id=asignacion.cajero_keycloak_id,
        )
        detalle = DetalleInventarioInicial.objects.create(
            apertura=apertura, denominacion=self.denominacion, moneda=self.usd,
            valor_denominacion=self.denominacion.valor, cantidad=3,
        )
        self.assertRedirects(self.client.post(self.editar, {"moneda": "PYG", "valor": "10000"}), self.lista)
        self.assertRedirects(self.client.post(self.desactivar), self.lista)
        self.assertEqual(apertura.saldos_iniciales, {"USD": Decimal("60")})
        detalle.refresh_from_db()
        self.assertEqual(detalle.moneda, self.usd)
        self.assertEqual(detalle.valor_denominacion, Decimal("20"))
        with self.assertRaises(ProtectedError):
            self.denominacion.delete()
        self.assertEqual(self.client.delete(self.editar).status_code, 405)
        self.assertTrue(DenominacionBillete.objects.filter(pk=self.denominacion.pk).exists())
