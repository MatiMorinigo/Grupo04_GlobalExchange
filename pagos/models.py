from django.contrib.auth import get_user_model
from django.db import models

from clientes.models import Cliente

from .validators import validar_formato_vencimiento

User = get_user_model()


class TipoMetodoPago(models.TextChoices):
    """Define los tipos de método de pago admitidos para un cliente."""
    TARJETA_CREDITO = "TARJETA_CREDITO", "Tarjeta de crédito"
    TARJETA_DEBITO = "TARJETA_DEBITO", "Tarjeta de débito"


class MetodoPago(models.Model):
    """Representa una tarjeta registrada por un cliente para sus operaciones cambiarias.

    Por seguridad, nunca se almacena el número completo de la tarjeta ni el
    código de seguridad (CVV): solo se conservan los últimos cuatro dígitos,
    suficientes para identificar la tarjeta ante el usuario.
    """
    id_metodo_pago = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="metodos_pago",
        verbose_name="Cliente",
    )
    tipo = models.CharField(max_length=20, choices=TipoMetodoPago.choices, verbose_name="Tipo")
    titular = models.CharField(max_length=150, verbose_name="Titular")
    ultimos_cuatro_digitos = models.CharField(max_length=4, verbose_name="Últimos 4 dígitos")
    fecha_vencimiento = models.CharField(
        max_length=5,
        verbose_name="Vencimiento",
        validators=[validar_formato_vencimiento],
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Creado el")
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name="Última modificación")

    class Meta:
        """Define el orden y los nombres de presentación de los métodos de pago."""
        ordering = ["-creado_en"]
        verbose_name = "Método de pago"
        verbose_name_plural = "Métodos de pago"

    def __str__(self):
        """Devuelve una etiqueta legible del método de pago.

        Returns:
            str: Tipo de tarjeta, últimos 4 dígitos y cliente propietario.
        """
        return f"{self.get_tipo_display()} •••• {self.ultimos_cuatro_digitos} ({self.cliente})"


class AccionAuditoriaMetodoPago(models.TextChoices):
    """Define las acciones que puede registrar la auditoría de métodos de pago."""
    CREACION = "CREACION", "Creación"
    MODIFICACION = "MODIFICACION", "Modificación"
    DESACTIVACION = "DESACTIVACION", "Desactivación"
    ACTIVACION = "ACTIVACION", "Activación"
    ELIMINACION = "ELIMINACION", "Eliminación"


class AuditoriaMetodoPagoManager(models.Manager):
    """Crea registros de auditoría para las acciones realizadas sobre métodos de pago."""

    def registrar(self, metodo_pago, accion, realizado_por, datos_anteriores=None, datos_nuevos=None):
        """Crea un registro de auditoría para una acción sobre un método de pago.

        Args:
            metodo_pago (MetodoPago): Método de pago afectado por la acción.
            accion (str): Acción realizada, según AccionAuditoriaMetodoPago.
            realizado_por (django.contrib.auth.models.User or None): Usuario
                que realizó la acción, o None si no pudo determinarse.
            datos_anteriores (dict or None): Datos previos a la acción, si
                corresponde.
            datos_nuevos (dict or None): Datos vigentes luego de la acción, si
                corresponde (no aplica, por ejemplo, en una eliminación).

        Returns:
            AuditoriaMetodoPago: Registro de auditoría creado.
        """
        return self.create(
            metodo_pago=metodo_pago,
            accion=accion,
            realizado_por=realizado_por,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
        )


class AuditoriaMetodoPago(models.Model):
    """Registra en un log de auditoría cada alta, modificación, baja o eliminación de un método de pago.

    El vínculo con ``MetodoPago`` usa ``SET_NULL`` en lugar de ``CASCADE``
    para que, al eliminar definitivamente un método de pago, la fila que deja
    constancia de esa eliminación no se borre junto con él.
    """
    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditorias",
        verbose_name="Método de pago",
    )
    accion = models.CharField(
        max_length=20,
        choices=AccionAuditoriaMetodoPago.choices,
        verbose_name="Acción",
    )
    datos_anteriores = models.JSONField(null=True, blank=True, verbose_name="Datos anteriores")
    datos_nuevos = models.JSONField(null=True, blank=True, verbose_name="Datos nuevos")
    realizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modificaciones_metodos_pago",
        verbose_name="Realizado por",
    )
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    objects = AuditoriaMetodoPagoManager()

    class Meta:
        """Define el orden y los nombres de presentación de la auditoría de métodos de pago."""
        ordering = ["-fecha"]
        verbose_name = "Auditoría de método de pago"
        verbose_name_plural = "Auditorías de métodos de pago"

    def __str__(self):
        """Devuelve una etiqueta legible del registro de auditoría.

        Returns:
            str: Acción realizada e identificador del método de pago afectado.
        """
        return f"{self.get_accion_display()} - {self.metodo_pago_id}"
