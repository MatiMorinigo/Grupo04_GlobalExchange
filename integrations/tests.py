import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.test import SimpleTestCase, override_settings

from pagos.models import MetodoPago, TipoMetodoPago
from transacciones.models import ProveedorPago

from .proveedores_pago import (
    ConfirmacionInvalidaError,
    MetodoPagoNoHabilitadoError,
    ProveedorPagoBase,
    ProveedorPagoError,
    SimuladorBilleteraProveedor,
    StripeProveedor,
    get_proveedor,
)
from .proveedores_pago.stripe_proveedor import a_unidad_minima, desde_unidad_minima


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


SECRETO_WEBHOOK = "whsec_prueba"
CONSULTAR_PAYMENT_INTENT = "integrations.proveedores_pago.stripe_proveedor.stripe.PaymentIntent.retrieve"


def _intento(estado="succeeded", id_pago="7", monto=742350, moneda="pyg", error=None):
    """Construye un PaymentIntent mínimo como lo envía Stripe."""

    return {
        "id": "pi_123",
        "object": "payment_intent",
        "status": estado,
        "amount": monto,
        "currency": moneda,
        "metadata": {"id_pago": id_pago, "id_transaccion": "42"} if id_pago else {},
        "last_payment_error": error,
    }


def _evento_firmado(tipo, intento, secreto=SECRETO_WEBHOOK):
    """Devuelve el cuerpo y el encabezado de firma de un evento de Stripe."""

    payload = json.dumps(
        {"id": "evt_1", "object": "event", "type": tipo, "data": {"object": intento}}
    )
    firma = stripe.WebhookSignature.generate_signature_header(payload, secreto)
    return payload.encode(), firma


@override_settings(STRIPE_WEBHOOK_SECRET=SECRETO_WEBHOOK)
class InterpretarEventoStripeTests(SimpleTestCase):
    """Prueba la validación de los webhooks de Stripe."""

    def test_pago_aprobado_devuelve_el_resultado_del_payment_intent(self):
        payload, firma = _evento_firmado("payment_intent.succeeded", _intento())

        resultado = StripeProveedor().interpretar_evento(payload, firma)

        self.assertTrue(resultado.aprobado)
        self.assertEqual(resultado.referencia_externa, "pi_123")
        self.assertEqual(resultado.id_pago, 7)
        self.assertEqual(resultado.monto, Decimal("742350.00"))
        self.assertEqual(resultado.moneda, "PYG")
        self.assertEqual(resultado.detalle, "")

    def test_pago_rechazado_incluye_el_motivo(self):
        error = {"code": "card_declined", "decline_code": "insufficient_funds",
                 "message": "Your card has insufficient funds."}
        payload, firma = _evento_firmado(
            "payment_intent.payment_failed",
            _intento(estado="requires_payment_method", monto=10000, moneda="usd", error=error),
        )

        resultado = StripeProveedor().interpretar_evento(payload, firma)

        self.assertFalse(resultado.aprobado)
        self.assertEqual(resultado.monto, Decimal("100.00"))
        self.assertEqual(resultado.moneda, "USD")
        self.assertIn("insufficient_funds", resultado.detalle)

    def test_firma_invalida_no_se_acepta(self):
        payload, firma = _evento_firmado("payment_intent.succeeded", _intento(), secreto="whsec_otro")

        with self.assertRaises(ConfirmacionInvalidaError):
            StripeProveedor().interpretar_evento(payload, firma)

    def test_payload_alterado_no_se_acepta(self):
        payload, firma = _evento_firmado("payment_intent.succeeded", _intento())

        with self.assertRaises(ConfirmacionInvalidaError):
            StripeProveedor().interpretar_evento(payload.replace(b"742350", b"1"), firma)

    @override_settings(STRIPE_WEBHOOK_SECRET="")
    def test_sin_secreto_configurado_no_se_acepta(self):
        payload, firma = _evento_firmado("payment_intent.succeeded", _intento())

        with self.assertRaisesMessage(ConfirmacionInvalidaError, "no está configurado"):
            StripeProveedor().interpretar_evento(payload, firma)

    def test_otros_eventos_se_ignoran(self):
        payload, firma = _evento_firmado("charge.refunded", {"id": "ch_1", "object": "charge"})

        self.assertIsNone(StripeProveedor().interpretar_evento(payload, firma))

    def test_evento_sin_id_pago_devuelve_resultado_sin_id(self):
        payload, firma = _evento_firmado("payment_intent.succeeded", _intento(id_pago=None))

        resultado = StripeProveedor().interpretar_evento(payload, firma)

        self.assertIsNone(resultado.id_pago)


class DesdeUnidadMinimaTests(SimpleTestCase):
    """Prueba la conversión inversa de los importes de Stripe."""

    def test_convierte_guaranies_y_centavos(self):
        self.assertEqual(desde_unidad_minima(742351, "PYG"), Decimal("742351.00"))
        self.assertEqual(desde_unidad_minima(1025, "usd"), Decimal("10.25"))

    def test_es_la_inversa_de_a_unidad_minima(self):
        for monto, moneda in ((Decimal("10.25"), "USD"), (Decimal("1500.00"), "PYG")):
            with self.subTest(moneda=moneda):
                self.assertEqual(desde_unidad_minima(a_unidad_minima(monto, moneda), moneda), monto)


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class ConsultarPagoStripeTests(SimpleTestCase):
    """Prueba la consulta de respaldo del estado de un pago en Stripe."""

    def _consultar(self, **retorno):
        with patch(CONSULTAR_PAYMENT_INTENT, **retorno) as consultar:
            resultado = StripeProveedor().consultar_pago(SimpleNamespace(referencia_externa="pi_123"))
        return resultado, consultar

    def test_pago_cobrado_se_informa_como_aprobado(self):
        resultado, consultar = self._consultar(return_value=_intento())

        self.assertTrue(resultado.aprobado)
        self.assertEqual(consultar.call_args.args, ("pi_123",))
        self.assertEqual(consultar.call_args.kwargs["api_key"], "sk_test_dummy")

    def test_pago_rechazado_se_informa_como_rechazado(self):
        resultado, _ = self._consultar(return_value=_intento(estado="requires_payment_method"))

        self.assertFalse(resultado.aprobado)

    def test_pago_en_proceso_no_tiene_resultado(self):
        resultado, _ = self._consultar(return_value=_intento(estado="processing"))

        self.assertIsNone(resultado)

    def test_error_de_comunicacion_se_informa(self):
        with self.assertRaises(ProveedorPagoError):
            self._consultar(side_effect=stripe.APIConnectionError("timeout"))


class ResultadoSimuladoTests(SimpleTestCase):
    """Prueba la respuesta de la billetera simulada."""

    def _pago(self):
        return SimpleNamespace(
            id_pago=9, referencia_externa="SIM-ABC", monto=Decimal("1000.00"), moneda_id="PYG"
        )

    def test_aprobacion_usa_los_datos_del_pago(self):
        resultado = SimuladorBilleteraProveedor().resultado_simulado(self._pago(), aprobado=True)

        self.assertTrue(resultado.aprobado)
        self.assertEqual(resultado.id_pago, 9)
        self.assertEqual(resultado.referencia_externa, "SIM-ABC")
        self.assertEqual(resultado.monto, Decimal("1000.00"))
        self.assertEqual(resultado.detalle, "")

    def test_rechazo_deja_constancia_del_usuario(self):
        usuario = SimpleNamespace(get_username=lambda: "analista1")

        resultado = SimuladorBilleteraProveedor().resultado_simulado(
            self._pago(), aprobado=False, usuario=usuario
        )

        self.assertFalse(resultado.aprobado)
        self.assertIn("analista1", resultado.detalle)
