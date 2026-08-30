from django.shortcuts import render
from django.urls import reverse


def home(request):
    """Render the first visual version of the main menu."""
    modules = [
        {
            "title": "Clientes",
            "value": "CRM",
            "description": "Alta y gestion inicial de clientes.",
            "icon": "bi bi-people-fill",
            "bg_class": "text-bg-primary",
            "href": reverse("cliente-create"),
            "link_class": "link-light",
            "status": "Disponible",
        },
        {
            "title": "Operaciones de cambio",
            "value": "FX",
            "description": "Compra y venta de divisas.",
            "icon": "bi bi-arrow-left-right",
            "bg_class": "text-bg-success",
            "href": "#",
            "link_class": "link-light",
            "status": "Placeholder",
        },
        {
            "title": "Cotizaciones",
            "value": "Tasas",
            "description": "Consulta de tasas de cambio.",
            "icon": "bi bi-graph-up-arrow",
            "bg_class": "text-bg-warning",
            "href": "#",
            "link_class": "link-dark",
            "status": "Placeholder",
        },
        {
            "title": "Reportes",
            "value": "BI",
            "description": "Resumenes operativos y financieros.",
            "icon": "bi bi-file-earmark-bar-graph-fill",
            "bg_class": "text-bg-danger",
            "href": "#",
            "link_class": "link-light",
            "status": "Placeholder",
        },
        {
            "title": "Usuarios",
            "value": "IAM",
            "description": "Usuarios, roles y permisos del sistema.",
            "icon": "bi bi-person-gear",
            "bg_class": "text-bg-info",
            "href": "#",
            "link_class": "link-dark",
            "status": "Placeholder",
        },
        {
            "title": "Configuracion",
            "value": "Admin",
            "description": "Parametros generales de la plataforma.",
            "icon": "bi bi-sliders",
            "bg_class": "text-bg-secondary",
            "href": "#",
            "link_class": "link-light",
            "status": "Placeholder",
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
