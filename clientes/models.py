from decimal import Decimal
from django.utils import timezone
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth import get_user_model

User = get_user_model()

class TipoCliente(models.TextChoices):
    """Define los tipos de persona admitidos para un cliente.
    """
    FISICA = "FISICA", "Persona física"
    JURIDICA = "JURIDICA", "Persona jurídica"

class CategoriaCliente(models.TextChoices):
    """Define las categorías comerciales disponibles para los clientes.
    """
    MINORISTA = "MINORISTA", "Minorista"
    CORPORATIVO = "CORPORATIVO", "Corporativo"
    VIP = "VIP", "VIP"

# Create your models here.
class Cliente(models.Model):
    """Almacena los datos de identificación y clasificación de un cliente.
    """
    id_cliente = models.BigAutoField(primary_key=True)
    ruc = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=150)
    categoria = models.CharField(
    max_length=11,
    choices=CategoriaCliente.choices
    )
    tipo = models.CharField(
        max_length=8,
        choices=TipoCliente.choices
    )
    activo = models.BooleanField(default=True)
    vip_vigente_hasta = models.DateField(
    null=True,
    blank=True,
    verbose_name="VIP vigente hasta",
    )

    @property
    def categoria_efectiva(self):
        """
        Devuelve la categoría aplicable actualmente al cliente.

        Los clientes cuya categoría base es VIP mantienen esa categoría
        permanentemente. Los demás clientes son considerados VIP mientras
        su promoción temporal se encuentre vigente.
        """
        if self.categoria == CategoriaCliente.VIP:
            return CategoriaCliente.VIP

        if (
            self.vip_vigente_hasta
            and self.vip_vigente_hasta >= timezone.localdate()
        ):
            return CategoriaCliente.VIP

        return self.categoria

class ConfiguracionBeneficioCategoria(models.Model):
    """
    Define el beneficio porcentual y el límite mensual aplicable
    a una categoría de cliente.
    """

    categoria = models.CharField(
        max_length=11,
        choices=CategoriaCliente.choices,
        unique=True,
    )

    porcentaje_beneficio = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[
        MinValueValidator(0),
        MaxValueValidator(Decimal("30.00")),
        ],
    )

    limite_mensual_pyg = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        validators=[
        MinValueValidator(0),
        ],
    )

    def __str__(self):
        return f"{self.get_categoria_display()} - {self.porcentaje_beneficio}%"

class ConfiguracionVIP(models.Model):
    """Configura las condiciones globales para obtener temporalmente la categoría VIP."""

    umbral_mensual_pyg = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Umbral mensual para VIP en PYG",
    )

    duracion_meses = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Duración del VIP temporal en meses",
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
        verbose_name="Última modificación",
    )

    modificado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuraciones_vip_modificadas",
        verbose_name="Modificado por",
    )

    class Meta:
        verbose_name = "Configuración VIP temporal"
        verbose_name_plural = "Configuración VIP temporal"

    @classmethod
    def obtener(cls):
        """Devuelve la única configuración VIP del sistema."""
        configuracion, _ = cls.objects.get_or_create(pk=1)
        return configuracion

    def save(self, *args, **kwargs):
        """Fuerza una única fila de configuración global."""
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"VIP desde {self.umbral_mensual_pyg} PYG "
            f"por {self.duracion_meses} mes(es)"
        )