"""Alertas de arqueo cuando la diferencia supera la tolerancia (HU-32).

Flujo: ``cerrar_caja`` llama a :func:`evaluar_cierre` dentro de su transacción.
Si alguna moneda supera su tolerancia se registra la alerta en esa misma
transacción y el correo se envía después del commit, en un hilo aparte, de modo
que un fallo de correo o de Keycloak nunca revierte el cierre ni la alerta.
"""

import logging
import time
from decimal import Decimal
from threading import Thread

from django.conf import settings
from django.db import connection, transaction
from django.template.loader import render_to_string

from notificaciones.services import _abrir_conexion, _enviar

from .keycloak_service import KeycloakServiceError, obtener_usuarios_por_rol
from .models import (
    AlertaArqueo,
    DetalleAlertaArqueo,
    EnvioAlertaArqueo,
    ToleranciaArqueo,
)

logger = logging.getLogger(__name__)

ROLES_DESTINATARIOS = ("administrador", "tesorero")
TOLERANCIA_POR_DEFECTO = Decimal("0.00")


def detectar_excedidos(diferencias, tolerancias):
    """Devuelve las monedas cuya diferencia supera su tolerancia.

    Función pura: no accede a la base de datos ni al correo. La comparación es
    en valor absoluto (faltante y sobrante por igual) y estricta: una
    diferencia igual al límite no alerta. Una moneda sin tolerancia usa cero.

    Args:
        diferencias (dict[str, Decimal]): Diferencia de cada moneda.
        tolerancias (dict[str, Decimal]): Tolerancia configurada por moneda.

    Returns:
        list[dict]: Una entrada por moneda excedida, ordenada por código, con
        las claves ``moneda_id``, ``diferencia`` y ``tolerancia``.
    """
    excedidos = []
    for moneda_id in sorted(diferencias):
        diferencia = diferencias[moneda_id]
        tolerancia = tolerancias.get(moneda_id, TOLERANCIA_POR_DEFECTO)
        if abs(diferencia) > tolerancia:
            excedidos.append(
                {
                    "moneda_id": moneda_id,
                    "diferencia": diferencia,
                    "tolerancia": tolerancia,
                }
            )
    return excedidos


def evaluar_cierre(cierre, detalles):
    """Compara las diferencias de un cierre con las tolerancias y alerta.

    Debe llamarse dentro de la transacción del cierre. Si hay monedas
    excedidas crea la alerta con su detalle y programa el envío para después
    del commit.

    Args:
        cierre (CierreCaja): Cierre recién creado.
        detalles (Iterable[DetalleCierreCaja]): Detalle del cierre por moneda.

    Returns:
        AlertaArqueo or None: La alerta creada, o None si nada la requiere.
    """
    tolerancias = {
        t.moneda_id: t.monto_maximo for t in ToleranciaArqueo.objects.all()
    }
    diferencias = {d.moneda_id: d.diferencia for d in detalles}
    excedidos = detectar_excedidos(diferencias, tolerancias)
    if not excedidos:
        return None

    alerta = AlertaArqueo.objects.create(cierre=cierre)
    DetalleAlertaArqueo.objects.bulk_create(
        [
            DetalleAlertaArqueo(
                alerta=alerta,
                moneda_id=item["moneda_id"],
                diferencia=item["diferencia"],
                tolerancia_aplicada=item["tolerancia"],
            )
            for item in excedidos
        ]
    )
    _programar_envio(alerta.pk)
    return alerta


def _programar_envio(alerta_id):
    """Lanza el envío en un hilo cuando la transacción se confirme."""
    hilo = Thread(
        target=_enviar_en_segundo_plano, args=(alerta_id,), daemon=True
    )
    transaction.on_commit(hilo.start, robust=True)


def _enviar_en_segundo_plano(alerta_id):
    """Ejecuta el envío dentro de un hilo y libera su conexión a la base."""
    try:
        enviar_alerta(alerta_id)
    except Exception:
        # Frontera del hilo: si no se registra aquí, el error se pierde.
        logger.exception("Error inesperado al enviar la alerta %s.", alerta_id)
    finally:
        connection.close()


def obtener_destinatarios():
    """Reúne los correos de administradores y tesoreros habilitados.

    Descarta usuarios sin correo y elimina duplicados por correo; si una
    persona tiene ambos roles se conserva el primero de ``ROLES_DESTINATARIOS``.

    Returns:
        list[dict]: Elementos con las claves ``email`` y ``rol``.

    Raises:
        KeycloakServiceError: Si no se pudo consultar Keycloak.
    """
    vistos = set()
    destinatarios = []
    for rol in ROLES_DESTINATARIOS:
        for usuario in obtener_usuarios_por_rol(rol):
            email = (usuario.get("email") or "").strip()
            if not email or email.lower() in vistos:
                continue
            vistos.add(email.lower())
            destinatarios.append({"email": email, "rol": rol})
    return destinatarios


def construir_mensaje(alerta):
    """Arma el asunto y el cuerpo del correo de una alerta.

    Returns:
        tuple[str, str]: Asunto y cuerpo en texto plano.
    """
    cierre = alerta.cierre
    caja = cierre.apertura.caja
    asunto = (
        f"Alerta de arqueo: diferencia sobre la tolerancia en "
        f"{caja.nombre} (cierre #{cierre.pk})"
    )
    cuerpo = render_to_string(
        "cajas/alerta_arqueo.txt",
        {
            "alerta": alerta,
            "cierre": cierre,
            "caja": caja,
            "sucursal": caja.sucursal,
            "cajero": cierre.apertura.asignacion.cajero_username,
            "detalles": alerta.detalles.select_related("moneda"),
        },
    )
    return asunto, cuerpo


def enviar_alerta(alerta_id):
    """Envía la alerta a administradores y tesoreros y registra cada envío.

    Si Keycloak falla, o no hay destinatarios, deja un único envío fallido con
    el motivo; la alerta ya existe y queda disponible para consulta.
    Entre un correo y el siguiente espera ``NOTIFICACIONES_PAUSA_ENVIO``.

    Returns:
        list[EnvioAlertaArqueo]: Envíos registrados.
    """
    alerta = AlertaArqueo.objects.select_related(
        "cierre__apertura__caja__sucursal", "cierre__apertura__asignacion"
    ).get(pk=alerta_id)

    try:
        destinatarios = obtener_destinatarios()
    except KeycloakServiceError as error:
        motivo = str(error.__cause__ or error)
        logger.error("No se pudo obtener los destinatarios de la alerta %s: %s",
                     alerta_id, motivo)
        return [_registrar_fallo(alerta, f"Keycloak: {motivo}")]

    if not destinatarios:
        return [_registrar_fallo(alerta, "No hay administradores ni tesoreros con correo.")]

    asunto, cuerpo = construir_mensaje(alerta)
    conexion, error_conexion = _abrir_conexion()

    envios = []
    for indice, destinatario in enumerate(destinatarios):
        if conexion and indice:
            time.sleep(settings.NOTIFICACIONES_PAUSA_ENVIO)
        error = error_conexion or _enviar(
            conexion, asunto, cuerpo, destinatario["email"]
        )
        envios.append(
            EnvioAlertaArqueo.objects.create(
                alerta=alerta,
                email=destinatario["email"],
                rol=destinatario["rol"],
                estado=(
                    EnvioAlertaArqueo.Estado.FALLIDA
                    if error
                    else EnvioAlertaArqueo.Estado.ENVIADA
                ),
                error=error,
            )
        )

    if conexion:
        conexion.close()
    return envios


def _registrar_fallo(alerta, motivo):
    return EnvioAlertaArqueo.objects.create(
        alerta=alerta,
        email="",
        rol="",
        estado=EnvioAlertaArqueo.Estado.FALLIDA,
        error=motivo,
    )
