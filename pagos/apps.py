from django.apps import AppConfig


class PagosConfig(AppConfig):
    """Configuración de la app de gestión de métodos de pago."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "pagos"
    verbose_name = "Métodos de pago"
