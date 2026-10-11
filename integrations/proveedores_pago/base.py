"""Interfaz común de los proveedores externos que procesan pagos."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ResultadoInicioPago:
    """Respuesta de un proveedor que aceptó procesar un pago.

    Attributes:
        referencia_externa (str): Identificador del pago en el proveedor,
            que permite reconocerlo cuando llegue su confirmación.
        estado_proveedor (str): Estado informado por el proveedor, tal como
            lo devuelve (por ejemplo, ``succeeded`` en Stripe).
    """

    referencia_externa: str
    estado_proveedor: str


class MetodoPagoNoHabilitadoError(Exception):
    """Indica que el método de pago no puede usarse con el proveedor.

    Se lanza antes de contactar al proveedor, por lo que no genera ningún
    intento de pago.
    """


class ProveedorPagoError(Exception):
    """Indica que el proveedor rechazó el pago o no pudo procesarlo.

    Args:
        mensaje_usuario (str): Explicación apta para mostrar al cliente.
        rechazado (bool): True si el proveedor rechazó el pago (por ejemplo,
            una tarjeta declinada); False si no pudo procesarlo.
        referencia_externa (str): Identificador del intento en el proveedor,
            si llegó a generarse.
        detalle (str): Información técnica para el registro del pago. Nunca
            contiene datos de la tarjeta.
    """

    def __init__(self, mensaje_usuario, *, rechazado=False, referencia_externa="", detalle=""):
        super().__init__(mensaje_usuario)
        self.mensaje_usuario = mensaje_usuario
        self.rechazado = rechazado
        self.referencia_externa = referencia_externa
        self.detalle = detalle


class ProveedorPagoBase(ABC):
    """Define cómo se valida e inicia un pago ante un proveedor externo.

    Attributes:
        codigo (str): Valor de ``transacciones.models.ProveedorPago`` que
            identifica al proveedor en los pagos registrados.
        monedas_admitidas (frozenset[str] or None): Códigos de moneda que el
            proveedor puede cobrar, o None si admite cualquiera.
    """

    codigo = ""
    monedas_admitidas = None

    def validar(self, metodo_pago, monto, moneda_codigo):
        """Comprueba que el pago pueda enviarse al proveedor.

        Args:
            metodo_pago (pagos.models.MetodoPago): Método con el que se paga.
            monto (decimal.Decimal): Importe a cobrar.
            moneda_codigo (str): Código de la moneda del importe.

        Raises:
            MetodoPagoNoHabilitadoError: Si el proveedor no admite la moneda
                o el método no reúne los datos que el proveedor necesita.
        """
        if self.monedas_admitidas is not None and moneda_codigo not in self.monedas_admitidas:
            raise MetodoPagoNoHabilitadoError(
                f"El método de pago seleccionado no admite pagos en {moneda_codigo}."
            )

    def monto_a_cobrar(self, monto, moneda_codigo):
        """Ajusta el importe a la precisión con la que el proveedor cobra.

        Args:
            monto (decimal.Decimal): Importe calculado para la operación.
            moneda_codigo (str): Código de la moneda del importe.

        Returns:
            decimal.Decimal: Importe que efectivamente se cobrará.
        """
        return monto

    @abstractmethod
    def iniciar_pago(self, pago):
        """Envía el pago al proveedor.

        Args:
            pago (transacciones.models.Pago): Pago ya registrado, con su
                método, monto y moneda.

        Returns:
            ResultadoInicioPago: Referencia y estado informados por el
            proveedor cuando acepta la solicitud.

        Raises:
            ProveedorPagoError: Si el proveedor rechaza el pago o no puede
                procesarlo.
        """
