from django.contrib import admin

from .models import Pago, Transaccion


class PagoInline(admin.TabularInline):
    """Muestra los intentos de pago dentro de la consulta de una transaccion."""

    model = Pago
    extra = 0
    can_delete = False
    fields = (
        "id_pago",
        "creado_en",
        "proveedor",
        "referencia_externa",
        "monto",
        "moneda",
        "estado",
        "mensaje_proveedor",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        """Impide registrar pagos manualmente desde el administrador."""

        return False


@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    """Expone las transacciones como registros historicos de solo lectura."""

    list_display = (
        "id_transaccion",
        "creada_en",
        "cliente",
        "tipo_operacion",
        "moneda",
        "monto_divisa",
        "tasa_aplicada",
        "comision_monto_pyg",
        "total_pyg",
        "estado",
    )
    list_filter = ("tipo_operacion", "estado", "moneda")
    search_fields = (
        "=id_transaccion",
        "cliente__nombre",
        "cliente__ruc",
        "moneda__codigo",
    )
    date_hierarchy = "creada_en"
    list_select_related = ("cliente", "moneda", "tasa_cambio", "creada_por")
    readonly_fields = [field.name for field in Transaccion._meta.fields]
    inlines = [PagoInline]

    def has_add_permission(self, request):
        """Impide crear transacciones manualmente desde el administrador."""

        return False

    def has_delete_permission(self, request, obj=None):
        """Impide eliminar transacciones y preserva su trazabilidad."""

        return False

    def has_change_permission(self, request, obj=None):
        """Impide modificar una transaccion desde la consulta administrativa."""

        return False


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    """Expone los intentos de pago como registros historicos de solo lectura."""

    list_display = (
        "id_pago",
        "creado_en",
        "transaccion",
        "proveedor",
        "referencia_externa",
        "monto",
        "moneda",
        "estado",
    )
    list_filter = ("proveedor", "estado", "moneda")
    search_fields = (
        "=id_pago",
        "=transaccion__id_transaccion",
        "referencia_externa",
        "transaccion__cliente__nombre",
    )
    date_hierarchy = "creado_en"
    list_select_related = ("transaccion", "moneda")
    readonly_fields = [field.name for field in Pago._meta.fields]

    def has_add_permission(self, request):
        """Impide registrar pagos manualmente desde el administrador."""

        return False

    def has_delete_permission(self, request, obj=None):
        """Impide eliminar pagos y preserva su trazabilidad."""

        return False

    def has_change_permission(self, request, obj=None):
        """Impide modificar un pago desde la consulta administrativa."""

        return False
