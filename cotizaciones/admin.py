from django.contrib import admin

from .models import AuditoriaMoneda, Moneda, TasaCambio


@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    """Configura el listado, el filtro de actividad y la búsqueda de monedas."""
    list_display = ("codigo", "nombre", "simbolo", "activa")
    list_filter = ("activa",)
    search_fields = ("codigo", "nombre")


@admin.register(AuditoriaMoneda)
class AuditoriaMonedaAdmin(admin.ModelAdmin):
    """Expone en solo lectura la auditoría de creación, modificación y deshabilitación de monedas."""
    list_display = ("moneda", "accion", "realizado_por", "fecha")
    list_filter = ("accion",)
    search_fields = ("moneda__codigo", "moneda__nombre")
    readonly_fields = [field.name for field in AuditoriaMoneda._meta.fields]

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
            obj (AuditoriaMoneda or None): Registro sobre el que se consulta
                el permiso, si corresponde.

        Returns:
            bool: False siempre, ya que la auditoría debe permanecer inalterada.
        """
        return False


@admin.register(TasaCambio)
class TasaCambioAdmin(admin.ModelAdmin):
    """Configura la consulta administrativa de tasas por monedas y vigencia."""
    list_display = (
        "moneda_origen",
        "moneda_destino",
        "precio_compra",
        "precio_venta",
        "vigente",
        "fecha_vigencia",
    )
    list_filter = ("vigente", "moneda_origen", "moneda_destino")
    search_fields = ("moneda_origen__codigo", "moneda_destino__codigo")
