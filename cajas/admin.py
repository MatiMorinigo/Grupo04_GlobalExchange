from django.contrib import admin

from .models import (
    DenominacionBillete, Remesa, DetalleRemesa,
    CierreCaja, DetalleCierreCaja, ConteoBilleteCierre,
    ToleranciaArqueo, AlertaArqueo, DetalleAlertaArqueo, EnvioAlertaArqueo,
)


@admin.register(DenominacionBillete)
class DenominacionBilleteAdmin(admin.ModelAdmin):
    """Catálogo controlado por los permisos administrativos de Django."""

    list_display = ("moneda", "valor", "activa")
    list_filter = ("moneda", "activa")
    ordering = ("moneda", "valor")


class DetalleRemesaInline(admin.TabularInline):
    model = DetalleRemesa
    extra = 0
    readonly_fields = ("valor_denominacion", "subtotal")


@admin.register(Remesa)
class RemesaAdmin(admin.ModelAdmin):
    list_display = (
        "id_remesa", "tipo", "caja", "moneda", "monto_total",
        "origen", "destino", "usuario_responsable", "fecha_hora",
    )
    list_filter = ("tipo", "moneda", "caja", "fecha_hora")
    search_fields = ("caja__nombre", "origen", "destino", "usuario_responsable__username")
    readonly_fields = ("fecha_hora",)
    inlines = [DetalleRemesaInline]


@admin.register(ToleranciaArqueo)
class ToleranciaArqueoAdmin(admin.ModelAdmin):
    list_display = ("moneda", "monto_maximo", "fecha_modificacion", "modificado_por")
    readonly_fields = ("fecha_modificacion", "modificado_por")


class DetalleAlertaArqueoInline(admin.TabularInline):
    model = DetalleAlertaArqueo
    extra = 0
    can_delete = False
    readonly_fields = ("moneda", "diferencia", "tolerancia_aplicada")


class EnvioAlertaArqueoInline(admin.TabularInline):
    model = EnvioAlertaArqueo
    extra = 0
    can_delete = False
    readonly_fields = ("email", "rol", "estado", "error", "fecha_envio")


@admin.register(AlertaArqueo)
class AlertaArqueoAdmin(admin.ModelAdmin):
    list_display = ("id_alerta", "cierre", "fecha_creacion")
    list_filter = ("fecha_creacion",)
    readonly_fields = ("cierre", "fecha_creacion")
    inlines = [DetalleAlertaArqueoInline, EnvioAlertaArqueoInline]


class DetalleCierreCajaInline(admin.TabularInline):
    model = DetalleCierreCaja
    extra = 0
    readonly_fields = ("moneda", "saldo_teorico", "saldo_fisico", "diferencia", "estado_arqueo")


class ConteoBilleteCierreInline(admin.TabularInline):
    model = ConteoBilleteCierre
    extra = 0
    readonly_fields = ("denominacion", "valor_denominacion", "cantidad", "subtotal")


@admin.register(CierreCaja)
class CierreCajaAdmin(admin.ModelAdmin):
    list_display = ("id_cierre", "apertura", "caja", "fecha_cierre", "usuario_responsable", "hay_diferencias")
    list_filter = ("fecha_cierre", "apertura__caja")
    search_fields = ("apertura__caja__nombre", "usuario_responsable__username")
    readonly_fields = ("fecha_cierre",)
    inlines = [DetalleCierreCajaInline, ConteoBilleteCierreInline]


