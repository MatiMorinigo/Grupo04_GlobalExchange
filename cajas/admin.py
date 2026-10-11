from django.contrib import admin

from .models import DenominacionBillete


@admin.register(DenominacionBillete)
class DenominacionBilleteAdmin(admin.ModelAdmin):
    """Catálogo controlado por los permisos administrativos de Django."""

    list_display = ("moneda", "valor", "activa")
    list_filter = ("moneda", "activa")
    ordering = ("moneda", "valor")
