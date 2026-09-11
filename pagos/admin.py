from django.contrib import admin

from .models import AuditoriaMetodoPago, MetodoPago


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    """Configura el listado, el filtro de estado y la búsqueda de métodos de pago."""
    list_display = ("cliente", "tipo", "ultimos_cuatro_digitos", "titular", "activo")
    list_filter = ("tipo", "activo")
    search_fields = ("cliente__nombre", "cliente__ruc", "titular", "ultimos_cuatro_digitos")


@admin.register(AuditoriaMetodoPago)
class AuditoriaMetodoPagoAdmin(admin.ModelAdmin):
    """Expone en solo lectura la auditoría de altas, modificaciones, bajas y eliminaciones de métodos de pago."""
    list_display = ("metodo_pago", "accion", "realizado_por", "fecha")
    list_filter = ("accion",)
    search_fields = ("metodo_pago__cliente__nombre", "metodo_pago__cliente__ruc")
    readonly_fields = [field.name for field in AuditoriaMetodoPago._meta.fields]

    def has_add_permission(self, request):
        """Impide crear registros de auditoría manualmente desde el admin.

        Args:
            request (django.http.HttpRequest): Solicitud administrativa actual.

        Returns:
            bool: False siempre, ya que los registros solo se crean por código.
        """
        return False

    def has_change_permission(self, request, obj=None):
        """Impide modificar registros de auditoría existentes.

        Args:
            request (django.http.HttpRequest): Solicitud administrativa actual.
            obj (AuditoriaMetodoPago or None): Registro sobre el que se
                consulta el permiso, si corresponde.

        Returns:
            bool: False siempre, ya que la auditoría debe permanecer inalterada.
        """
        return False
