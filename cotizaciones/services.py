from decimal import Decimal, ROUND_HALF_UP

from .models import TasaCambio


PYG = "PYG"
DECIMAL_PLACES = Decimal("0.01")


class SimulacionConversionError(ValueError):
    pass


def redondear_monto(valor):
    return valor.quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def obtener_tasa_para_simulacion(moneda_origen, moneda_destino):
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
