"""Proveedor simulado para pagos con billeteras electrónicas."""

import uuid

from .base import ProveedorPagoBase, ResultadoInicioPago, ResultadoPago


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

    def resultado_simulado(self, pago, aprobado, usuario=None):
        """Construye la respuesta de la billetera simulada para un pago.

        Representa lo que informaría el proveedor real cuando el titular
        aprueba o rechaza el pago en su billetera. En el sistema, esa decisión
        la toma un analista cambiario o un administrador.

        Args:
            pago (transacciones.models.Pago): Pago del simulador a resolver.
            aprobado (bool): Si el pago se aprueba.
            usuario (django.contrib.auth.models.User or None): Usuario que
                resolvió el pago, para dejar constancia en el detalle.

        Returns:
            ResultadoPago: Resultado con la referencia, el monto y la moneda
            del propio pago.
        """
        detalle = ""
        if not aprobado:
            detalle = "Rechazado en el simulador de billetera"
            if usuario is not None:
                detalle += f" por {usuario.get_username()}"
            detalle += "."
        return ResultadoPago(
            referencia_externa=pago.referencia_externa,
            aprobado=aprobado,
            id_pago=pago.id_pago,
            monto=pago.monto,
            moneda=pago.moneda_id,
            detalle=detalle,
        )
