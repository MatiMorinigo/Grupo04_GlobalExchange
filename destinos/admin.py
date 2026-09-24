from django.contrib import admin

from .models import AuditoriaDestinoAcreditacion, DestinoAcreditacion


@admin.register(DestinoAcreditacion)
class DestinoAcreditacionAdmin(admin.ModelAdmin):
    """Configura el listado, los filtros y la búsqueda de destinos de acreditación."""
    list_display = ("cliente", "tipo", "moneda", "identificacion", "titular", "activo")
    list_filter = ("tipo", "moneda", "activo")
    search_fields = (
        "cliente__nombre",
        "cliente__ruc",
        "titular",
        "documento_titular",
        "alias",
        "banco",
        "numero_cuenta",
        "proveedor_billetera",
        "numero_billetera",
    )


@admin.register(AuditoriaDestinoAcreditacion)
class AuditoriaDestinoAcreditacionAdmin(admin.ModelAdmin):
    """Expone en solo lectura la auditoría de los destinos de acreditación."""
    list_display = ("destino", "accion", "realizado_por", "fecha")
    list_filter = ("accion",)
    search_fields = ("destino__cliente__nombre", "destino__cliente__ruc")
    readonly_fields = [field.name for field in AuditoriaDestinoAcreditacion._meta.fields]

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
            obj (AuditoriaDestinoAcreditacion or None): Registro sobre el que
                se consulta el permiso, si corresponde.

        Returns:
            bool: False siempre, ya que la auditoría debe permanecer inalterada.
        """
        return False
