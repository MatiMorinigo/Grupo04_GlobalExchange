from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.test import SimpleTestCase, override_settings

from pagos.models import MetodoPago, TipoMetodoPago
from transacciones.models import ProveedorPago

from .proveedores_pago import (
    MetodoPagoNoHabilitadoError,
    ProveedorPagoBase,
    ProveedorPagoError,
    SimuladorBilleteraProveedor,
    StripeProveedor,
    get_proveedor,
)
from .proveedores_pago.stripe_proveedor import a_unidad_minima


CREAR_PAYMENT_INTENT = "integrations.proveedores_pago.stripe_proveedor.stripe.PaymentIntent.create"


def _pago(monto="1500.50", moneda="PYG", token="pm_card_visa"):
    """Construye un pago mínimo con los atributos que leen los proveedores."""

    return SimpleNamespace(
        id_pago=7,
        transaccion_id=42,
        monto=Decimal(monto),
        moneda_id=moneda,
        metodo_pago=SimpleNamespace(stripe_payment_method_id=token),
    )


def _error_tarjeta(code="card_declined", decline_code="generic_decline", id_intento="pi_rechazado"):
    """Construye el error que Stripe lanza cuando rechaza una tarjeta."""

    cuerpo = {
        "error": {
            "type": "card_error",
            "code": code,
            "decline_code": decline_code,
            "message": "Your card was declined.",
            "payment_intent": {"id": id_intento, "object": "payment_intent"},
        }
    }
    return stripe.CardError("Your card was declined.", None, code, json_body=cuerpo)


class GetProveedorTests(SimpleTestCase):
    """Prueba el único punto que elige el proveedor según el tipo de método."""

    def test_tarjetas_de_credito_y_debito_usan_stripe(self):
        for tipo in (TipoMetodoPago.TARJETA_CREDITO, TipoMetodoPago.TARJETA_DEBITO):
            with self.subTest(tipo=tipo):
                self.assertIsInstance(get_proveedor(MetodoPago(tipo=tipo)), StripeProveedor)

    def test_billetera_usa_el_simulador(self):
        proveedor = get_proveedor(MetodoPago(tipo=TipoMetodoPago.BILLETERA_ELECTRONICA))

        self.assertIsInstance(proveedor, SimuladorBilleteraProveedor)

    def test_tipo_sin_proveedor_no_esta_habilitado(self):
        with self.assertRaisesMessage(MetodoPagoNoHabilitadoError, "este método"):
            get_proveedor(MetodoPago(tipo="EFECTIVO"))

    def test_codigos_de_proveedor_coinciden_con_los_registrados_en_pago(self):
        self.assertIn(StripeProveedor.codigo, ProveedorPago.values)
        self.assertIn(SimuladorBilleteraProveedor.codigo, ProveedorPago.values)


class ValidacionMonedaTests(SimpleTestCase):
    """Prueba el control de monedas común a todos los proveedores."""

    class _ProveedorSoloPYG(ProveedorPagoBase):
        monedas_admitidas = frozenset({"PYG"})

        def iniciar_pago(self, pago):
            raise NotImplementedError

    def test_proveedor_con_monedas_restringidas_rechaza_otras(self):
        with self.assertRaisesMessage(MetodoPagoNoHabilitadoError, "no admite pagos en USD"):
            self._ProveedorSoloPYG().validar(None, Decimal("10"), "USD")

    def test_simulador_admite_cualquier_moneda(self):
        simulador = SimuladorBilleteraProveedor()

        for moneda in ("PYG", "USD", "EUR"):
            with self.subTest(moneda=moneda):
                simulador.validar(None, Decimal("10"), moneda)


class UnidadMinimaTests(SimpleTestCase):
    """Prueba la conversión de importes al formato que Stripe espera."""

    def test_guaranies_se_redondean_a_unidades_enteras(self):
        self.assertEqual(a_unidad_minima(Decimal("1500.50"), "PYG"), 1501)
        self.assertEqual(a_unidad_minima(Decimal("1500.49"), "PYG"), 1500)

    def test_monedas_con_decimales_se_expresan_en_centavos(self):
        self.assertEqual(a_unidad_minima(Decimal("10.25"), "USD"), 1025)
        self.assertEqual(a_unidad_minima(Decimal("100"), "EUR"), 10000)

    def test_monto_a_cobrar_refleja_el_redondeo(self):
        proveedor = StripeProveedor()

        self.assertEqual(proveedor.monto_a_cobrar(Decimal("1500.50"), "PYG"), Decimal("1501.00"))
        self.assertEqual(proveedor.monto_a_cobrar(Decimal("10.25"), "USD"), Decimal("10.25"))


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class StripeProveedorTests(SimpleTestCase):
    """Prueba el inicio de pagos con Stripe sin contactar al servicio real."""

    def test_pago_aceptado_devuelve_la_referencia_del_payment_intent(self):
        with patch(CREAR_PAYMENT_INTENT) as crear:
            crear.return_value = SimpleNamespace(id="pi_123", status="succeeded")
            resultado = StripeProveedor().iniciar_pago(_pago())

        self.assertEqual(resultado.referencia_externa, "pi_123")
        self.assertEqual(resultado.estado_proveedor, "succeeded")
        kwargs = crear.call_args.kwargs
        self.assertEqual(kwargs["amount"], 1501)
        self.assertEqual(kwargs["currency"], "pyg")
        self.assertEqual(kwargs["payment_method"], "pm_card_visa")
        self.assertTrue(kwargs["confirm"])
        self.assertEqual(
            kwargs["automatic_payment_methods"],
            {"enabled": True, "allow_redirects": "never"},
        )
        self.assertEqual(kwargs["metadata"], {"id_transaccion": "42", "id_pago": "7"})
        self.assertEqual(kwargs["idempotency_key"], "globalexchange-pago-7")
        self.assertEqual(kwargs["api_key"], "sk_test_dummy")

    def test_pago_en_divisa_se_envia_en_centavos(self):
        with patch(CREAR_PAYMENT_INTENT) as crear:
            crear.return_value = SimpleNamespace(id="pi_usd", status="succeeded")
            StripeProveedor().iniciar_pago(_pago(monto="100.00", moneda="USD"))

        self.assertEqual(crear.call_args.kwargs["amount"], 10000)
        self.assertEqual(crear.call_args.kwargs["currency"], "usd")

    def test_tarjeta_rechazada_informa_el_motivo_y_conserva_la_referencia(self):
        with patch(CREAR_PAYMENT_INTENT, side_effect=_error_tarjeta()):
            with self.assertRaises(ProveedorPagoError) as contexto:
                StripeProveedor().iniciar_pago(_pago(token="pm_card_chargeDeclined"))

        error = contexto.exception
        self.assertTrue(error.rechazado)
        self.assertEqual(error.referencia_externa, "pi_rechazado")
        self.assertEqual(error.mensaje_usuario, "La tarjeta fue rechazada por el emisor.")

    def test_fondos_insuficientes_tiene_mensaje_propio(self):
        rechazo = _error_tarjeta(decline_code="insufficient_funds")
        with patch(CREAR_PAYMENT_INTENT, side_effect=rechazo):
            with self.assertRaises(ProveedorPagoError) as contexto:
                StripeProveedor().iniciar_pago(_pago())

        self.assertEqual(contexto.exception.mensaje_usuario, "La tarjeta no tiene fondos suficientes.")

    def test_error_de_conexion_no_se_considera_rechazo(self):
        with patch(CREAR_PAYMENT_INTENT, side_effect=stripe.APIConnectionError("timeout")):
            with self.assertRaises(ProveedorPagoError) as contexto:
                StripeProveedor().iniciar_pago(_pago())

        self.assertFalse(contexto.exception.rechazado)
        self.assertEqual(contexto.exception.referencia_externa, "")
        self.assertIn("No pudimos comunicarnos", contexto.exception.mensaje_usuario)

    def test_pago_que_requiere_autenticacion_adicional_se_rechaza(self):
        with patch(CREAR_PAYMENT_INTENT) as crear:
            crear.return_value = SimpleNamespace(id="pi_3ds", status="requires_action")
            with self.assertRaises(ProveedorPagoError) as contexto:
                StripeProveedor().iniciar_pago(_pago())

        self.assertTrue(contexto.exception.rechazado)
        self.assertEqual(contexto.exception.referencia_externa, "pi_3ds")

    def test_validar_exige_token_en_la_tarjeta(self):
        tarjeta = MetodoPago(tipo=TipoMetodoPago.TARJETA_CREDITO, stripe_payment_method_id="")

        with self.assertRaisesMessage(MetodoPagoNoHabilitadoError, "no está habilitada"):
            StripeProveedor().validar(tarjeta, Decimal("1000"), "PYG")

    @override_settings(STRIPE_SECRET_KEY="")
    def test_validar_exige_la_clave_de_stripe(self):
        tarjeta = MetodoPago(tipo=TipoMetodoPago.TARJETA_CREDITO, stripe_payment_method_id="pm_card_visa")

        with self.assertRaisesMessage(MetodoPagoNoHabilitadoError, "no está configurado"):
            StripeProveedor().validar(tarjeta, Decimal("1000"), "PYG")

    def test_validar_rechaza_importes_mayores_al_maximo(self):
        tarjeta = MetodoPago(tipo=TipoMetodoPago.TARJETA_CREDITO, stripe_payment_method_id="pm_card_visa")

        StripeProveedor().validar(tarjeta, Decimal("99999999"), "PYG")
        with self.assertRaisesMessage(MetodoPagoNoHabilitadoError, "supera el máximo"):
            StripeProveedor().validar(tarjeta, Decimal("100000000"), "PYG")


class SimuladorBilleteraTests(SimpleTestCase):
    """Prueba el proveedor simulado de billeteras electrónicas."""

    def test_genera_referencias_sim_unicas(self):
        simulador = SimuladorBilleteraProveedor()

        primera = simulador.iniciar_pago(_pago())
        segunda = simulador.iniciar_pago(_pago())

        self.assertTrue(primera.referencia_externa.startswith("SIM-"))
        self.assertNotEqual(primera.referencia_externa, segunda.referencia_externa)
        self.assertEqual(primera.estado_proveedor, "pendiente_aprobacion")
