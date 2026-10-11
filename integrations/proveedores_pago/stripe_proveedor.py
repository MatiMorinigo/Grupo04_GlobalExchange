"""Proveedor de pagos con tarjeta a través de Stripe (PaymentIntents)."""

from decimal import ROUND_HALF_UP, Decimal

import stripe
from django.conf import settings

from .base import (
    ConfirmacionInvalidaError,
    MetodoPagoNoHabilitadoError,
    ProveedorPagoBase,
    ProveedorPagoError,
    ResultadoInicioPago,
    ResultadoPago,
)


MONEDAS_SIN_DECIMALES = frozenset(
    {
        "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA",
        "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
    }
)
"""frozenset[str]: Monedas que Stripe cobra en unidades enteras (zero-decimal)."""

MONTO_MAXIMO_STRIPE = 99_999_999
"""int: Mayor importe, en unidades mínimas, que Stripe acepta en un cobro."""

ESTADOS_ACEPTADOS = frozenset({"succeeded", "processing", "requires_capture"})
"""frozenset[str]: Estados del PaymentIntent en los que el pago quedó aceptado."""

MENSAJES_RECHAZO = {
    "insufficient_funds": "La tarjeta no tiene fondos suficientes.",
    "card_declined": "La tarjeta fue rechazada por el emisor.",
    "generic_decline": "La tarjeta fue rechazada por el emisor.",
    "expired_card": "La tarjeta está vencida.",
    "incorrect_cvc": "El código de seguridad de la tarjeta es incorrecto.",
    "lost_card": "La tarjeta fue rechazada por el emisor.",
    "stolen_card": "La tarjeta fue rechazada por el emisor.",
    "processing_error": "El emisor no pudo procesar la tarjeta. Intentá nuevamente.",
}
"""dict[str, str]: Mensajes en español para los códigos de rechazo de Stripe."""

EVENTO_PAGO_APROBADO = "payment_intent.succeeded"
EVENTO_PAGO_RECHAZADO = "payment_intent.payment_failed"
"""str: Eventos del webhook de Stripe que informan el resultado de un pago."""

ESTADOS_INTENTO_RECHAZADO = frozenset({"requires_payment_method", "canceled"})
"""frozenset[str]: Estados de un PaymentIntent consultado que indican un rechazo."""

MENSAJE_RECHAZO_GENERICO = "El proveedor rechazó el pago."
MENSAJE_SIN_COMUNICACION = (
    "No pudimos comunicarnos con el proveedor de pagos. Intentá nuevamente más tarde."
)


def a_unidad_minima(monto, moneda_codigo):
    """Convierte un importe a la unidad mínima en que Stripe lo espera.

    Args:
        monto (decimal.Decimal): Importe expresado en la moneda.
        moneda_codigo (str): Código ISO de la moneda.

    Returns:
        int: Importe entero; guaraníes enteros para PYG y centavos para las
        monedas con decimales. Se redondea con ROUND_HALF_UP.
    """
    monto = Decimal(str(monto))
    if moneda_codigo.upper() in MONEDAS_SIN_DECIMALES:
        return int(monto.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int((monto * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def desde_unidad_minima(cantidad, moneda_codigo):
    """Convierte un importe en unidades mínimas de Stripe al importe en la moneda.

    Es la operación inversa de ``a_unidad_minima``.

    Args:
        cantidad (int): Importe tal como lo informa Stripe.
        moneda_codigo (str): Código ISO de la moneda.

    Returns:
        decimal.Decimal: Importe con dos decimales; guaraníes enteros para
        PYG y la conversión de centavos para las monedas con decimales.
    """
    unidades = Decimal(int(cantidad))
    if moneda_codigo.upper() in MONEDAS_SIN_DECIMALES:
        return unidades.quantize(Decimal("0.01"))
    return (unidades / 100).quantize(Decimal("0.01"))


def _como_dict(objeto):
    """Convierte un objeto de Stripe en un diccionario de Python.

    Desde stripe-python 15, ``StripeObject`` ya no se comporta como un
    diccionario (no admite ``.get``), así que se convierte con ``to_dict``.
    """
    return objeto.to_dict() if hasattr(objeto, "to_dict") else objeto


def _detalle_rechazo_intento(intento):
    """Describe el último error de pago de un PaymentIntent, si lo tiene."""

    error = intento.get("last_payment_error") or {}
    codigo = error.get("decline_code") or error.get("code") or ""
    mensaje = error.get("message") or ""
    return f"{codigo}: {mensaje}".strip(": ") or MENSAJE_RECHAZO_GENERICO


def _resultado_desde_intento(intento, aprobado):
    """Construye el resultado normalizado a partir de un PaymentIntent.

    Args:
        intento (dict): PaymentIntent de Stripe ya convertido a diccionario.
        aprobado (bool): Si el proveedor cobró el pago.

    Returns:
        ResultadoPago: Resultado con la referencia, el ``id_pago`` de la
        metadata, el importe y la moneda informados por Stripe.
    """
    metadata = intento.get("metadata") or {}
    id_pago = metadata.get("id_pago")
    moneda = (intento.get("currency") or "").upper() or None
    cantidad = intento.get("amount")
    return ResultadoPago(
        referencia_externa=intento["id"],
        aprobado=aprobado,
        id_pago=int(id_pago) if id_pago and str(id_pago).isdigit() else None,
        monto=desde_unidad_minima(cantidad, moneda) if cantidad is not None and moneda else None,
        moneda=moneda,
        detalle="" if aprobado else _detalle_rechazo_intento(intento),
    )


def mensaje_rechazo(error):
    """Traduce el motivo de rechazo de Stripe a un mensaje para el cliente.

    Args:
        error (stripe.CardError): Error devuelto por Stripe.

    Returns:
        str: Mensaje en español según el código de rechazo.
    """
    detalle = getattr(error, "error", None)
    decline_code = getattr(detalle, "decline_code", None)
    for codigo in (decline_code, error.code):
        if codigo in MENSAJES_RECHAZO:
            return MENSAJES_RECHAZO[codigo]
    return MENSAJE_RECHAZO_GENERICO


def _referencia_de_error(error):
    """Obtiene el PaymentIntent que Stripe adjunta a un pago rechazado, si existe."""

    detalle = getattr(error, "error", None)
    intento = getattr(detalle, "payment_intent", None)
    if intento is None:
        return ""
    if isinstance(intento, str):
        return intento
    return getattr(intento, "id", None) or _como_dict(intento).get("id", "")


class StripeProveedor(ProveedorPagoBase):
    """Cobra con tarjeta mediante un PaymentIntent confirmado desde el servidor.

    La tarjeta se identifica con el token ``pm_*`` guardado en el método de
    pago; nunca se envía ni se registra el número de la tarjeta. El resultado
    definitivo del cobro lo informa Stripe más tarde mediante un webhook.
    """

    codigo = "STRIPE"
    monedas_admitidas = None

    def validar(self, metodo_pago, monto, moneda_codigo):
        """Comprueba la configuración, el token de la tarjeta y el importe.

        Args:
            metodo_pago (pagos.models.MetodoPago): Tarjeta con la que se paga.
            monto (decimal.Decimal): Importe a cobrar.
            moneda_codigo (str): Código de la moneda del importe.

        Raises:
            MetodoPagoNoHabilitadoError: Si falta la clave de Stripe, la
                tarjeta no tiene token o el importe supera el máximo admitido.
        """
        super().validar(metodo_pago, monto, moneda_codigo)
        if not settings.STRIPE_SECRET_KEY:
            raise MetodoPagoNoHabilitadoError("El proveedor de pagos no está configurado.")
        if not metodo_pago.stripe_payment_method_id:
            raise MetodoPagoNoHabilitadoError(
                "Esta tarjeta no está habilitada para pagos en línea."
            )
        if a_unidad_minima(monto, moneda_codigo) > MONTO_MAXIMO_STRIPE:
            raise MetodoPagoNoHabilitadoError(
                "El importe supera el máximo admitido por el proveedor de pagos."
            )

    def monto_a_cobrar(self, monto, moneda_codigo):
        """Redondea el importe a la precisión que Stripe cobra en esa moneda.

        Args:
            monto (decimal.Decimal): Importe calculado para la operación.
            moneda_codigo (str): Código de la moneda del importe.

        Returns:
            decimal.Decimal: Guaraníes enteros para PYG, o centavos para las
            monedas con decimales.
        """
        unidades = Decimal(a_unidad_minima(monto, moneda_codigo))
        if moneda_codigo.upper() in MONEDAS_SIN_DECIMALES:
            return unidades.quantize(Decimal("0.01"))
        return (unidades / 100).quantize(Decimal("0.01"))

    def iniciar_pago(self, pago):
        """Crea y confirma el PaymentIntent del pago en Stripe.

        Args:
            pago (transacciones.models.Pago): Pago ya registrado, con su
                tarjeta, monto y moneda.

        Returns:
            ResultadoInicioPago: Identificador ``pi_...`` y estado del
            PaymentIntent.

        Raises:
            ProveedorPagoError: Si Stripe rechaza la tarjeta, si el pago
                requiere un paso que no se admite o si no hay comunicación con
                el proveedor.
        """
        try:
            intento = stripe.PaymentIntent.create(
                amount=a_unidad_minima(pago.monto, pago.moneda_id),
                currency=pago.moneda_id.lower(),
                payment_method=pago.metodo_pago.stripe_payment_method_id,
                confirm=True,
                automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
                description=f"Global Exchange - operación {pago.transaccion_id}",
                metadata={
                    "id_transaccion": str(pago.transaccion_id),
                    "id_pago": str(pago.id_pago),
                },
                api_key=settings.STRIPE_SECRET_KEY,
                idempotency_key=f"globalexchange-pago-{pago.id_pago}",
            )
        except stripe.CardError as error:
            raise ProveedorPagoError(
                mensaje_rechazo(error),
                rechazado=True,
                referencia_externa=_referencia_de_error(error),
                detalle=f"{error.code}: {error.user_message or ''}".strip(": "),
            ) from error
        except stripe.StripeError as error:
            raise ProveedorPagoError(
                MENSAJE_SIN_COMUNICACION,
                detalle=f"{type(error).__name__}: {error.user_message or error.code or ''}",
            ) from error

        if intento.status not in ESTADOS_ACEPTADOS:
            raise ProveedorPagoError(
                "El pago requiere un paso adicional que no está soportado.",
                rechazado=True,
                referencia_externa=intento.id,
                detalle=f"PaymentIntent en estado {intento.status}",
            )

        return ResultadoInicioPago(
            referencia_externa=intento.id,
            estado_proveedor=intento.status,
        )

    def interpretar_evento(self, payload, firma):
        """Valida una notificación del webhook de Stripe y extrae el resultado del pago.

        Args:
            payload (bytes): Cuerpo de la solicitud, sin modificar; la firma
                se calcula sobre estos bytes exactos.
            firma (str): Valor del encabezado ``Stripe-Signature``.

        Returns:
            ResultadoPago or None: Resultado del pago para los eventos
            ``payment_intent.succeeded`` y ``payment_intent.payment_failed``;
            None para cualquier otro evento, que no afecta a los pagos.

        Raises:
            ConfirmacionInvalidaError: Si falta el secreto del webhook, la
                firma no es válida o el contenido no es un evento de Stripe.
        """
        secreto = settings.STRIPE_WEBHOOK_SECRET
        if not secreto:
            raise ConfirmacionInvalidaError("El webhook de Stripe no está configurado.")
        try:
            evento = _como_dict(stripe.Webhook.construct_event(payload, firma, secreto))
        except (ValueError, stripe.SignatureVerificationError) as error:
            raise ConfirmacionInvalidaError(
                f"Notificación de Stripe inválida: {type(error).__name__}"
            ) from error

        tipo = evento.get("type")
        if tipo not in (EVENTO_PAGO_APROBADO, EVENTO_PAGO_RECHAZADO):
            return None
        try:
            intento = evento["data"]["object"]
            return _resultado_desde_intento(intento, aprobado=tipo == EVENTO_PAGO_APROBADO)
        except (KeyError, TypeError, ValueError) as error:
            raise ConfirmacionInvalidaError(
                "El evento de Stripe no contiene un PaymentIntent válido."
            ) from error

    def consultar_pago(self, pago):
        """Consulta en Stripe el resultado actual de un pago iniciado.

        Sirve como respaldo cuando el webhook no llegó.

        Args:
            pago (transacciones.models.Pago): Pago con referencia ``pi_...``.

        Returns:
            ResultadoPago or None: Resultado aprobado o rechazado, o None si
            Stripe todavía no tiene un resultado definitivo.

        Raises:
            ProveedorPagoError: Si no hay comunicación con Stripe.
        """
        try:
            intento = _como_dict(
                stripe.PaymentIntent.retrieve(
                    pago.referencia_externa,
                    api_key=settings.STRIPE_SECRET_KEY,
                )
            )
        except stripe.StripeError as error:
            raise ProveedorPagoError(
                MENSAJE_SIN_COMUNICACION,
                detalle=f"{type(error).__name__}: {error.user_message or error.code or ''}",
            ) from error

        estado = intento.get("status")
        if estado == "succeeded":
            return _resultado_desde_intento(intento, aprobado=True)
        if estado in ESTADOS_INTENTO_RECHAZADO:
            return _resultado_desde_intento(intento, aprobado=False)
        return None
