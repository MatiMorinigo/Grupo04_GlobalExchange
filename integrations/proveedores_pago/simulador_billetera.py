"""Proveedor simulado para pagos con billeteras electrónicas."""

import uuid

from .base import ProveedorPagoBase, ResultadoInicioPago


class SimuladorBilleteraProveedor(ProveedorPagoBase):
    """Simula un proveedor de billeteras electrónicas (Tigo Money, Personal Pay, etc.).

    Las billeteras no tienen una pasarela real disponible, por lo que el
    simulador solo genera una referencia propia y deja el pago esperando su
    aprobación. Admite cualquier moneda: en una compra cobra guaraníes y en
    una venta la divisa de la operación.
    """

    codigo = "SIMULADOR_BILLETERA"
    monedas_admitidas = None

    def iniciar_pago(self, pago):
        """Genera la referencia del pago simulado.

        Args:
            pago (transacciones.models.Pago): Pago ya registrado.

        Returns:
            ResultadoInicioPago: Referencia ``SIM-...`` única y estado
            ``pendiente_aprobacion``.
        """
        return ResultadoInicioPago(
            referencia_externa=f"SIM-{uuid.uuid4().hex.upper()}",
            estado_proveedor="pendiente_aprobacion",
        )
