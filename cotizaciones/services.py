from decimal import Decimal, ROUND_HALF_UP

from .models import TasaCambio

from clientes.models import ConfiguracionBeneficioCategoria


PYG = "PYG"
DECIMAL_PLACES = Decimal("0.01")


class SimulacionConversionError(ValueError):
    """Indica que los datos o las tasas disponibles impiden simular la conversión."""
    pass


def redondear_monto(valor):
    """Redondea un importe a dos decimales mediante ROUND_HALF_UP.

    Args:
        valor (decimal.Decimal): Importe que se desea redondear.

    Returns:
        decimal.Decimal: Importe cuantizado a centésimas.

    Raises:
        decimal.InvalidOperation: Si el valor no puede cuantizarse con
            el contexto decimal activo y la excepción está habilitada.
    """
    return valor.quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)

def obtener_beneficio_categoria(categoria):
    """
    Obtiene la configuración de beneficio asociada a una categoría.

    Args:
        categoria (str or None): Categoría del cliente.

    Returns:
        ConfiguracionBeneficioCategoria or None: Configuración encontrada.
        Si no se proporciona categoría, retorna None.

    Raises:
        SimulacionConversionError: Si la categoría no posee una
            configuración de beneficios.
    """
    if not categoria:
        return None

    configuracion = ConfiguracionBeneficioCategoria.objects.filter(
        categoria=categoria
    ).first()

    if not configuracion:
        raise SimulacionConversionError(
            "No existe configuración de beneficios para la categoría seleccionada."
        )

    return configuracion

def obtener_tasa_para_simulacion(moneda_origen, moneda_destino):
    """Selecciona la tasa vigente para una conversión que incluya guaraníes.

    Normaliza los códigos a mayúsculas. Utiliza el precio de compra para
    convertir a PYG y el precio de venta para convertir desde PYG, buscando
    en ambos casos el par registrado como moneda extranjera/PYG. Solo
    considera tasas cuyas dos monedas estén habilitadas (activa=True).

    Args:
        moneda_origen (str): Código de la moneda que se entrega.
        moneda_destino (str): Código de la moneda que se recibe.

    Returns:
        tuple[TasaCambio, decimal.Decimal, str]: Registro de tasa, precio
        aplicable y tipo de operación, compra o venta.

    Raises:
        SimulacionConversionError: Si las monedas coinciden, ninguna es PYG
            o no existe una tasa vigente para el par requerido.
    """
    origen = moneda_origen.upper()
    destino = moneda_destino.upper()

    if origen == destino:
        raise SimulacionConversionError("La moneda de origen y destino deben ser distintas.")

    if destino == PYG:
        tasa = (
            TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
            .filter(
                moneda_origen_id=origen,
                moneda_destino_id=PYG,
                vigente=True,
                moneda_origen__activa=True,
                moneda_destino__activa=True,
            )
            .first()
        )
        if not tasa:
            raise SimulacionConversionError("No existe una tasa vigente para el par seleccionado.")

        return tasa, tasa.precio_compra, "compra"

    if origen == PYG:
        tasa = (
            TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
            .filter(
                moneda_origen_id=destino,
                moneda_destino_id=PYG,
                vigente=True,
                moneda_origen__activa=True,
                moneda_destino__activa=True,
            )
            .first()
        )
        if not tasa:
            raise SimulacionConversionError("No existe una tasa vigente para el par seleccionado.")

        return tasa, tasa.precio_venta, "venta"

    raise SimulacionConversionError("La simulación debe incluir guaraníes como moneda de origen o destino.")


def simular_conversion(moneda_origen, moneda_destino, monto, categoria=None):
    """
    Calcula una conversión monetaria sin registrar una transacción.

    Si se proporciona una categoría de cliente, aplica el beneficio
    configurado hasta el límite mensual disponible. Como se trata de una
    simulación, el límite no se consume ni se modifica en la base de datos.

    Args:
        moneda_origen (str): Código de la moneda entregada.
        moneda_destino (str): Código de la moneda recibida.
        monto (Decimal or str or int or float): Monto a convertir.
        categoria (str or None): Categoría del cliente utilizada para
            determinar el beneficio aplicable.

    Returns:
        dict: Resultado detallado de la simulación.

    Raises:
        SimulacionConversionError: Si los datos de la conversión no son válidos.
    """
    origen = moneda_origen.upper()
    destino = moneda_destino.upper()
    monto_decimal = Decimal(str(monto))

    if monto_decimal <= 0:
        raise SimulacionConversionError("El monto debe ser mayor a cero.")

    tasa, tasa_aplicada, tipo_tasa = obtener_tasa_para_simulacion(
        origen,
        destino,
    )

    configuracion = obtener_beneficio_categoria(categoria)

    porcentaje_beneficio = Decimal("0.00")
    limite_mensual_pyg = Decimal("0.00")

    if configuracion:
        porcentaje_beneficio = configuracion.porcentaje_beneficio
        limite_mensual_pyg = configuracion.limite_mensual_pyg

    porcentaje_decimal = porcentaje_beneficio / Decimal("100")

    # Sin beneficio: comportamiento original.
    if not configuracion or porcentaje_beneficio == 0 or limite_mensual_pyg == 0:
        if destino == PYG:
            subtotal = monto_decimal * tasa_aplicada
        else:
            subtotal = monto_decimal / tasa_aplicada

        return {
            "moneda_origen": origen,
            "moneda_destino": destino,
            "monto_origen": redondear_monto(monto_decimal),
            "tasa_id": tasa.id_tasa,
            "par_tasa": f"{tasa.moneda_origen_id}/{tasa.moneda_destino_id}",
            "tipo_tasa": tipo_tasa,
            "tasa_aplicada": tasa_aplicada,
            "subtotal": redondear_monto(subtotal),
            "beneficio_porcentaje": porcentaje_beneficio,
            "beneficio_monto": Decimal("0.00"),
            "monto_beneficiado_pyg": Decimal("0.00"),
            "limite_mensual_pyg": limite_mensual_pyg,
            "total_final": redondear_monto(subtotal),
            "mensaje_beneficio": "Sin beneficio aplicable.",
            "fecha_vigencia": tasa.fecha_vigencia,
        }

    # Cliente vende divisa y recibe PYG.
    if destino == PYG:
        subtotal = monto_decimal * tasa_aplicada

        monto_beneficiado_pyg = min(
            subtotal,
            limite_mensual_pyg,
        )

        beneficio_monto = monto_beneficiado_pyg * porcentaje_decimal
        total_final = subtotal + beneficio_monto

    # Cliente compra divisa entregando PYG.
    else:
        subtotal = monto_decimal / tasa_aplicada

        monto_beneficiado_pyg = min(
            monto_decimal,
            limite_mensual_pyg,
        )

        monto_normal_pyg = monto_decimal - monto_beneficiado_pyg

        tasa_preferencial = tasa_aplicada * (
            Decimal("1") - porcentaje_decimal
        )

        total_con_beneficio = (
            monto_beneficiado_pyg / tasa_preferencial
        )

        total_sin_beneficio = (
            monto_normal_pyg / tasa_aplicada
        )

        total_final = total_con_beneficio + total_sin_beneficio
        beneficio_monto = total_final - subtotal

    if monto_beneficiado_pyg < (
        subtotal if destino == PYG else monto_decimal
    ):
        mensaje = (
            "El beneficio se aplicó parcialmente hasta alcanzar "
            "el límite mensual configurado."
        )
    else:
        mensaje = "El beneficio se aplicó a la totalidad de la simulación."

    return {
        "moneda_origen": origen,
        "moneda_destino": destino,
        "monto_origen": redondear_monto(monto_decimal),
        "tasa_id": tasa.id_tasa,
        "par_tasa": f"{tasa.moneda_origen_id}/{tasa.moneda_destino_id}",
        "tipo_tasa": tipo_tasa,
        "tasa_aplicada": tasa_aplicada,
        "subtotal": redondear_monto(subtotal),
        "beneficio_porcentaje": porcentaje_beneficio,
        "beneficio_monto": redondear_monto(beneficio_monto),
        "monto_beneficiado_pyg": redondear_monto(monto_beneficiado_pyg),
        "limite_mensual_pyg": redondear_monto(limite_mensual_pyg),
        "total_final": redondear_monto(total_final),
        "mensaje_beneficio": mensaje,
        "fecha_vigencia": tasa.fecha_vigencia,
    }