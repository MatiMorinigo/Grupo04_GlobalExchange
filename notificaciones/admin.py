from django.contrib import admin

from .models import Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    """Expone en solo lectura el registro de notificaciones de tasas enviadas."""
    list_display = ("tasa", "email", "precio_compra", "precio_venta", "estado", "creada_en")
    list_filter = ("estado",)
    search_fields = ("email", "tasa__moneda_origen__codigo")

    def has_add_permission(self, request):
        """Impide crear notificaciones manualmente desde el admin.

        Returns:
            bool: False siempre, ya que los registros solo se crean por código.
        """
        return False

    def has_change_permission(self, request, obj=None):
        """Impide modificar notificaciones existentes.

        Returns:
            bool: False siempre, ya que el registro debe permanecer inalterado.
        """
        return False
