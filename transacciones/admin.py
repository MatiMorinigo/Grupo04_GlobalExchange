from django.contrib import admin

from .models import Transaccion


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

    def has_add_permission(self, request):
        """Impide crear transacciones manualmente desde el administrador."""

        return False

    def has_delete_permission(self, request, obj=None):
        """Impide eliminar transacciones y preserva su trazabilidad."""

        return False

    def has_change_permission(self, request, obj=None):
        """Impide modificar una transaccion desde la consulta administrativa."""

        return False
