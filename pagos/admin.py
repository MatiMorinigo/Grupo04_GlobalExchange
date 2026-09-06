from django.contrib import admin

from .models import MetodoPago


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    """Configura la consulta administrativa de métodos de pago con trazabilidad.

    Expone los campos de auditoría (creado_por, modificado_por, fechas)
    en modo solo lectura para fines de trazabilidad (CA-5 / HU27).
    """

    list_display = (
        "nombre",
        "habilitado",
        "creado_por",
        "creado_en",
        "modificado_por",
        "actualizado_en",
    )
    list_filter = ("habilitado", "creado_en", "actualizado_en")
    search_fields = ("nombre", "descripcion")
    readonly_fields = (
        "creado_en",
        "actualizado_en",
        "creado_por",
        "modificado_por",
    )
    fieldsets = (
        (
            "Información del método de pago",
            {
                "fields": ("nombre", "descripcion", "habilitado"),
            },
        ),
        (
            "Trazabilidad",
            {
                "fields": (
                    "creado_por",
                    "creado_en",
                    "modificado_por",
                    "actualizado_en",
                ),
                "classes": ("collapse",),
            },
        ),
    )
