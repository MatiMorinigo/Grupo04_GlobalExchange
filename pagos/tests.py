"""
Tests automáticos para la app pagos — HU 27.

Cubre:
- Modelo MetodoPago: creación, unicidad del nombre, str, campos de auditoría.
- API DRF (EsAdministrador): CRUD completo y filtro de habilitados.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import MetodoPago

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _crear_metodo(nombre="Transferencia", habilitado=True, creado_por=None):
    """Crea y retorna un MetodoPago de prueba."""
    return MetodoPago.objects.create(
        nombre=nombre,
        descripcion="Descripción de prueba",
        habilitado=habilitado,
        creado_por=creado_por,
    )


def _crear_usuario(username="testuser"):
    """Crea y retorna un usuario de Django para pruebas."""
    return User.objects.create_user(username=username, password="testpass123")


# ─────────────────────────────────────────────────────────────────────────────
# Tests de Modelo
# ─────────────────────────────────────────────────────────────────────────────


class MetodoPagoModelTest(TestCase):
    """Pruebas unitarias sobre el modelo MetodoPago."""

    def test_creacion_basica(self):
        """Un método de pago se crea correctamente con los valores por defecto."""
        metodo = _crear_metodo()
        self.assertEqual(metodo.nombre, "Transferencia")
        self.assertTrue(metodo.habilitado)
        self.assertIsNotNone(metodo.creado_en)
        self.assertIsNotNone(metodo.actualizado_en)

    def test_str_retorna_nombre(self):
        """__str__ devuelve el nombre del método de pago."""
        metodo = _crear_metodo(nombre="Efectivo")
        self.assertEqual(str(metodo), "Efectivo")

    def test_habilitado_por_defecto_es_true(self):
        """El campo habilitado es True por defecto."""
        metodo = MetodoPago.objects.create(nombre="Cheque")
        self.assertTrue(metodo.habilitado)

    def test_nombre_es_unico(self):
        """No se pueden crear dos métodos con el mismo nombre."""
        from django.db import IntegrityError

        _crear_metodo(nombre="Débito")
        with self.assertRaises(IntegrityError):
            _crear_metodo(nombre="Débito")

    def test_creado_por_puede_ser_nulo(self):
        """El campo creado_por acepta NULL."""
        metodo = MetodoPago.objects.create(nombre="Billetera virtual", creado_por=None)
        self.assertIsNone(metodo.creado_por)

    def test_campos_auditoria_se_registran(self):
        """creado_por y modificado_por se asignan correctamente."""
        usuario = _crear_usuario()
        metodo = _crear_metodo(nombre="Crédito", creado_por=usuario)
        self.assertEqual(metodo.creado_por, usuario)
        self.assertIsNone(metodo.modificado_por)

        metodo.modificado_por = usuario
        metodo.save(update_fields=["modificado_por", "actualizado_en"])
        metodo.refresh_from_db()
        self.assertEqual(metodo.modificado_por, usuario)

    def test_descripcion_puede_estar_vacia(self):
        """El campo descripcion es opcional (blank=True)."""
        metodo = MetodoPago.objects.create(nombre="Sin descripción", descripcion="")
        self.assertEqual(metodo.descripcion, "")

    def test_meta_ordenamiento(self):
        """Los métodos se ordenan alfabéticamente por nombre."""
        _crear_metodo(nombre="Transferencia")
        _crear_metodo(nombre="Efectivo")
        _crear_metodo(nombre="Cheque")
        nombres = list(MetodoPago.objects.values_list("nombre", flat=True))
        self.assertEqual(nombres, sorted(nombres))

    def test_toggle_habilitado(self):
        """Cambiar habilitado de True a False funciona correctamente."""
        metodo = _crear_metodo(habilitado=True)
        metodo.habilitado = False
        metodo.save(update_fields=["habilitado", "actualizado_en"])
        metodo.refresh_from_db()
        self.assertFalse(metodo.habilitado)


# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Tests de API
# ─────────────────────────────────────────────────────────────────────────────


class MetodoPagoAPIBase(TestCase):
    """Clase base con utilidades para los tests de la API de pagos."""

    def setUp(self):
        from rest_framework.test import APIClient

        self.client = APIClient()
        self.usuario = _crear_usuario()
        self.metodo = _crear_metodo(nombre="Transferencia", creado_por=self.usuario)

    def _forzar_autenticacion(self):
        self.client.force_authenticate(user=self.usuario)

    def _con_rol_admin(self, activo=True):
        return patch("pagos.permissions.tiene_rol", return_value=activo)


class MetodoPagoListCreateAPITest(MetodoPagoAPIBase):
    """Pruebas para MetodoPagoListCreateView (GET, POST)."""

    def test_get_lista_metodos_como_admin(self):
        """GET /api/pagos/metodos-pago/ retorna 200 para administradores."""
        self._forzar_autenticacion()
        with self._con_rol_admin(True):
            response = self.client.get(reverse("metodopago-list-create"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_get_rechaza_sin_rol_admin(self):
        """GET retorna 403 cuando el usuario no es administrador."""
        self._forzar_autenticacion()
        with self._con_rol_admin(False):
            response = self.client.get(reverse("metodopago-list-create"))
        self.assertEqual(response.status_code, 403)

    def test_post_crea_metodo(self):
        """POST crea un nuevo método de pago y retorna 201."""
        self._forzar_autenticacion()
        datos = {"nombre": "Cheque", "descripcion": "Pago con cheque", "habilitado": True}
        with self._con_rol_admin(True):
            response = self.client.post(reverse("metodopago-list-create"), datos, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(MetodoPago.objects.filter(nombre="Cheque").exists())

    def test_filtro_habilitado_true(self):
        """GET con ?habilitado=true retorna solo métodos habilitados."""
        _crear_metodo(nombre="Inhabilitado", habilitado=False)
        self._forzar_autenticacion()
        with self._con_rol_admin(True):
            response = self.client.get(
                reverse("metodopago-list-create"), {"habilitado": "true"}
            )
        nombres = [m["nombre"] for m in response.data]
        self.assertIn("Transferencia", nombres)
        self.assertNotIn("Inhabilitado", nombres)

    def test_filtro_habilitado_false(self):
        """GET con ?habilitado=false retorna solo métodos inhabilitados."""
        _crear_metodo(nombre="Inhabilitado", habilitado=False)
        self._forzar_autenticacion()
        with self._con_rol_admin(True):
            response = self.client.get(
                reverse("metodopago-list-create"), {"habilitado": "false"}
            )
        nombres = [m["nombre"] for m in response.data]
        self.assertIn("Inhabilitado", nombres)
        self.assertNotIn("Transferencia", nombres)


class MetodoPagoDetailAPITest(MetodoPagoAPIBase):
    """Pruebas para MetodoPagoDetailView (GET, PATCH)."""

    def _url(self):
        return reverse(
            "metodopago-detail",
            kwargs={"id_metodo_pago": self.metodo.id_metodo_pago},
        )

    def test_get_detalle_como_admin(self):
        """GET retorna 200 y los datos del método para administradores."""
        self._forzar_autenticacion()
        with self._con_rol_admin(True):
            response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["nombre"], "Transferencia")

    def test_patch_actualiza_metodo(self):
        """PATCH actualiza el nombre del método de pago."""
        self._forzar_autenticacion()
        with self._con_rol_admin(True):
            response = self.client.patch(
                self._url(), {"nombre": "Wire transfer"}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.metodo.refresh_from_db()
        self.assertEqual(self.metodo.nombre, "Wire transfer")

    def test_get_no_encontrado_retorna_404(self):
        """GET con un ID inexistente retorna 404."""
        self._forzar_autenticacion()
        with self._con_rol_admin(True):
            response = self.client.get(
                reverse("metodopago-detail", kwargs={"id_metodo_pago": 99999})
            )
        self.assertEqual(response.status_code, 404)


class MetodoPagoHabilitadosAPITest(MetodoPagoAPIBase):
    """Pruebas para MetodoPagoHabilitadosView — endpoint para operaciones cambiarias."""

    def test_retorna_solo_habilitados(self):
        """GET /api/pagos/metodos-pago/habilitados/ retorna solo métodos habilitados."""
        _crear_metodo(nombre="Inhabilitado", habilitado=False)
        self._forzar_autenticacion()
        response = self.client.get(reverse("metodopago-habilitados"))
        self.assertEqual(response.status_code, 200)
        nombres = [m["nombre"] for m in response.data]
        self.assertIn("Transferencia", nombres)
        self.assertNotIn("Inhabilitado", nombres)

    def test_lista_vacia_si_no_hay_habilitados(self):
        """Retorna una lista vacía cuando no hay ningún método habilitado."""
        MetodoPago.objects.all().update(habilitado=False)
        self._forzar_autenticacion()
        response = self.client.get(reverse("metodopago-habilitados"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
