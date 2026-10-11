"""Proveedores externos de pago y elección del proveedor según el método de pago.

``get_proveedor`` es el único punto que decide qué proveedor procesa cada
tipo de método de pago.
"""

from pagos.models import TipoMetodoPago

from .base import (
    ConfirmacionInvalidaError,
    MetodoPagoNoHabilitadoError,
    ProveedorPagoBase,
    ProveedorPagoError,
    ResultadoInicioPago,
    ResultadoPago,
)
from .simulador_billetera import SimuladorBilleteraProveedor
from .stripe_proveedor import StripeProveedor


_PROVEEDORES_POR_TIPO = {
    TipoMetodoPago.TARJETA_CREDITO: StripeProveedor,
    TipoMetodoPago.TARJETA_DEBITO: StripeProveedor,
    TipoMetodoPago.BILLETERA_ELECTRONICA: SimuladorBilleteraProveedor,
}


def get_proveedor(metodo_pago):
    """Devuelve el proveedor que procesa los pagos de un método de pago.

    Args:
        metodo_pago (pagos.models.MetodoPago): Método elegido para pagar.

    Returns:
        ProveedorPagoBase: Stripe para tarjetas de crédito y débito, o el
        simulador para billeteras electrónicas.

    Raises:
        MetodoPagoNoHabilitadoError: Si el tipo de método no tiene un
            proveedor de pagos asociado.
    """
    clase = _PROVEEDORES_POR_TIPO.get(metodo_pago.tipo)
    if clase is None:
        raise MetodoPagoNoHabilitadoError("No se puede iniciar el pago con este método.")
    return clase()


__all__ = [
    "ConfirmacionInvalidaError",
    "MetodoPagoNoHabilitadoError",
    "ProveedorPagoBase",
    "ProveedorPagoError",
    "ResultadoInicioPago",
    "ResultadoPago",
    "SimuladorBilleteraProveedor",
    "StripeProveedor",
    "get_proveedor",
]
