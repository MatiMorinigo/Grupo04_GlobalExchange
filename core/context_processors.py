from django.conf import settings
from core.keycloak import tiene_rol

def app_environment(request):
    """Añade al contexto de las plantillas el entorno y el permiso administrativo.

    Utiliza Desarrollo cuando APP_ENV no está definido y oculta la etiqueta
    cuando su valor corresponde a una de las variantes de producción admitidas.

    Args:
        request (django.http.HttpRequest or None): Solicitud utilizada para
            comprobar el rol; si es None, el permiso se considera falso.

    Returns:
        dict: Contexto con es_administrador y la etiqueta app_environment.
    """
    environment = getattr(settings, "APP_ENV", "Desarrollo")
    if str(environment).strip().lower() in {"prod", "production", "produccion", "producción"}:
        environment = ""

    return {
        "es_administrador": tiene_rol(request, "administrador") if request else False,
        "app_environment": environment,
    }
