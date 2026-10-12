"""Aperturas e interfaz transaccional para futuros movimientos y cierres."""

from contextlib import contextmanager
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, DatabaseError, transaction
from django.utils import timezone

from decimal import Decimal
from core.keycloak import obtener_claims_verificados, tiene_rol
from cotizaciones.models import Moneda
from .models import (
    AperturaCaja, AsignacionCaja, Caja, DenominacionBillete,
    DetalleInventarioInicial, Sucursal, Remesa, DetalleRemesa,
    CierreCaja, DetalleCierreCaja, ConteoBilleteCierre,
)
from .alertas import evaluar_cierre

MAX_LINEAS_INVENTARIO = 100


class AperturaCajaError(ValidationError):
    """Conflicto de negocio que las vistas pueden mostrar sin producir un 500."""


class CierreCajaError(ValidationError):
    """Error al procesar el cierre y arqueo de caja (HU-37)."""


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


# ---------------------------------------------------------------------------
# Remesas de Efectivo (HU-36)
# ---------------------------------------------------------------------------

class RemesaError(ValidationError):
    """Error de regla de negocio o validación al registrar una remesa."""


def registrar_remesa(
    *,
    request=None,
    usuario=None,
    caja_id=None,
    tipo=None,
    moneda_id=None,
    desglose=None,
    observaciones="",
):
    """Registra una remesa (entrega o devolución) entre Tesorería y una caja (HU-36).

    Valida:

    - Permisos: tesorero o administrador.
    - Caja y apertura activa con bloqueo transaccional concurrente.
    - Moneda y denominaciones válidas y activas.
    - En caso de devolución (egreso de caja), que no supere el saldo disponible
      ni el inventario de billetes de esa denominación.
    - Registra origen, destino, usuario responsable, fecha y hora real.
    """
    if request is not None:
        if not request.user or not request.user.is_authenticated:
            raise PermissionDenied("Debe iniciar sesión para operar.")
        if not (
            tiene_rol(request, "tesorero")
            or tiene_rol(request, "administrador")
            or request.user.is_superuser
        ):
            raise PermissionDenied("Solo los tesoreros o administradores pueden registrar remesas.")
        usuario = request.user
    elif usuario is None:
        raise RemesaError("Se requiere un usuario responsable.")

    if not caja_id:
        raise RemesaError("Debe seleccionar una caja.")

    if tipo not in (Remesa.Tipo.ENTREGA, Remesa.Tipo.DEVOLUCION):
        raise RemesaError("Tipo de remesa inválido.")

    if not moneda_id:
        raise RemesaError("Debe seleccionar una moneda.")

    try:
        moneda = Moneda.objects.get(pk=moneda_id, activa=True)
    except Moneda.DoesNotExist as err:
        raise RemesaError("La moneda seleccionada no existe o no está activa.") from err

    if not desglose or not isinstance(desglose, list):
        raise RemesaError("Debe indicar el desglose de billetes de la remesa.")

    if len(desglose) > MAX_LINEAS_INVENTARIO:
        raise RemesaError(f"El desglose no puede superar {MAX_LINEAS_INVENTARIO} líneas.")

    # Validar denominaciones y cantidades
    denominaciones_ids = []
    lineas_limpias = []
    for item in desglose:
        if not isinstance(item, dict) or "denominacion_id" not in item or "cantidad" not in item:
            raise RemesaError("Línea de desglose inválida.")
        try:
            d_id = int(item["denominacion_id"])
            cantidad = int(item["cantidad"])
        except (ValueError, TypeError):
            raise RemesaError("Denominación o cantidad inválida en el desglose.")
        if cantidad <= 0:
            raise RemesaError("La cantidad de billetes en cada línea debe ser mayor a cero.")
        denominaciones_ids.append(d_id)
        lineas_limpias.append((d_id, cantidad))

    if len(set(denominaciones_ids)) != len(denominaciones_ids):
        raise RemesaError("No repita denominaciones dentro del desglose de la remesa.")

    denominaciones_map = {
        d.pk: d
        for d in DenominacionBillete.objects.filter(
            pk__in=denominaciones_ids, activa=True, moneda=moneda
        )
    }

    if len(denominaciones_map) != len(denominaciones_ids):
        raise RemesaError("El desglose contiene denominaciones que no existen, no están activas o no pertenecen a la moneda seleccionada.")

    monto_total = Decimal("0.00")
    desglose_procesado = []
    for d_id, cantidad in lineas_limpias:
        denom = denominaciones_map[d_id]
        subtotal = denom.valor * cantidad
        monto_total += subtotal
        desglose_procesado.append({
            "denominacion": denom,
            "cantidad": cantidad,
            "subtotal": subtotal,
        })

    if monto_total <= 0:
        raise RemesaError("El monto total de la remesa debe ser mayor a cero.")

    # Adquirir bloqueos y validar caja con apertura_para_movimiento
    try:
        with apertura_para_movimiento(caja_id) as apertura:
            if tipo == Remesa.Tipo.DEVOLUCION:
                # Criterio 6: El sistema no debe permitir registrar egresos superiores al efectivo disponible.
                saldo_disponible = apertura.obtener_saldo_actual(moneda.pk)
                if monto_total > saldo_disponible:
                    raise RemesaError(
                        f"El monto a devolver ({moneda.codigo} {monto_total}) supera el saldo disponible en caja ({moneda.codigo} {saldo_disponible})."
                    )

                inventario_actual = apertura.obtener_inventario_actual(moneda_id=moneda.pk)
                for item in desglose_procesado:
                    denom = item["denominacion"]
                    cant_pedida = item["cantidad"]
                    stock_disp = inventario_actual.get(denom.pk, {}).get("cantidad", 0)
                    if cant_pedida > stock_disp:
                        raise RemesaError(
                            f"La cantidad de billetes de {denom.valor} a devolver ({cant_pedida}) supera la cantidad disponible en el inventario de la caja ({stock_disp})."
                        )

            # Determinar origen y destino
            if tipo == Remesa.Tipo.ENTREGA:
                origen = "Tesorería"
                destino = f"Caja {apertura.caja.codigo} - {apertura.caja.nombre}"
            else:
                origen = f"Caja {apertura.caja.codigo} - {apertura.caja.nombre}"
                destino = "Tesorería"

            remesa = Remesa.objects.create(
                caja=apertura.caja,
                apertura=apertura,
                tipo=tipo,
                origen=origen,
                destino=destino,
                moneda=moneda,
                monto_total=monto_total,
                usuario_responsable=usuario,
                observaciones=observaciones or "",
            )

            detalles = [
                DetalleRemesa(
                    remesa=remesa,
                    denominacion=item["denominacion"],
                    valor_denominacion=item["denominacion"].valor,
                    cantidad=item["cantidad"],
                )
                for item in desglose_procesado
            ]
            DetalleRemesa.objects.bulk_create(detalles)

            return remesa
    except AperturaCajaError as error:
        raise RemesaError(str(error)) from error


def cerrar_caja(
    request=None,
    apertura_id=None,
    conteo_billetes=None,
    observaciones="",
    usuario=None,
):
    """Registra el cierre y arqueo de caja (HU-37).

    Criterios de aceptación:
    - Permite cerrar únicamente una caja que tenga una apertura activa.
    - El cajero debe ingresar el conteo físico final por moneda y denominación.
    - Calcula el saldo físico final a partir del conteo ingresado.
    - Calcula el saldo teórico utilizando la apertura y los movimientos (remesas).
    - Compara el saldo teórico con el saldo físico identificando faltantes o sobrantes.
    - Conserva el saldo teórico, el saldo físico y la diferencia obtenida.
    - Una caja cerrada no debe aceptar nuevos movimientos correspondientes a ese turno.
    - Registra fecha, hora y usuario responsable.
    """
    if request is not None:
        if not request.user or not request.user.is_authenticated:
            raise PermissionDenied("Debe iniciar sesión para operar.")
        usuario = request.user
        cajero_id = obtener_cajero_autenticado(request)
    elif usuario is None:
        raise CierreCajaError("Se requiere un usuario responsable.")
    else:
        cajero_id = None

    if not apertura_id:
        raise CierreCajaError("Debe especificar la apertura de caja a cerrar.")

    if not conteo_billetes or not isinstance(conteo_billetes, (list, tuple)):
        raise CierreCajaError("Debe ingresar el conteo físico de billetes.")

    if len(conteo_billetes) > MAX_LINEAS_INVENTARIO:
        raise CierreCajaError(f"El conteo no puede superar {MAX_LINEAS_INVENTARIO} líneas.")

    # Validar formato de líneas de conteo
    conteo_limpio = []
    denominaciones_ids = []
    for item in conteo_billetes:
        if not isinstance(item, dict) or "denominacion_id" not in item or "cantidad" not in item:
            raise CierreCajaError("Línea de conteo inválida.")
        try:
            d_id = int(item["denominacion_id"])
            cant = int(item["cantidad"])
        except (ValueError, TypeError):
            raise CierreCajaError("Denominación o cantidad inválida en el conteo.")
        if cant < 0:
            raise CierreCajaError("La cantidad de billetes no puede ser negativa.")
        denominaciones_ids.append(d_id)
        conteo_limpio.append((d_id, cant))

    if len(set(denominaciones_ids)) != len(denominaciones_ids):
        raise CierreCajaError("No repita denominaciones dentro del conteo físico.")

    try:
        with transaction.atomic():
            # Bloquear la apertura y verificar estado
            try:
                apertura = AperturaCaja.objects.select_for_update().select_related("caja__sucursal").get(pk=apertura_id)
            except AperturaCaja.DoesNotExist as err:
                raise CierreCajaError("La apertura de caja no existe.") from err

            # Criterio 1: El sistema debe permitir cerrar únicamente una caja que tenga una apertura activa.
            if apertura.estado != AperturaCaja.Estado.ABIERTA:
                raise CierreCajaError("Solo se puede cerrar una caja con apertura activa. Esta caja ya se encuentra cerrada.")

            if hasattr(apertura, "cierre"):
                raise CierreCajaError("Esta apertura ya cuenta con un cierre registrado.")

            # Si vino cajero_id por request, verificar que la apertura pertenezca a ese cajero
            if cajero_id and apertura.cajero_keycloak_id != cajero_id:
                raise PermissionDenied("No tiene permisos para cerrar la apertura de otro cajero.")

            # Bloquear catálogo de denominaciones
            denominaciones_map = {
                d.pk: d
                for d in DenominacionBillete.objects.select_for_update()
                .select_related("moneda")
                .filter(pk__in=denominaciones_ids, activa=True, moneda__activa=True)
            }
            if len(denominaciones_map) != len(denominaciones_ids):
                raise CierreCajaError("El conteo contiene denominaciones no válidas o inactivas.")

            # Criterio 3: El sistema debe calcular el saldo físico final a partir del conteo ingresado.
            saldos_fisicos = {}
            conteos_a_crear = []
            for d_id, cant in conteo_limpio:
                denom = denominaciones_map[d_id]
                m_id = denom.moneda_id
                subtotal = denom.valor * cant
                saldos_fisicos[m_id] = saldos_fisicos.get(m_id, Decimal("0.00")) + subtotal
                conteos_a_crear.append({
                    "denominacion": denom,
                    "valor_denominacion": denom.valor,
                    "cantidad": cant,
                })

            # Criterio 4: El sistema debe calcular el saldo teórico utilizando la apertura y los movimientos realizados durante la jornada.
            saldos_teoricos = apertura.saldos_actuales

            # Unir todas las monedas involucradas
            todas_monedas_ids = set(saldos_teoricos.keys()).union(set(saldos_fisicos.keys()))

            ahora = timezone.now()

            # Criterio 9: El cierre debe registrar fecha, hora y usuario responsable.
            cierre = CierreCaja.objects.create(
                apertura=apertura,
                fecha_cierre=ahora,
                usuario_responsable=usuario,
                observaciones=observaciones or "",
            )

            # Criterios 5, 6, 7:
            # - Comparar saldo teórico con saldo físico.
            # - Identificar y registrar faltante o sobrante (diferencia = físico - teórico).
            # - El cierre debe conservar saldo teórico, saldo físico y diferencia obtenida.
            detalles_cierre = []
            for m_id in sorted(todas_monedas_ids):
                teorico = saldos_teoricos.get(m_id, Decimal("0.00"))
                fisico = saldos_fisicos.get(m_id, Decimal("0.00"))
                dif = fisico - teorico
                detalles_cierre.append(
                    DetalleCierreCaja(
                        cierre=cierre,
                        moneda_id=m_id,
                        saldo_teorico=teorico,
                        saldo_fisico=fisico,
                        diferencia=dif,
                    )
                )
            DetalleCierreCaja.objects.bulk_create(detalles_cierre)

            # HU-32: comparar cada diferencia con la tolerancia de su moneda y
            # registrar la alerta en esta misma transacción.
            evaluar_cierre(cierre, detalles_cierre)

            # Guardar conteo físico de billetes
            conteos_objs = [
                ConteoBilleteCierre(
                    cierre=cierre,
                    denominacion=item["denominacion"],
                    valor_denominacion=item["valor_denominacion"],
                    cantidad=item["cantidad"],
                )
                for item in conteos_a_crear
            ]
            ConteoBilleteCierre.objects.bulk_create(conteos_objs)

            # Criterio 8: Una caja cerrada no debe aceptar nuevos movimientos correspondientes a ese turno.
            apertura.estado = AperturaCaja.Estado.CERRADA
            apertura.fecha_cierre = ahora
            apertura.save(update_fields=["estado", "fecha_cierre"])

            return cierre
    except (IntegrityError, DatabaseError) as error:
        raise CierreCajaError("Error al registrar el cierre de caja.") from error


