from calendar import monthrange
from datetime import datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from transacciones.models import EstadoTransaccion, Transaccion

from .models import CategoriaCliente, Cliente, ConfiguracionVIP


def calcular_fin_vigencia_vip(fecha_referencia, duracion_meses):
    """Calcula el último día del período VIP temporal."""

    inicio_mes = fecha_referencia.replace(day=1)

    indice_mes = inicio_mes.month - 1 + duracion_meses - 1
    anio = inicio_mes.year + indice_mes // 12
    mes = indice_mes % 12 + 1

    ultimo_dia = monthrange(anio, mes)[1]

    return inicio_mes.replace(
        year=anio,
        month=mes,
        day=ultimo_dia,
    )


def evaluar_vip_temporal(fecha_referencia=None):
    """
    Evalúa el volumen de operaciones del mes anterior y asigna o renueva
    el VIP temporal a los clientes que alcancen el umbral configurado.
    """

    if fecha_referencia is None:
        fecha_referencia = timezone.localdate()

    configuracion = ConfiguracionVIP.obtener()

    # Un umbral en cero indica que la promoción todavía no fue configurada.
    if configuracion.umbral_mensual_pyg <= 0:
        return {
            "evaluados": 0,
            "actualizados": 0,
        }

    inicio_mes_actual = fecha_referencia.replace(day=1)
    ultimo_dia_mes_anterior = inicio_mes_actual - timedelta(days=1)
    inicio_mes_anterior = ultimo_dia_mes_anterior.replace(day=1)

    zona_horaria = timezone.get_current_timezone()

    desde = timezone.make_aware(
        datetime.combine(inicio_mes_anterior, time.min),
        zona_horaria,
    )

    hasta = timezone.make_aware(
        datetime.combine(inicio_mes_actual, time.min),
        zona_horaria,
    )

    volumenes = (
        Transaccion.objects
        .filter(
            estado=EstadoTransaccion.COMPLETADA,
            completada_en__gte=desde,
            completada_en__lt=hasta,
        )
        .values("cliente_id")
        .annotate(volumen=Sum("subtotal_pyg"))
    )

    volumen_por_cliente = {
        registro["cliente_id"]: registro["volumen"]
        for registro in volumenes
    }

    fecha_fin_vip = calcular_fin_vigencia_vip(
        inicio_mes_actual,
        configuracion.duracion_meses,
    )

    clientes = Cliente.objects.exclude(
        categoria=CategoriaCliente.VIP
    )

    actualizados = 0

    for cliente in clientes:
        volumen = volumen_por_cliente.get(cliente.id_cliente, 0)

        if volumen >= configuracion.umbral_mensual_pyg:
            cliente.vip_vigente_hasta = fecha_fin_vip
            cliente.save(update_fields=["vip_vigente_hasta"])
            actualizados += 1

    return {
        "evaluados": clientes.count(),
        "actualizados": actualizados,
    }