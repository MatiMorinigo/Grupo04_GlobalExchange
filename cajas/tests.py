from django.test import TestCase
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Sucursal, Caja


class SucursalCajaTests(TestCase):

    def setUp(self):
        self.sucursal = Sucursal.objects.create(
            codigo="SUC01",
            nombre="Sucursal Central",
            direccion="Asunción"
        )

    def test_crear_caja_asociada_a_sucursal(self):
        caja = Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA01",
            nombre="Caja Principal"
        )

        self.assertEqual(caja.sucursal, self.sucursal)
        self.assertTrue(caja.activa)

    def test_no_permitir_codigo_repetido_en_misma_sucursal(self):
        Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA01",
            nombre="Caja Principal"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Caja.objects.create(
                    sucursal=self.sucursal,
                    codigo="CAJA01",
                    nombre="Otra Caja"
                )

    def test_permitir_mismo_codigo_en_distintas_sucursales(self):
        otra_sucursal = Sucursal.objects.create(
            codigo="SUC02",
            nombre="Sucursal Secundaria",
            direccion="San Lorenzo"
        )

        Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA01",
            nombre="Caja Principal"
        )

        Caja.objects.create(
            sucursal=otra_sucursal,
            codigo="CAJA01",
            nombre="Caja Secundaria"
        )

        self.assertEqual(Caja.objects.count(), 2)

    def test_no_eliminar_sucursal_con_cajas(self):
        Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA01",
            nombre="Caja Principal"
        )

        with self.assertRaises(ProtectedError):
            self.sucursal.delete()

class CajaWebTests(TestCase):

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="usuario_prueba",
            password="test12345"
        )
        self.client.force_login(self.usuario)

        self.sucursal = Sucursal.objects.create(
            codigo="SUC01",
            nombre="Sucursal Central",
            direccion="Asunción"
        )

    @patch("core.mixins.tiene_rol", return_value=True)
    def test_administrador_puede_crear_sucursal(self, mock_rol):
        respuesta = self.client.post(
            reverse("sucursal-create"),
            {
                "codigo": "SUC02",
                "nombre": "Sucursal Secundaria",
                "direccion": "San Lorenzo",
            }
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            Sucursal.objects.filter(codigo="SUC02").exists()
        )

    @patch("core.mixins.tiene_rol", return_value=False)
    def test_usuario_sin_rol_administrador_no_puede_crear_sucursal(self, mock_rol):
        respuesta = self.client.post(
            reverse("sucursal-create"),
            {
                "codigo": "SUC02",
                "nombre": "Sucursal Secundaria",
                "direccion": "San Lorenzo",
            }
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(
            Sucursal.objects.filter(codigo="SUC02").exists()
        )

    @patch(
        "cajas.mixins.tiene_rol",
        side_effect=lambda request, rol: rol == "tesorero"
    )
    def test_tesorero_puede_crear_caja(self, mock_rol):
        respuesta = self.client.post(
            reverse("caja-create"),
            {
                "sucursal": self.sucursal.pk,
                "codigo": "CAJA01",
                "nombre": "Caja Principal",
            }
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            Caja.objects.filter(codigo="CAJA01").exists()
        )

    @patch("cajas.mixins.tiene_rol", return_value=False)
    def test_usuario_sin_permisos_no_puede_crear_caja(self, mock_rol):
        respuesta = self.client.post(
            reverse("caja-create"),
            {
                "sucursal": self.sucursal.pk,
                "codigo": "CAJA01",
                "nombre": "Caja Principal",
            }
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(
            Caja.objects.filter(codigo="CAJA01").exists()
        )

    @patch("core.mixins.tiene_rol", return_value=True)
    def test_no_desactivar_sucursal_con_cajas_activas(self, mock_rol):
        Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA01",
            nombre="Caja Principal"
        )

        respuesta = self.client.post(
            reverse(
                "sucursal-deactivate",
                args=[self.sucursal.pk]
            )
        )

        self.sucursal.refresh_from_db()
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(self.sucursal.activa)

    @patch("cajas.mixins.tiene_rol", return_value=True)
    def test_no_asignar_caja_a_sucursal_inactiva(self, mock_rol):
        caja = Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA01",
            nombre="Caja Principal"
        )

        sucursal_inactiva = Sucursal.objects.create(
            codigo="SUC02",
            nombre="Sucursal Inactiva",
            direccion="San Lorenzo",
            activa=False
        )

        respuesta = self.client.post(
            reverse("caja-update", args=[caja.pk]),
            {
                "sucursal": sucursal_inactiva.pk,
                "codigo": "CAJA01",
                "nombre": "Caja Modificada",
            }
        )

        caja.refresh_from_db()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(caja.sucursal, self.sucursal)
        self.assertIn("sucursal", respuesta.context["form"].errors)