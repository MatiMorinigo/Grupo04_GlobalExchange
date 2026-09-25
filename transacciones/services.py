from decimal import Decimal

from django.db import transaction as db_transaction

from cotizaciones.models import ConfiguracionComision, TasaCambio
from cotizaciones.services import (
    SimulacionConversionError,
    obtener_beneficio_categoria,
    redondear_monto,
)

from .models import TipoOperacion, Transaccion


PYG = "PYG"
CIEN = Decimal("100")


class OperacionCambiariaError(ValueError):
    """Indica que una operación cambiaria no puede calcularse o registrarse."""
    pass


def obtener_tasa_vigente_compra(moneda_codigo):
    """Obtiene la tasa vigente del par entre una divisa y el guaraní.

    Solo considera tasas marcadas como vigentes cuyas dos monedas estén
    habilitadas, con el mismo criterio que utiliza el simulador de
    conversiones.

    Args:
        moneda_codigo (str): Código de la moneda extranjera de la operación.

    Returns:
        cotizaciones.models.TasaCambio: Tasa vigente del par divisa/PYG.

    Raises:
        OperacionCambiariaError: Si la moneda es el guaraní o si no existe
            una tasa vigente para el par requerido.
    """
    codigo = (moneda_codigo or "").upper()

    if codigo == PYG:
        raise OperacionCambiariaError("La operación debe involucrar una moneda extranjera.")

    tasa = (
        TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
        .filter(
            moneda_origen_id=codigo,
            moneda_destino_id=PYG,
            vigente=True,
            moneda_origen__activa=True,
            moneda_destino__activa=True,
        )
        .first()
    )

    if not tasa:
        raise OperacionCambiariaError(
            "No existe una cotización vigente para la moneda seleccionada."
        )

    return tasa


def calcular_compra(cliente, moneda_codigo, monto_divisa, tasa=None):
    """Calcula los importes de una compra de divisas para un cliente.

    El cliente entrega guaraníes y recibe la moneda extranjera indicada, por
    lo que se aplica el precio de venta de la cotización vigente. Sobre el
    subtotal se descuenta el beneficio correspondiente a la categoría del
    cliente, acotado por su límite configurado, y se suma la comisión de
    compra vigente en el sistema.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        moneda_codigo (str): Código de la moneda extranjera a comprar.
        monto_divisa (decimal.Decimal or str or int): Cantidad de divisa que
            el cliente desea adquirir.
        tasa (cotizaciones.models.TasaCambio or None): Tasa a utilizar. Si
            se omite, se busca la vigente para el par.

    Returns:
        dict: Importes y condiciones de la operación, con las claves que
        necesita el modelo Transaccion para registrarse.

    Raises:
        OperacionCambiariaError: Si el monto no es positivo, si no hay una
            cotización vigente o si la categoría del cliente no tiene
            configuración de beneficios.
    """
    monto = Decimal(str(monto_divisa))

    if monto <= 0:
        raise OperacionCambiariaError("El monto de la operación debe ser mayor a cero.")

    if tasa is None:
        tasa = obtener_tasa_vigente_compra(moneda_codigo)

    tasa_aplicada = tasa.precio_venta
    subtotal_pyg = redondear_monto(monto * tasa_aplicada)

    try:
        configuracion = obtener_beneficio_categoria(cliente.categoria)
    except SimulacionConversionError as error:
        raise OperacionCambiariaError(str(error)) from error

    beneficio_porcentaje = Decimal("0.00")
    limite_beneficio_pyg = Decimal("0.00")

    if configuracion:
        beneficio_porcentaje = configuracion.porcentaje_beneficio
        limite_beneficio_pyg = configuracion.limite_mensual_pyg

    # Un límite en cero desactiva el beneficio, igual que en el simulador.
    if beneficio_porcentaje == 0 or limite_beneficio_pyg == 0:
        monto_beneficiado_pyg = Decimal("0.00")
        beneficio_monto_pyg = Decimal("0.00")
    else:
        monto_beneficiado_pyg = min(subtotal_pyg, limite_beneficio_pyg)
        beneficio_monto_pyg = redondear_monto(
            monto_beneficiado_pyg * beneficio_porcentaje / CIEN
        )

    comision_porcentaje = ConfiguracionComision.obtener().porcentaje_compra
    comision_monto_pyg = redondear_monto(subtotal_pyg * comision_porcentaje / CIEN)

    total_pyg = redondear_monto(subtotal_pyg - beneficio_monto_pyg + comision_monto_pyg)

    return {
        "tipo_operacion": TipoOperacion.COMPRA,
        "moneda": tasa.moneda_origen,
        "tasa_cambio": tasa,
        "tasa_aplicada": tasa_aplicada,
        "fecha_vigencia_tasa": tasa.fecha_vigencia,
        "monto_divisa": redondear_monto(monto),
        "subtotal_pyg": subtotal_pyg,
        "categoria_aplicada": cliente.categoria,
        "beneficio_porcentaje": beneficio_porcentaje,
        "limite_beneficio_pyg": redondear_monto(limite_beneficio_pyg),
        "monto_beneficiado_pyg": redondear_monto(monto_beneficiado_pyg),
        "beneficio_monto_pyg": beneficio_monto_pyg,
        "comision_porcentaje": comision_porcentaje,
        "comision_monto_pyg": comision_monto_pyg,
        "total_pyg": total_pyg,
    }


def crear_transaccion_compra(
    cliente,
    usuario,
    moneda_codigo,
    monto_divisa,
    destino=None,
    metodo_pago=None,
    tasa=None,
):
    """Registra una compra de divisas en estado pendiente.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        usuario (django.contrib.auth.models.User): Usuario que la registra.
        moneda_codigo (str): Código de la moneda extranjera a comprar.
        monto_divisa (decimal.Decimal): Cantidad de divisa a adquirir.
        destino (destinos.models.DestinoAcreditacion or None): Destino donde
            se acreditará la divisa, si el cliente ya lo eligió.
        metodo_pago (pagos.models.MetodoPago or None): Medio con el que el
            cliente abonará la operación.
        tasa (cotizaciones.models.TasaCambio or None): Cotización a aplicar.
            Si se omite, se toma la vigente para el par.

    Returns:
        Transaccion: Transacción creada en estado pendiente.

    Raises:
        OperacionCambiariaError: Si los datos de la operación no permiten
            calcularla.
        django.core.exceptions.ValidationError: Si la transacción resultante
            no supera las validaciones del modelo.
    """
    with db_transaction.atomic():
        calculo = calcular_compra(cliente, moneda_codigo, monto_divisa, tasa=tasa)
        transaccion = Transaccion(
            cliente=cliente,
            creada_por=usuario,
            destino_acreditacion=destino,
            metodo_pago=metodo_pago,
            **calculo,
        )
        transaccion.full_clean()
        transaccion.save()

    return transaccion
