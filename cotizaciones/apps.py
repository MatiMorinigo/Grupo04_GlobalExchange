from django.apps import AppConfig


class CotizacionesConfig(AppConfig):
    """Configura la aplicación cotizaciones y su tipo de clave primaria automática."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "cotizaciones"
