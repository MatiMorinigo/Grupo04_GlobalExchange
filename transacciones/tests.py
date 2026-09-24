from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import BigAutoField
from django.test import TestCase
from django.utils import timezone

from clientes.models import CategoriaCliente, Cliente, TipoCliente
from cotizaciones.models import Moneda, TasaCambio

from .models import (
    EstadoTransaccion,
    EtapaCancelacion,
    TipoOperacion,
    Transaccion,
)


User = get_user_model()


class TransaccionModelTests(TestCase):
    """Prueba la estructura y las reglas de integridad de las transacciones."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user(username="operador")
        cls.cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente de prueba",
            categoria=CategoriaCliente.VIP,
            tipo=TipoCliente.FISICA,
        )
        cls.pyg = Moneda.objects.get(codigo="PYG")
        cls.usd = Moneda.objects.get(codigo="USD")
        cls.eur = Moneda.objects.get(codigo="EUR")
        cls.tasa_usd = TasaCambio.objects.create(
            moneda_origen=cls.usd,
            moneda_destino=cls.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
            vigente=True,
        )
        cls.tasa_eur = TasaCambio.objects.create(
            moneda_origen=cls.eur,
            moneda_destino=cls.pyg,
            precio_compra=Decimal("8100.0000"),
            precio_venta=Decimal("8250.0000"),
            vigente=True,
        )

    def crear_transaccion(self, **cambios):
        """Construye una transaccion valida y permite sobrescribir campos."""

        datos = {
            "cliente": self.cliente,
            "creada_por": self.usuario,
            "tipo_operacion": TipoOperacion.COMPRA,
            "moneda": self.usd,
            "tasa_cambio": self.tasa_usd,
            "tasa_aplicada": self.tasa_usd.precio_venta,
            "fecha_vigencia_tasa": self.tasa_usd.fecha_vigencia,
            "monto_divisa": Decimal("100.00"),
            "subtotal_pyg": Decimal("735000.00"),
            "categoria_aplicada": CategoriaCliente.VIP,
            "beneficio_porcentaje": Decimal("5.00"),
            "limite_beneficio_pyg": Decimal("50000000.00"),
            "monto_beneficiado_pyg": Decimal("735000.00"),
            "beneficio_monto_pyg": Decimal("36750.00"),
            "comision_porcentaje": Decimal("1.00"),
            "comision_monto_pyg": Decimal("7350.00"),
            "total_pyg": Decimal("705600.00"),
        }
        datos.update(cambios)
        return Transaccion(**datos)

    def test_utiliza_big_auto_field_como_clave_primaria(self):
        campo = Transaccion._meta.get_field("id_transaccion")

        self.assertIsInstance(campo, BigAutoField)

    def test_transaccion_valida_inicia_pendiente(self):
        transaccion = self.crear_transaccion()

        transaccion.full_clean()
        transaccion.save()

        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)
        self.assertIsNotNone(transaccion.id_transaccion)

    def test_rechaza_pyg_como_moneda_extranjera(self):
        transaccion = self.crear_transaccion(moneda=self.pyg)

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("moneda", contexto.exception.message_dict)

    def test_rechaza_tasa_de_otra_moneda(self):
        transaccion = self.crear_transaccion(tasa_cambio=self.tasa_eur)

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("tasa_cambio", contexto.exception.message_dict)

    def test_compra_exige_precio_de_venta(self):
        transaccion = self.crear_transaccion(
            tasa_aplicada=self.tasa_usd.precio_compra,
        )

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("tasa_aplicada", contexto.exception.message_dict)

    def test_venta_utiliza_precio_de_compra(self):
        transaccion = self.crear_transaccion(
            tipo_operacion=TipoOperacion.VENTA,
            tasa_aplicada=self.tasa_usd.precio_compra,
        )

        transaccion.full_clean()

    def test_cancelada_exige_fecha_y_etapa(self):
        transaccion = self.crear_transaccion(estado=EstadoTransaccion.CANCELADA)

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("cancelada_en", contexto.exception.message_dict)
        self.assertIn("etapa_cancelacion", contexto.exception.message_dict)

    def test_cancelacion_previa_al_pago_es_valida(self):
        transaccion = self.crear_transaccion(
            estado=EstadoTransaccion.CANCELADA,
            cancelada_en=timezone.now(),
            etapa_cancelacion=EtapaCancelacion.PREVIA_PAGO,
            motivo_cancelacion="El cliente rechazo la nueva cotizacion.",
        )

        transaccion.full_clean()

    def test_completada_exige_fecha(self):
        transaccion = self.crear_transaccion(estado=EstadoTransaccion.COMPLETADA)

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("completada_en", contexto.exception.message_dict)

    def test_rechaza_monto_beneficiado_superior_al_limite(self):
        transaccion = self.crear_transaccion(
            limite_beneficio_pyg=Decimal("100000.00"),
            monto_beneficiado_pyg=Decimal("100001.00"),
        )

        with self.assertRaises(ValidationError):
            transaccion.full_clean()

    def test_tasa_y_condiciones_quedan_guardadas_como_snapshot(self):
        transaccion = self.crear_transaccion()
        transaccion.full_clean()
        transaccion.save()

        self.tasa_usd.precio_venta = Decimal("7400.0000")
        self.tasa_usd.save(update_fields=["precio_venta"])

        transaccion.refresh_from_db()
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7350.0000"))
        self.assertEqual(transaccion.beneficio_porcentaje, Decimal("5.00"))
        self.assertEqual(transaccion.comision_porcentaje, Decimal("1.00"))

    def test_aceptar_nueva_tasa_actualiza_la_misma_transaccion(self):
        transaccion = self.crear_transaccion()
        transaccion.full_clean()
        transaccion.save()
        identificador_original = transaccion.id_transaccion

        self.tasa_usd.vigente = False
        self.tasa_usd.save(update_fields=["vigente"])
        tasa_nueva = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7250.0000"),
            precio_venta=Decimal("7400.0000"),
            vigente=True,
        )

        transaccion.tasa_cambio = tasa_nueva
        transaccion.tasa_aplicada = tasa_nueva.precio_venta
        transaccion.fecha_vigencia_tasa = tasa_nueva.fecha_vigencia
        transaccion.subtotal_pyg = Decimal("740000.00")
        transaccion.monto_beneficiado_pyg = Decimal("740000.00")
        transaccion.beneficio_monto_pyg = Decimal("37000.00")
        transaccion.comision_monto_pyg = Decimal("7400.00")
        transaccion.total_pyg = Decimal("710400.00")
        transaccion.full_clean()
        transaccion.save()

        self.assertEqual(transaccion.id_transaccion, identificador_original)
        self.assertEqual(Transaccion.objects.count(), 1)
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7400.0000"))
