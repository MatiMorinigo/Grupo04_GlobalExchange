from django.db import models


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