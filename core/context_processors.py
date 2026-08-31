from django.conf import settings
from core.keycloak import tiene_rol

def app_environment(request):
    environment = getattr(settings, "APP_ENV", "Desarrollo")
    if str(environment).strip().lower() in {"prod", "production", "produccion", "producción"}:
        environment = ""

    return {
        "es_administrador": tiene_rol(request, "administrador"),
        "app_environment": environment,
    }
