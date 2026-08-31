from django.db import models
from django.contrib.auth import get_user_model

from clientes.models import Cliente

User = get_user_model()


class EstadoSolicitud(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    APROBADA = "APROBADA", "Aprobada"
    RECHAZADA = "RECHAZADA", "Rechazada"


class SolicitudAsociacion(models.Model):
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="solicitudes_asociacion",
        verbose_name="Usuario",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="solicitudes_asociacion",
        verbose_name="Cliente",
    )
    estado = models.CharField(
        max_length=10,
        choices=EstadoSolicitud.choices,
        default=EstadoSolicitud.PENDIENTE,
        verbose_name="Estado",
    )
    fecha_solicitud = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de solicitud")
    fecha_resolucion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de resolución")
    resuelto_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_resueltas",
        verbose_name="Resuelto por",
    )

    class Meta:
        verbose_name = "Solicitud de asociación"
        verbose_name_plural = "Solicitudes de asociación"
        ordering = ["-fecha_solicitud"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "cliente"],
                condition=models.Q(estado="PENDIENTE"),
                name="unique_solicitud_pendiente",
            )
        ]

    def __str__(self):
        return f"{self.usuario} ↔ {self.cliente} [{self.estado}]"


class UsuarioCliente(models.Model):
    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="perfil",
        verbose_name="Usuario",
    )
    cliente_activo = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios_activos",
        verbose_name="Cliente activo",
    )

    class Meta:
        verbose_name = "Asociación usuario-cliente"
        verbose_name_plural = "Asociaciones usuario-cliente"

    def __str__(self):
        return f"Asociación de {self.usuario}"

    def get_clientes_aprobados(self):
        """Retorna los clientes con solicitud aprobada para este usuario."""
        return Cliente.objects.filter(
            solicitudes_asociacion__usuario=self.usuario,
            solicitudes_asociacion__estado=EstadoSolicitud.APROBADA,
        )

