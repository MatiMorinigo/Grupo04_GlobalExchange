from django.shortcuts import render
from django.urls import reverse
from core.keycloak import tiene_rol
from clientes.models import Cliente
from usuarios.models import EstadoSolicitud, SolicitudAsociacion, UsuarioCliente


def home(request):
    """Renderiza la página inicial con los módulos y clientes del usuario.

    Oculta los módulos administrativos a quienes no tienen ese rol. Para
    usuarios autenticados con identificador, consulta sus clientes activos
    con asociación aprobada. Si existen y no hay un cliente activo asignado
    al perfil, crea el perfil si hace falta y le asigna el primero.

    Args:
        request (django.http.HttpRequest): Solicitud de la página inicial.

    Returns:
        django.http.HttpResponse: Página con los módulos visibles, los
        clientes aprobados y el cliente activo.
    """
    # Operar exige un cliente activo, así que a quien no inició sesión se le
    # ofrece el módulo como disponible pero pendiente de autenticación.
    autenticado = request.user.is_authenticated

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
            "admin_only": True,
        },
        {
            "title": "Operaciones de cambio",
            "description": "Compra de divisas.",
            "icon": "bi bi-arrow-left-right",
            "bg_class": "text-bg-success",
            "href": reverse("compra-web-create") if autenticado else "",
            "link_class": "link-light",
            "status": "Disponible" if autenticado else "Requiere sesión",
            "status_class": "text-bg-success" if autenticado else "text-bg-secondary",
            "enabled": autenticado,
            "action_label": "Comprar divisas" if autenticado else "Iniciá sesión",
            "disabled_reason": "" if autenticado else "Iniciá sesión para operar.",
        },
        {
            "title": "Cotizaciones",
            "description": "Consulta de tasas de cambio.",
            "icon": "bi bi-graph-up-arrow",
            "bg_class": "text-bg-warning",
            "href": reverse("cotizacion-web-list"),
            "link_class": "link-dark",
            "status": "Disponible",
            "status_class": "text-bg-success",
            "enabled": True,
            "action_label": "Ver Cotizaciones",
            "disabled_reason": "",
        },
        {
            "title": "Reportes",
            "description": "Resúmenes operativos y financieros.",
            "icon": "bi bi-file-earmark-bar-graph-fill",
            "bg_class": "text-bg-danger",
            "link_class": "link-light",
            "status": "No Disponible",
            "status_class": "text-bg-secondary",
            "enabled": False,
            "action_label": "Próximamente",
            "disabled_reason": "Módulo aún no disponible.",
            "admin_only": True,
        },
        {
            "title": "Configuración",
            "description": "Beneficios por categoría y comisiones del sistema.",
            "icon": "bi bi-sliders",
            "bg_class": "text-bg-secondary",
            "href": reverse("configuracion_beneficios"),
            "link_class": "link-light",
            "status": "Disponible",
            "status_class": "text-bg-success",
            "enabled": True,
            "action_label": "Configurar",
            "disabled_reason": "",
            "admin_only": True,
        },
    ]
    if not tiene_rol(request, "administrador"):
        modules = [
            module
            for module in modules
            if not module.get("admin_only", False)
        ]
    # Contexto de clientes asociados al usuario
    clientes_aprobados = []
    cliente_activo = None
    perfil = None

    if request.user.is_authenticated and request.user.pk is not None:
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
