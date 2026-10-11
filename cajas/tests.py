from django.test import TestCase
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse

from destinos.models import User
from .models import Sucursal, Caja
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import AsignacionCaja
from uuid import uuid4
from django.db import IntegrityError, transaction

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

class AsignacionCajaTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.administrador = User.objects.create_user(
            username="admin_asignaciones"
        )

        self.cajero1 = uuid4()

        self.cajero2 = uuid4()

        self.sucursal = Sucursal.objects.create(
            codigo="SUC01",
            nombre="Sucursal Central",
            direccion="Asunción"
        )

        self.caja1 = Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA01",
            nombre="Caja Principal"
        )

        self.caja2 = Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA02",
            nombre="Caja Secundaria"
        )

        self.inicio = timezone.now().replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        self.fin = self.inicio + timedelta(hours=6)

    def crear_asignacion(self, caja, cajero, inicio, fin):
        asignacion = AsignacionCaja(
            caja=caja,
            cajero_keycloak_id=cajero,
            cajero_username=f"cajero-{str(cajero)[:8]}",
            turno="Mañana",
            fecha_inicio=inicio,
            fecha_fin=fin,
            asignado_por=self.administrador
        )
        asignacion.full_clean()
        asignacion.save()
        return asignacion

    def test_no_dos_cajeros_en_misma_caja(self):
        self.crear_asignacion(
            self.caja1, self.cajero1,
            self.inicio, self.fin
        )

        with self.assertRaises(ValidationError):
            self.crear_asignacion(
                self.caja1, self.cajero2,
                self.inicio + timedelta(hours=2),
                self.fin + timedelta(hours=2)
            )

    def test_no_mismo_cajero_en_dos_cajas(self):
        self.crear_asignacion(
            self.caja1, self.cajero1,
            self.inicio, self.fin
        )

        with self.assertRaises(ValidationError):
            self.crear_asignacion(
                self.caja2, self.cajero1,
                self.inicio + timedelta(hours=2),
                self.fin + timedelta(hours=2)
            )

    def test_turnos_consecutivos_permitidos(self):
        self.crear_asignacion(
            self.caja1, self.cajero1,
            self.inicio, self.fin
        )

        self.crear_asignacion(
            self.caja1, self.cajero2,
            self.fin,
            self.fin + timedelta(hours=6)
        )

        self.assertEqual(
            AsignacionCaja.objects.count(), 2
        )

    def test_fecha_fin_debe_ser_posterior(self):
        with self.assertRaises(ValidationError):
            self.crear_asignacion(
                self.caja1, self.cajero1,
                self.inicio, self.inicio
            )

    def test_no_asignar_caja_inactiva(self):
        self.caja1.activa = False
        self.caja1.save()

        with self.assertRaises(ValidationError):
            self.crear_asignacion(
                self.caja1, self.cajero1,
                self.inicio, self.fin
            )


    def test_bd_impide_dos_cajeros_en_misma_caja(self):
        self.crear_asignacion(
            self.caja1, self.cajero1,
            self.inicio, self.fin
        )

        # Intentamos insertar directamente, sin full_clean().
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AsignacionCaja.objects.create(
                    caja=self.caja1,
                    cajero_keycloak_id=self.cajero2,
                    cajero_username="cajero2",
                    turno="Tarde",
                    fecha_inicio=self.inicio + timedelta(hours=2),
                    fecha_fin=self.fin + timedelta(hours=2),
                    asignado_por=self.administrador
                )


    def test_bd_impide_mismo_cajero_en_dos_cajas(self):
        self.crear_asignacion(
            self.caja1, self.cajero1,
            self.inicio, self.fin
        )

        # Mismo cajero, distinta caja, horario superpuesto.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AsignacionCaja.objects.create(
                    caja=self.caja2,
                    cajero_keycloak_id=self.cajero1,
                    cajero_username="cajero1",
                    turno="Tarde",
                    fecha_inicio=self.inicio + timedelta(hours=2),
                    fecha_fin=self.fin + timedelta(hours=2),
                    asignado_por=self.administrador
                )

class AsignacionCajaWebTests(TestCase):

    def setUp(self):
        self.administrador = get_user_model().objects.create_user(
            username="admin_asignaciones_web"
        )
        self.client.force_login(self.administrador)

        self.sucursal = Sucursal.objects.create(
            codigo="SUC01",
            nombre="Sucursal Central",
            direccion="Asunción"
        )

        self.caja = Caja.objects.create(
            sucursal=self.sucursal,
            codigo="CAJA01",
            nombre="Caja Principal"
        )

        self.cajero_id = str(uuid4())

        self.datos = {
            "caja": self.caja.pk,
            "cajero_keycloak_id": self.cajero_id,
            "turno": "Mañana",
            "fecha_inicio": "2026-10-14T08:00",
            "fecha_fin": "2026-10-14T14:00",
        }

    @patch("cajas.mixins.tiene_rol", return_value=True)
    def test_crear_asignacion_con_cajero_valido(self, mock_rol):
        with patch(
            "cajas.forms.obtener_cajeros_keycloak"
        ) as mock_lista, patch(
            "cajas.forms.obtener_cajero_verificado"
        ) as mock_verificar:

            cajero = {
                "id": self.cajero_id,
                "username": "cajero_prueba"
            }

            mock_lista.return_value = [cajero]
            mock_verificar.return_value = cajero

            respuesta = self.client.post(
                reverse("asignacion-create"),
                self.datos
            )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(AsignacionCaja.objects.count(), 1)

        asignacion = AsignacionCaja.objects.first()
        self.assertEqual(
            asignacion.cajero_username,
            "cajero_prueba"
        )
        self.assertEqual(
            str(asignacion.cajero_keycloak_id),
            self.cajero_id
        )

    @patch("cajas.mixins.tiene_rol", return_value=True)
    def test_rechazar_usuario_sin_rol_cajero(self, mock_rol):
        with patch(
            "cajas.forms.obtener_cajeros_keycloak"
        ) as mock_lista, patch(
            "cajas.forms.obtener_cajero_verificado"
        ) as mock_verificar:

            mock_lista.return_value = [{
                "id": self.cajero_id,
                "username": "usuario_prueba"
            }]

            # Keycloak indica que el usuario no es válido.
            mock_verificar.return_value = None

            respuesta = self.client.post(
                reverse("asignacion-create"),
                self.datos
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(AsignacionCaja.objects.count(), 0)
        self.assertIn(
            "cajero_keycloak_id",
            respuesta.context["form"].errors
        )

    @patch("cajas.mixins.tiene_rol", return_value=False)
    def test_usuario_sin_permisos_no_puede_asignar(self, mock_rol):
        respuesta = self.client.post(
            reverse("asignacion-create"),
            self.datos
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(AsignacionCaja.objects.count(), 0)
