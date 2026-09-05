from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Moneda(models.Model):
    codigo = models.CharField(max_length=3, primary_key=True)
    nombre = models.CharField(max_length=80)
    simbolo = models.CharField(max_length=8)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class TasaCambio(models.Model):
    id_tasa = models.BigAutoField(primary_key=True)
    moneda_origen = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="tasas_origen",
    )
    moneda_destino = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="tasas_destino",
    )
    precio_compra = models.DecimalField(max_digits=18, decimal_places=4)
    precio_venta = models.DecimalField(max_digits=18, decimal_places=4)
    vigente = models.BooleanField(default=True)
    fecha_vigencia = models.DateTimeField(default=timezone.now)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["moneda_origen__codigo", "moneda_destino__codigo"]
        verbose_name = "Tasa de cambio"
        verbose_name_plural = "Tasas de cambio"
        constraints = [
            models.CheckConstraint(
                condition=~Q(moneda_origen=F("moneda_destino")),
                name="cotizaciones_tasa_monedas_distintas",
            ),
            models.UniqueConstraint(
                fields=["moneda_origen", "moneda_destino"],
                condition=Q(vigente=True),
                name="cotizaciones_tasa_vigente_unica_por_par",
            ),
        ]

    def clean(self):
        if self.moneda_origen_id == self.moneda_destino_id:
            raise ValidationError("La moneda de origen y destino deben ser distintas.")

    def __str__(self):
        return f"{self.moneda_origen_id}/{self.moneda_destino_id}"

    def tasa_anterior(self):
        if not self.fecha_vigencia:
            return None

        return (
            TasaCambio.objects.filter(
                moneda_origen=self.moneda_origen,
                moneda_destino=self.moneda_destino,
                fecha_vigencia__lt=self.fecha_vigencia,
            )
            .exclude(pk=self.pk)
            .order_by("-fecha_vigencia")
            .first()
        )

    def variacion_compra(self):
        anterior = self.tasa_anterior()
        if not anterior:
            return None
        return self.precio_compra - anterior.precio_compra

    def variacion_venta(self):
        anterior = self.tasa_anterior()
        if not anterior:
            return None
        return self.precio_venta - anterior.precio_venta
