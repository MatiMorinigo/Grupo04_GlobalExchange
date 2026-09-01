from django.contrib import admin

from .models import Moneda, TasaCambio


@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "simbolo", "activa")
    list_filter = ("activa",)
    search_fields = ("codigo", "nombre")


@admin.register(TasaCambio)
class TasaCambioAdmin(admin.ModelAdmin):
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
