from django.shortcuts import render
from django.urls import reverse


def home(request):
    modules = [
        {
            "title": "Clientes",
            "description": "Alta y gestión inicial de clientes.",
            "icon": "bi bi-people-fill",
            "bg_class": "text-bg-primary",
            "href": reverse("cliente-create"),
            "link_class": "link-light",
            "status": "Disponible",
            "status_class": "text-bg-success",
            "enabled": True,
            "action_label": "Abrir Clientes",
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

    return render(
        request,
        "core/home.html",
        {
            "active_menu": "home",
            "modules": modules,
        },
    )
