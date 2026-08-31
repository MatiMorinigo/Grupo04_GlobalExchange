from django.shortcuts import render
from django.urls import reverse

from clientes.models import Cliente
from usuarios.models import EstadoSolicitud, SolicitudAsociacion, UsuarioCliente


def home(request):
    modules = [
        {
            "title": "Clientes",
            "description": "Alta y gestión inicial de clientes.",
            "icon": "bi bi-people-fill",
            "bg_class": "text-bg-primary",
            "href": reverse("cliente-web-list"),
            "link_class": "link-light",
            "status": "Disponible",
            "status_class": "text-bg-success",
            "enabled": True,
            "action_label": "Ver Clientes",
            "disabled_reason": "",
        },
        {
            "title": "Operaciones de cambio",
            "description": "Compra y venta de divisas.",
            "icon": "bi bi-arrow-left-right",
            "bg_class": "text-bg-success",
            "link_class": "link-light",
            "status": "Próximamente",
            "status_class": "text-bg-secondary",
            "enabled": False,
            "action_label": "Próximamente",
            "disabled_reason": "Módulo aún no disponible.",
        },
        {
            "title": "Cotizaciones",
            "description": "Consulta de tasas de cambio.",
            "icon": "bi bi-graph-up-arrow",
            "bg_class": "text-bg-warning",
            "link_class": "link-dark",
            "status": "Próximamente",
            "status_class": "text-bg-secondary",
            "enabled": False,
            "action_label": "Próximamente",
            "disabled_reason": "Módulo aún no disponible.",
        },
        {
            "title": "Reportes",
            "description": "Resúmenes operativos y financieros.",
            "icon": "bi bi-file-earmark-bar-graph-fill",
            "bg_class": "text-bg-danger",
            "link_class": "link-light",
            "status": "Próximamente",
            "status_class": "text-bg-secondary",
            "enabled": False,
            "action_label": "Próximamente",
            "disabled_reason": "Módulo aún no disponible.",
        },
        {
            "title": "Usuarios",
            "description": "Usuarios, roles y permisos del sistema.",
            "icon": "bi bi-person-gear",
            "bg_class": "text-bg-info",
            "link_class": "link-dark",
            "status": "Próximamente",
            "status_class": "text-bg-secondary",
            "enabled": False,
            "action_label": "Próximamente",
            "disabled_reason": "Módulo aún no disponible.",
        },
        {
            "title": "Configuración",
            "description": "Parámetros generales de la plataforma.",
            "icon": "bi bi-sliders",
            "bg_class": "text-bg-secondary",
            "link_class": "link-light",
            "status": "Próximamente",
            "status_class": "text-bg-secondary",
            "enabled": False,
            "action_label": "Próximamente",
            "disabled_reason": "Módulo aún no disponible.",
        },
    ]

    # Contexto de clientes asociados al usuario
    clientes_aprobados = []
    cliente_activo = None
    perfil = None

    if request.user.is_authenticated:
        clientes_aprobados = list(
            Cliente.objects.filter(
                solicitudes_asociacion__usuario=request.user,
                solicitudes_asociacion__estado=EstadoSolicitud.APROBADA,
                activo=True,
            ).distinct()
        )

        try:
            perfil = request.user.perfil
            cliente_activo = perfil.cliente_activo
        except UsuarioCliente.DoesNotExist:
            perfil = None
            cliente_activo = None

        # Si el usuario tiene clientes aprobados pero no tiene cliente activo asignado,
        # asignar el primero automáticamente
        if clientes_aprobados and cliente_activo is None:
            perfil, _ = UsuarioCliente.objects.get_or_create(usuario=request.user)
            perfil.cliente_activo = clientes_aprobados[0]
            perfil.save(update_fields=["cliente_activo"])
            cliente_activo = clientes_aprobados[0]

    return render(
        request,
        "core/home.html",
        {
            "active_menu": "home",
            "modules": modules,
            "clientes_aprobados": clientes_aprobados,
            "cliente_activo": cliente_activo,
        },
    )
