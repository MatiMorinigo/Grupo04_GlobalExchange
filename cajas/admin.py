from django.contrib import admin

from .models import DenominacionBillete, Remesa, DetalleRemesa


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

