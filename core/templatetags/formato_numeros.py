from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def formato_numero(valor, max_decimales=2):
    """Formatea un número con miles en punto y hasta N decimales con coma."""
    if valor is None or valor == "":
        return ""

    try:
        decimales = max(0, int(max_decimales))
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return valor

    if not numero.is_finite():
        return valor

    numero_formateado = f"{numero:,.{decimales}f}"
    if decimales:
        numero_formateado = numero_formateado.rstrip("0").rstrip(".")

    return numero_formateado.replace(",", "_").replace(".", ",").replace("_", ".")
