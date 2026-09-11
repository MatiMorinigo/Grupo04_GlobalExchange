import re
from datetime import date

from django.core.exceptions import ValidationError

REGEX_VENCIMIENTO = re.compile(r"^(0[1-9]|1[0-2])/(\d{2})$")


def validar_formato_vencimiento(valor):
    """Valida que la fecha de vencimiento respete el formato MM/AA.

    Args:
        valor (str): Fecha de vencimiento ingresada.

    Raises:
        django.core.exceptions.ValidationError: Si el valor no respeta el
            formato MM/AA.
    """
    if not REGEX_VENCIMIENTO.match(valor or ""):
        raise ValidationError("Usá el formato MM/AA.")


def validar_vencimiento_no_vencido(valor):
    """Valida que la tarjeta no esté ya vencida.

    Args:
        valor (str): Fecha de vencimiento en formato MM/AA.

    Raises:
        django.core.exceptions.ValidationError: Si el formato es inválido o
            si el mes/año ya pasó respecto de la fecha actual.
    """
    validar_formato_vencimiento(valor)
    mes_str, anio_str = valor.split("/")
    mes = int(mes_str)
    anio = 2000 + int(anio_str)
    hoy = date.today()
    if (anio, mes) < (hoy.year, hoy.month):
        raise ValidationError("La tarjeta ya está vencida.")


def validar_numero_tarjeta(numero):
    """Valida el formato de un número de tarjeta y lo verifica con el algoritmo de Luhn.

    Args:
        numero (str): Número de tarjeta ingresado, con o sin espacios.

    Returns:
        str: Número de tarjeta sin espacios, ya validado.

    Raises:
        django.core.exceptions.ValidationError: Si el número no tiene un
            formato válido o no pasa la verificación de Luhn.
    """
    numero_limpio = (numero or "").replace(" ", "")
    if not numero_limpio.isdigit() or not (13 <= len(numero_limpio) <= 19):
        raise ValidationError("Ingresá un número de tarjeta válido.")
    if not _luhn_valido(numero_limpio):
        raise ValidationError("El número de tarjeta no es válido.")
    return numero_limpio


def _luhn_valido(numero):
    """Verifica un número de tarjeta con el algoritmo de Luhn.

    Args:
        numero (str): Cadena compuesta únicamente por dígitos.

    Returns:
        bool: True si el número satisface el checksum de Luhn.
    """
    digitos = [int(digito) for digito in reversed(numero)]
    total = 0
    for indice, digito in enumerate(digitos):
        if indice % 2 == 1:
            digito *= 2
            if digito > 9:
                digito -= 9
        total += digito
    return total % 10 == 0


def validar_numero_billetera(valor):
    """Valida y normaliza el celular asociado; acepta prefijo internacional."""
    numero = re.sub(r"[ ()-]", "", valor or "")
    if not re.fullmatch(r"\+?[0-9]{7,15}", numero):
        raise ValidationError("Ingresá un celular válido, de 7 a 15 dígitos, con prefijo internacional opcional.")
    return numero
