from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class MetodoPago(models.Model):
    """Almacena los métodos de pago admitidos en las operaciones cambiarias.

    Registra nombre, descripción y estado de habilitación de cada método.
    Los campos de trazabilidad permiten auditar quién y cuándo creó o
    modificó cada registro (RF44 / HU27).
    """

    id_metodo_pago = models.BigAutoField(primary_key=True)
    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Nombre",
    )
    descripcion = models.TextField(
        blank=True,
        verbose_name="Descripción",
    )
    habilitado = models.BooleanField(
        default=True,
        verbose_name="Habilitado",
    )

    # ── Trazabilidad ─────────────────────────────────────────────────────────
    creado_en = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Creado el",
    )
    actualizado_en = models.DateTimeField(
        auto_now=True,
        verbose_name="Última modificación",
    )
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metodos_pago_creados",
        verbose_name="Creado por",
    )
    modificado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metodos_pago_modificados",
        verbose_name="Modificado por",
    )

    class Meta:
        """Define el orden y los nombres de presentación del modelo."""

        ordering = ["nombre"]
        verbose_name = "Método de pago"
        verbose_name_plural = "Métodos de pago"

    def __str__(self):
        """Devuelve el nombre del método de pago.

        Returns:
            str: Nombre del método de pago.
        """
        return self.nombre
