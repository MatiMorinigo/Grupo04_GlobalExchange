"""Aperturas e interfaz transaccional para futuros movimientos y cierres."""

from contextlib import contextmanager
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.keycloak import obtener_claims_verificados
from .models import (
    AperturaCaja, AsignacionCaja, Caja, DenominacionBillete,
    DetalleInventarioInicial, Sucursal,
)

MAX_LINEAS_INVENTARIO = 100


class AperturaCajaError(ValidationError):
    """Conflicto de negocio que las vistas pueden mostrar sin producir un 500."""


def obtener_cajero_autenticado(request):
    """Obtiene el UUID sub y exige el rol cajero del mismo token verificado."""
    if not request.user.is_authenticated:
        raise PermissionDenied("Debe iniciar sesión como cajero.")
    claims = obtener_claims_verificados(request)
    realm = claims.get("realm_access")
    roles = realm.get("roles") if isinstance(realm, dict) else None
    if not isinstance(roles, list) or "cajero" not in roles:
        raise PermissionDenied("Se requiere el rol cajero de Keycloak.")
    try:
        return UUID(claims["sub"])
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise PermissionDenied("El token no contiene un identificador de cajero válido.") from error


def asignaciones_vigentes(cajero_id):
    ahora = timezone.now()
    return AsignacionCaja.objects.filter(
        cajero_keycloak_id=cajero_id, fecha_inicio__lte=ahora, fecha_fin__gt=ahora,
    ).select_related("caja__sucursal")


def abrir_caja(*, request, asignacion_id, inventario):
    """Abre una caja con líneas {denominacion_id: int, cantidad: int}.

    Valida otra vez todos los datos dentro de la transacción; no acepta
    identidad, fechas, monedas, valores ni totales provenientes del cliente.
    Una lista no vacía con cantidades cero es un inventario válido.
    """
    cajero_id = obtener_cajero_autenticado(request)
    if not isinstance(inventario, (list, tuple)) or not 1 <= len(inventario) <= MAX_LINEAS_INVENTARIO:
        raise AperturaCajaError("Registre entre 1 y 100 líneas de inventario.")
    ids = []
    for linea in inventario:
        if not isinstance(linea, dict):
            raise AperturaCajaError("Línea de inventario inválida.")
        denominacion_id, cantidad = linea.get("denominacion_id"), linea.get("cantidad")
        if type(denominacion_id) is not int or denominacion_id <= 0:
            raise AperturaCajaError("Seleccione una denominación válida.")
        if type(cantidad) is not int or not 0 <= cantidad <= 2147483647:
            raise AperturaCajaError("La cantidad debe ser un entero no negativo válido.")
        ids.append(denominacion_id)
    if len(set(ids)) != len(ids):
        raise AperturaCajaError("No repita denominaciones dentro del inventario.")

    try:
        with transaction.atomic():
            # Apertura: Asignación → Caja → Sucursal → catálogo/monedas.
            # Movimientos/cierres: Caja → Apertura (no necesitan Asignación).
            try:
                asignacion = AsignacionCaja.objects.select_for_update().get(pk=asignacion_id)
            except AsignacionCaja.DoesNotExist as error:
                raise AperturaCajaError("La asignación no existe.") from error
            if asignacion.cajero_keycloak_id != cajero_id:
                raise AperturaCajaError("No está asignado a esta caja.")
            caja = Caja.objects.select_for_update().get(pk=asignacion.caja_id)
            sucursal = Sucursal.objects.select_for_update().get(pk=caja.sucursal_id)
            if not caja.activa or not sucursal.activa:
                raise AperturaCajaError("La caja y su sucursal deben estar activas.")
            if AperturaCaja.objects.filter(caja=caja, estado=AperturaCaja.Estado.ABIERTA).exists():
                raise AperturaCajaError("La caja ya tiene una apertura activa.")
            # Bloquea el catálogo y las monedas para mantener los valores validados.
            denominaciones = {
                d.pk: d for d in DenominacionBillete.objects.select_for_update()
                .select_related("moneda").filter(pk__in=ids).order_by("pk")
            }
            if len(denominaciones) != len(ids) or any(
                not d.activa or not d.moneda.activa or d.valor <= 0
                for d in denominaciones.values()
            ):
                raise AperturaCajaError("El inventario contiene denominaciones o monedas no habilitadas.")
            # La hora se toma después de adquirir los bloqueos, no al recibir el POST.
            ahora = timezone.now()
            if not asignacion.fecha_inicio <= ahora < asignacion.fecha_fin:
                raise AperturaCajaError("La asignación no está vigente en este horario.")
            apertura = AperturaCaja.objects.create(
                caja=caja, asignacion=asignacion, cajero_keycloak_id=cajero_id,
                fecha_apertura=ahora,
            )
            for linea in inventario:
                denominacion = denominaciones[linea["denominacion_id"]]
                detalle = DetalleInventarioInicial(
                    apertura=apertura, denominacion=denominacion,
                    moneda=denominacion.moneda, valor_denominacion=denominacion.valor,
                    cantidad=linea["cantidad"],
                )
                detalle.full_clean()
                detalle.save()
            return apertura
    except IntegrityError as error:
        restriccion = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
        if restriccion == "caja_apertura_activa_unica":
            raise AperturaCajaError("La caja ya tiene una apertura activa.") from error
        raise


def obtener_apertura_activa(caja_id):
    """Consulta una apertura o rechaza la operación. No aplica el horario del turno.

    Para ESCRIBIR movimientos usar ``apertura_para_movimiento``; esta consulta
    sola no conserva un bloqueo frente al cierre concurrente.
    """
    try:
        return AperturaCaja.objects.get(caja_id=caja_id, estado=AperturaCaja.Estado.ABIERTA)
    except AperturaCaja.DoesNotExist as error:
        raise AperturaCajaError("La caja no tiene una apertura activa.") from error


@contextmanager
def apertura_para_movimiento(caja_id):
    """Mantiene una transacción y bloquea Caja → Apertura durante el movimiento.

    Dev 4 debe guardar el movimiento dentro del ``with`` y referenciar la
    apertura devuelta. El cierre debe adquirir los mismos bloqueos en ese orden.
    Este contrato no reemplaza permisos, arqueo ni validación del saldo disponible.
    """
    with transaction.atomic():
        try:
            Caja.objects.select_for_update().get(pk=caja_id)
        except Caja.DoesNotExist as error:
            raise AperturaCajaError("La caja no existe.") from error
        apertura = obtener_apertura_activa(caja_id)
        apertura = AperturaCaja.objects.select_for_update().get(pk=apertura.pk)
        if apertura.estado != AperturaCaja.Estado.ABIERTA:
            raise AperturaCajaError("La caja no tiene una apertura activa.")
        yield apertura
