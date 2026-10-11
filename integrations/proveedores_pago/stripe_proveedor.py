"""Proveedor de pagos con tarjeta a través de Stripe (PaymentIntents)."""

from decimal import ROUND_HALF_UP, Decimal

import stripe
from django.conf import settings

from .base import (
    MetodoPagoNoHabilitadoError,
    ProveedorPagoBase,
    ProveedorPagoError,
    ResultadoInicioPago,
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
    return getattr(intento, "id", "") or intento.get("id", "")


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
