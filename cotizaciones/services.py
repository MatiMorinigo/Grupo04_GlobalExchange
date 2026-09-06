from decimal import Decimal, ROUND_HALF_UP

from .models import TasaCambio


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


def obtener_tasa_para_simulacion(moneda_origen, moneda_destino):
    """Selecciona la tasa vigente para una conversión que incluya guaraníes.

    Normaliza los códigos a mayúsculas. Utiliza el precio de compra para
    convertir a PYG y el precio de venta para convertir desde PYG, buscando
    en ambos casos el par registrado como moneda extranjera/PYG.

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
            .filter(moneda_origen_id=origen, moneda_destino_id=PYG, vigente=True)
            .first()
        )
        if not tasa:
            raise SimulacionConversionError("No existe una tasa vigente para el par seleccionado.")

        return tasa, tasa.precio_compra, "compra"

    if origen == PYG:
        tasa = (
            TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
            .filter(moneda_origen_id=destino, moneda_destino_id=PYG, vigente=True)
            .first()
        )
        if not tasa:
            raise SimulacionConversionError("No existe una tasa vigente para el par seleccionado.")

        return tasa, tasa.precio_venta, "venta"

    raise SimulacionConversionError("La simulación debe incluir guaraníes como moneda de origen o destino.")


def simular_conversion(moneda_origen, moneda_destino, monto):
    """Calcula una conversión monetaria sin guardar una operación.

    Multiplica por el precio de compra al convertir a PYG y divide por el
    precio de venta al convertir desde PYG. Redondea los importes a dos
    decimales y devuelve descuentos de valor cero.

    Args:
        moneda_origen (str): Código de la moneda que se entrega.
        moneda_destino (str): Código de la moneda que se recibe.
        monto (decimal.Decimal or str or int or float): Importe positivo
            expresado en la moneda de origen.

    Returns:
        dict: Códigos normalizados, monto de origen, identificador y par de
        la tasa, tipo y precio aplicado, subtotal, descuentos, total final,
        mensaje de descuento y fecha de vigencia.

    Raises:
        SimulacionConversionError: Si el monto no es positivo, las monedas
            coinciden, el par no incluye PYG o no hay una tasa vigente.
        decimal.InvalidOperation: Si el monto no admite conversión decimal
            o una operación decimal es inválida con el contexto activo.
        decimal.DivisionByZero: Si se convierte desde PYG con precio de
            venta cero y la excepción está habilitada en el contexto decimal.
    """
    origen = moneda_origen.upper()
    destino = moneda_destino.upper()
    monto_decimal = Decimal(str(monto))

    if monto_decimal <= 0:
        raise SimulacionConversionError("El monto debe ser mayor a cero.")

    tasa, tasa_aplicada, tipo_tasa = obtener_tasa_para_simulacion(origen, destino)

    if destino == PYG:
        subtotal = monto_decimal * tasa_aplicada
    else:
        subtotal = monto_decimal / tasa_aplicada

    descuento_monto = Decimal("0.00")
    total_final = redondear_monto(subtotal - descuento_monto)

    return {
        "moneda_origen": origen,
        "moneda_destino": destino,
        "monto_origen": redondear_monto(monto_decimal),
        "tasa_id": tasa.id_tasa,
        "par_tasa": f"{tasa.moneda_origen_id}/{tasa.moneda_destino_id}",
        "tipo_tasa": tipo_tasa,
        "tasa_aplicada": tasa_aplicada,
        "subtotal": redondear_monto(subtotal),
        "descuento_porcentaje": Decimal("0.00"),
        "descuento_monto": descuento_monto,
        "total_final": total_final,
        "mensaje_descuento": "Sin descuento configurado para esta simulación.",
        "fecha_vigencia": tasa.fecha_vigencia,
    }
