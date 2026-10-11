from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import (
    DateTimeRangeField,
    RangeBoundary,
    RangeOperators,
)
from django.db.models import Func

class Sucursal(models.Model):
    id_sucursal = models.BigAutoField(primary_key=True)

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=255)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "Sucursal"
        verbose_name_plural = "Sucursales"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class Caja(models.Model):
    id_caja = models.BigAutoField(primary_key=True)

    sucursal = models.ForeignKey(
        Sucursal,
        on_delete=models.PROTECT,
        related_name="cajas"
    )

    codigo = models.CharField(max_length=20)
    nombre = models.CharField(max_length=100)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["sucursal__codigo", "codigo"]
        verbose_name = "Caja"
        verbose_name_plural = "Cajas"

        constraints = [
            models.UniqueConstraint(
                fields=["sucursal", "codigo"],
                name="unique_codigo_caja_por_sucursal"
            )
        ]

    def __str__(self):
        return f"{self.sucursal.nombre} - {self.nombre}"

class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()

class AsignacionCaja(models.Model):
    id_asignacion = models.BigAutoField(primary_key=True)

    caja = models.ForeignKey(
        Caja,
        on_delete=models.PROTECT,
        related_name="asignaciones"
    )

    cajero_keycloak_id = models.UUIDField(
    db_index=True
    )

    cajero_username = models.CharField(
        max_length=150
    )

    turno = models.CharField(max_length=50)

    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()

    asignado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="asignaciones_realizadas"
    )

    fecha_registro = models.DateTimeField(auto_now_add=True)


    class Meta:
        ordering = ["-fecha_inicio"]
        verbose_name = "Asignación de caja"
        verbose_name_plural = "Asignaciones de caja"

        constraints = [
            ExclusionConstraint(
                name="no_superposicion_por_caja",
                expressions=[
                    (
                        TsTzRange(
                            "fecha_inicio",
                            "fecha_fin",
                            RangeBoundary()
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                    ("caja", RangeOperators.EQUAL),
                ],
            ),
            ExclusionConstraint(
                name="no_superposicion_por_cajero",
                expressions=[
                    (
                        TsTzRange(
                            "fecha_inicio",
                            "fecha_fin",
                            RangeBoundary()
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                    ("cajero_keycloak_id", RangeOperators.EQUAL),
                ],
            ),
        ]


    def clean(self):
        super().clean()

        errores = {}

        # La caja y su sucursal deben estar activas.
        if self.caja_id:
            disponible = Caja.objects.filter(
                pk=self.caja_id,
                activa=True,
                sucursal__activa=True
            ).exists()

            if not disponible:
                errores["caja"] = (
                    "La caja y su sucursal deben estar activas."
                )

        if self.fecha_inicio and self.fecha_fin:
            if self.fecha_fin <= self.fecha_inicio:
                errores["fecha_fin"] = (
                    "La fecha de fin debe ser posterior al inicio."
                )

            elif self.caja_id and self.cajero_keycloak_id:
                # Buscar asignaciones cuyos horarios se superpongan.
                superpuestas = AsignacionCaja.objects.filter(
                    fecha_inicio__lt=self.fecha_fin,
                    fecha_fin__gt=self.fecha_inicio
                ).exclude(pk=self.pk)

                # Dos cajeros no pueden ocupar la misma caja
                # durante horarios superpuestos.
                if superpuestas.filter(caja_id=self.caja_id).exists():
                    errores["caja"] = (
                        "La caja ya tiene un cajero asignado "
                        "durante ese horario."
                    )

                # Un cajero no puede ocupar dos cajas
                # durante horarios superpuestos.
                if superpuestas.filter(cajero_keycloak_id=self.cajero_keycloak_id).exists():
                    errores["cajero_keycloak_id"] = (
                        "El cajero ya tiene una asignación "
                        "durante ese horario."
                    )

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return (
            f"{self.cajero_username} - {self.caja} "
            f"({self.fecha_inicio} a {self.fecha_fin})"
        )