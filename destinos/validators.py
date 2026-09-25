import re

from django.core.exceptions import ValidationError


def validar_numero_cuenta(valor):
    """Valida y normaliza el número de una cuenta bancaria.

    Acepta el número con espacios o guiones de separación, que se descartan
    antes de validarlo.

    Args:
        valor (str): Número de cuenta ingresado.

    Returns:
        str: Número de cuenta compuesto únicamente por dígitos.

    Raises:
        django.core.exceptions.ValidationError: Si el número contiene
            caracteres no numéricos o su longitud está fuera del rango
            admitido de 5 a 30 dígitos.
    """
    numero = re.sub(r"[ -]", "", valor or "")
    if not re.fullmatch(r"[0-9]{5,30}", numero):
        raise ValidationError("Ingresá un número de cuenta válido, de 5 a 30 dígitos.")
    return numero


def validar_documento_titular(valor):
    """Valida el documento de identidad o RUC del titular del destino.

    Args:
        valor (str): Documento ingresado, con o sin guiones.

    Returns:
        str: Documento normalizado, sin espacios.

    Raises:
        django.core.exceptions.ValidationError: Si el documento no respeta
            el formato de cédula o RUC admitido.
    """
    documento = re.sub(r"\s", "", valor or "")
    if not re.fullmatch(r"[0-9]{5,15}(-[0-9A-Za-z])?", documento):
        raise ValidationError("Ingresá una cédula o RUC válido, por ejemplo 1234567 o 80012345-6.")
    return documento
