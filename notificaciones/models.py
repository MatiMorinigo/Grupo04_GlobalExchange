from django.conf import settings
from django.db import models


class EstadoNotificacion(models.TextChoices):
    """Define el resultado del envío de una notificación."""
    ENVIADA = "ENVIADA", "Enviada"
    FALLIDA = "FALLIDA", "Fallida"


class Notificacion(models.Model):
    """Registra el aviso de una tasa de cambio publicada enviado a un usuario.

    Conserva una copia del correo de destino y de los precios informados para
    que el registro siga siendo válido aunque el usuario o la tasa cambien.
    """
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="notificaciones",
        verbose_name="Usuario",
    )
    tasa = models.ForeignKey(
        "cotizaciones.TasaCambio",
        on_delete=models.CASCADE,
        related_name="notificaciones",
        verbose_name="Tasa de cambio",
    )
    email = models.EmailField(verbose_name="Correo de destino")
    precio_compra = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Precio de compra")
    precio_venta = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Precio de venta")
    estado = models.CharField(max_length=10, choices=EstadoNotificacion.choices, verbose_name="Estado")
    error = models.TextField(blank=True, verbose_name="Error")
    creada_en = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    class Meta:
        """Define el orden y los nombres de presentación de las notificaciones."""
        ordering = ["-creada_en"]
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"

    def __str__(self):
        """Devuelve una etiqueta legible de la notificación.

        Returns:
            str: Par de monedas, correo de destino y estado del envío.
        """
        return f"{self.tasa} - {self.email} [{self.estado}]"
