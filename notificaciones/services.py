import logging
import time
from smtplib import SMTPException
from threading import Thread

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage, get_connection
from django.db import connection, transaction
from django.template.loader import render_to_string

from .models import EstadoNotificacion, Notificacion

logger = logging.getLogger(__name__)

ERRORES_DE_ENVIO = (SMTPException, OSError)


def notificar_al_confirmar(tasa):
    """Programa la notificación de una tasa para cuando su transacción se confirme.

    El envío se lanza después del commit y en un hilo aparte, por lo que no
    puede revertir la tasa ni demorar la respuesta a quien la publicó.

    Args:
        tasa (cotizaciones.models.TasaCambio): Tasa vigente recién publicada.
    """
    hilo = Thread(target=_notificar_en_segundo_plano, args=(tasa,), daemon=True)
    transaction.on_commit(hilo.start, robust=True)


def _notificar_en_segundo_plano(tasa):
    """Ejecuta la notificación dentro de un hilo y libera su conexión a la base.

    Args:
        tasa (cotizaciones.models.TasaCambio): Tasa vigente recién publicada.
    """
    try:
        notificar_cambio_tasa(tasa)
    except Exception:
        # Frontera del hilo: si no se registra aquí, el error se pierde.
        logger.exception("Error inesperado al notificar la tasa %s.", tasa)
    finally:
        connection.close()


def notificar_cambio_tasa(tasa):
    """Envía por correo la tasa publicada a los usuarios activos con correo.

    Registra cada notificación apenas se intenta su envío, con el resultado.
    Si no se puede conectar con el servidor de correo, todas quedan como fallidas.
    Entre un correo y el siguiente espera NOTIFICACIONES_PAUSA_ENVIO segundos.

    Args:
        tasa (cotizaciones.models.TasaCambio): Tasa vigente recién publicada.

    Returns:
        list[Notificacion]: Notificaciones registradas, una por destinatario.
    """
    usuarios = get_user_model().objects.filter(is_active=True).exclude(email="")
    if not usuarios:
        return []

    asunto = f"Cotización actualizada: {tasa}"
    cuerpo = render_to_string("notificaciones/cambio_tasa.txt", {"tasa": tasa})
    conexion, error_conexion = _abrir_conexion()

    notificaciones = []
    for indice, usuario in enumerate(usuarios):
        if conexion and indice:
            time.sleep(settings.NOTIFICACIONES_PAUSA_ENVIO)
        error = error_conexion or _enviar(conexion, asunto, cuerpo, usuario.email)
        notificaciones.append(
            Notificacion.objects.create(
                usuario=usuario,
                tasa=tasa,
                email=usuario.email,
                precio_compra=tasa.precio_compra,
                precio_venta=tasa.precio_venta,
                estado=EstadoNotificacion.FALLIDA if error else EstadoNotificacion.ENVIADA,
                error=error,
            )
        )

    if conexion:
        conexion.close()
    return notificaciones


def _abrir_conexion():
    """Abre la conexión con el servidor de correo.

    Returns:
        tuple[BaseEmailBackend or None, str]: Conexión abierta y error vacío,
        o None y el detalle del error si no se pudo conectar.
    """
    conexion = get_connection()
    try:
        conexion.open()
    except ERRORES_DE_ENVIO as exc:
        logger.exception("No se pudo conectar con el servidor de correo.")
        return None, str(exc)
    return conexion, ""


def _enviar(conexion, asunto, cuerpo, email):
    """Envía un correo por la conexión indicada.

    Returns:
        str: Detalle del error, o cadena vacía si el correo fue enviado.
    """
    try:
        EmailMessage(asunto, cuerpo, to=[email], connection=conexion).send()
    except ERRORES_DE_ENVIO as exc:
        logger.exception("No se pudo enviar el correo a %s.", email)
        return str(exc)
    return ""
