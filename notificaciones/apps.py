from django.apps import AppConfig


class NotificacionesConfig(AppConfig):
    """Configura la aplicación notificaciones y su tipo de clave primaria automática."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "notificaciones"
