from django.conf import settings


def app_environment(request):
    environment = getattr(settings, "APP_ENV", "Desarrollo")
    if str(environment).strip().lower() in {"prod", "production", "produccion", "producción"}:
        environment = ""

    return {
        "app_environment": environment,
    }
