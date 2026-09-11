from django.apps import AppConfig


class PagosConfig(AppConfig):
    """Configura la aplicación pagos y su tipo de clave primaria automática."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "pagos"
    verbose_name = "Métodos de pago"
