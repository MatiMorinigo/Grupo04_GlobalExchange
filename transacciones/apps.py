from django.apps import AppConfig


class TransaccionesConfig(AppConfig):
    """Configura la aplicacion de operaciones cambiarias."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "transacciones"
    verbose_name = "Transacciones"
