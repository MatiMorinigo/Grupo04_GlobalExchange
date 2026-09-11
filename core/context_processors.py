from django.conf import settings
from core.keycloak import obtener_roles


ROLES_USUARIO = {
    "administrador": "Administrador",
    "analista_cambiario": "Analista cambiario",
    "cajero": "Cajero",
    "tesorero": "Tesorero",
    "usuario": "Usuario",
}


def app_environment(request):
    """Añade al contexto el entorno, los roles visibles y el permiso administrativo.

    Utiliza Desarrollo cuando APP_ENV no está definido y oculta la etiqueta
    cuando su valor corresponde a una de las variantes de producción admitidas.

    Args:
        request (django.http.HttpRequest or None): Solicitud utilizada para
            comprobar el rol; si es None, el permiso se considera falso.

    Returns:
        dict: Contexto con es_administrador, rol_usuario y app_environment.
    """
    environment = getattr(settings, "APP_ENV", "Desarrollo")
    if str(environment).strip().lower() in {"prod", "production", "produccion", "producción"}:
        environment = ""

    roles = obtener_roles(request) if request else []
    roles_visibles = [etiqueta for rol, etiqueta in ROLES_USUARIO.items() if rol in roles]

    return {
        "es_administrador": "administrador" in roles,
        "rol_usuario": " · ".join(roles_visibles),
        "app_environment": environment,
    }
