from django.contrib import admin

from .models import SolicitudAsociacion, UsuarioCliente


@admin.register(SolicitudAsociacion)
class SolicitudAsociacionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "cliente", "estado", "fecha_solicitud", "fecha_resolucion", "resuelto_por")
    list_filter = ("estado",)
    search_fields = ("usuario__username", "cliente__nombre", "cliente__ruc")
    readonly_fields = ("fecha_solicitud", "fecha_resolucion", "resuelto_por")


@admin.register(UsuarioCliente)
class UsuarioClienteAdmin(admin.ModelAdmin):
    list_display = ("usuario", "cliente_activo")
    search_fields = ("usuario__username",)
