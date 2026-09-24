from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

User = get_user_model()


class Moneda(models.Model):
    """Representa una moneda identificada por su código, con nombre, símbolo y estado."""
    codigo = models.CharField(max_length=3, primary_key=True)
    nombre = models.CharField(max_length=80)
    simbolo = models.CharField(max_length=8)
    activa = models.BooleanField(default=True)

    class Meta:
        """Define el orden por código y los nombres de presentación de las monedas."""
        ordering = ["codigo"]
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"

    def __str__(self):
        """Devuelve una etiqueta legible de la moneda.

        Returns:
            str: Código y nombre de la moneda separados por un guion.
        """
        return f"{self.codigo} - {self.nombre}"


class TasaCambio(models.Model):
    """Almacena los precios de compra y venta de un par de monedas.

    Registra la vigencia de la tasa y sus fechas. Las restricciones exigen
    monedas distintas y una única tasa marcada como vigente por cada par.
    """
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
    modificado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasas_registradas",
        verbose_name="Registrado por",
    )

    class Meta:
        """Define el orden, los nombres y las restricciones del par de monedas."""
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
        """Valida que las monedas de origen y destino sean distintas.

        Returns:
            None: La validación finaliza sin errores.

        Raises:
            django.core.exceptions.ValidationError: Si coinciden los
                identificadores de las monedas de origen y destino.
        """
        if self.moneda_origen_id == self.moneda_destino_id:
            raise ValidationError("La moneda de origen y destino deben ser distintas.")

    def __str__(self):
        """Devuelve el par de monedas representado por la tasa.

        Returns:
            str: Códigos de origen y destino separados por una barra.
        """
        return f"{self.moneda_origen_id}/{self.moneda_destino_id}"

    def tasa_anterior(self):
        """Busca la tasa inmediatamente anterior del mismo par de monedas.

        Considera fechas estrictamente anteriores, excluye el registro actual
        y no restringe la búsqueda al estado vigente.

        Returns:
            TasaCambio or None: Tasa más reciente anterior a esta, o None si no
            hay antecedentes o la instancia no tiene fecha de vigencia.
        """
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
        """Calcula la diferencia de compra respecto de la tasa anterior.

        Returns:
            decimal.Decimal or None: Precio de compra actual menos el anterior,
            o None si no hay una tasa previa.
        """
        anterior = self.tasa_anterior()
        if not anterior:
            return None
        return self.precio_compra - anterior.precio_compra

    def variacion_venta(self):
        """Calcula la diferencia de venta respecto de la tasa anterior.

        Returns:
            decimal.Decimal or None: Precio de venta actual menos el anterior,
            o None si no hay una tasa previa.
        """
        anterior = self.tasa_anterior()
        if not anterior:
            return None
        return self.precio_venta - anterior.precio_venta


class AuditoriaTasaCambio(models.Model):
    """Registra en un log de auditoría cada modificación manual de una tasa de cambio."""
    tasa_nueva = models.ForeignKey(
        TasaCambio,
        on_delete=models.CASCADE,
        related_name="auditorias",
        verbose_name="Tasa nueva",
    )
    tasa_anterior = models.ForeignKey(
        TasaCambio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditorias_como_anterior",
        verbose_name="Tasa anterior",
    )
    precio_compra_anterior = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name="Precio de compra anterior"
    )
    precio_venta_anterior = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name="Precio de venta anterior"
    )
    precio_compra_nuevo = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Precio de compra nuevo")
    precio_venta_nuevo = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Precio de venta nuevo")
    realizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modificaciones_tasas",
        verbose_name="Realizado por",
    )
    fecha_modificacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de modificación")

    class Meta:
        """Define el orden y los nombres de presentación del log de auditoría de tasas."""
        ordering = ["-fecha_modificacion"]
        verbose_name = "Auditoría de tasa de cambio"
        verbose_name_plural = "Auditorías de tasas de cambio"

    def __str__(self):
        """Devuelve una etiqueta legible del registro de auditoría.

        Returns:
            str: Par de monedas y fecha de la modificación registrada.
        """
        return f"{self.tasa_nueva} - {self.fecha_modificacion:%d/%m/%Y %H:%M}"


class AccionAuditoriaMoneda(models.TextChoices):
    """Define las acciones que puede registrar la auditoría de monedas."""
    CREACION = "CREACION", "Creación"
    MODIFICACION = "MODIFICACION", "Modificación"
    DESHABILITACION = "DESHABILITACION", "Deshabilitación"
    HABILITACION = "HABILITACION", "Habilitación"


class AuditoriaMonedaManager(models.Manager):
    """Crea registros de auditoría para las acciones realizadas sobre monedas."""

    def registrar(self, moneda, accion, realizado_por, datos_anteriores=None, datos_nuevos=None):
        """Crea un registro de auditoría para una acción sobre una moneda.

        Args:
            moneda (Moneda): Moneda afectada por la acción.
            accion (str): Acción realizada, según AccionAuditoriaMoneda.
            realizado_por (django.contrib.auth.models.User or None): Usuario
                que realizó la acción, o None si no pudo determinarse.
            datos_anteriores (dict or None): Datos previos a la acción, si
                corresponde.
            datos_nuevos (dict): Datos vigentes de la moneda luego de la acción.

        Returns:
            AuditoriaMoneda: Registro de auditoría creado.
        """
        return self.create(
            moneda=moneda,
            accion=accion,
            realizado_por=realizado_por,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
        )


class AuditoriaMoneda(models.Model):
    """Registra la creación, modificación y deshabilitación de monedas para fines de trazabilidad."""
    moneda = models.ForeignKey(
        Moneda,
        on_delete=models.CASCADE,
        related_name="auditorias",
        verbose_name="Moneda",
    )
    accion = models.CharField(
        max_length=20,
        choices=AccionAuditoriaMoneda.choices,
        verbose_name="Acción",
    )
    datos_anteriores = models.JSONField(null=True, blank=True, verbose_name="Datos anteriores")
    datos_nuevos = models.JSONField(verbose_name="Datos nuevos")
    realizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modificaciones_monedas",
        verbose_name="Realizado por",
    )
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    objects = AuditoriaMonedaManager()

    class Meta:
        """Define el orden y los nombres de presentación de la auditoría de monedas."""
        ordering = ["-fecha"]
        verbose_name = "Auditoría de moneda"
        verbose_name_plural = "Auditorías de monedas"

    def __str__(self):
        """Devuelve una etiqueta legible del registro de auditoría.

        Returns:
            str: Acción realizada y código de la moneda afectada.
        """
        return f"{self.get_accion_display()} - {self.moneda_id}"


class ConfiguracionComision(models.Model):
    """Almacena los porcentajes de comisión que la casa de cambios aplica a sus operaciones.

    Existe una única fila en la tabla: la configuración es global al sistema y
    el administrador la edita desde la sección Configuración. Toda lectura
    debe realizarse mediante :meth:`obtener`, que crea la fila con valores en
    cero si todavía no existe.

    Los porcentajes se registran como copia en cada transacción, de modo que
    un cambio posterior en esta configuración no altera las operaciones ya
    generadas.
    """
    porcentaje_compra = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Comisión de compra (%)",
    )
    porcentaje_venta = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Comisión de venta (%)",
    )
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name="Última modificación")
    modificado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comisiones_configuradas",
        verbose_name="Modificado por",
    )

    class Meta:
        """Define los nombres de presentación de la configuración de comisiones."""
        verbose_name = "Configuración de comisiones"
        verbose_name_plural = "Configuración de comisiones"

    @classmethod
    def obtener(cls):
        """Devuelve la configuración vigente, creándola en cero si no existe.

        Returns:
            ConfiguracionComision: Única instancia de configuración del sistema.
        """
        configuracion, _ = cls.objects.get_or_create(pk=1)
        return configuracion

    def save(self, *args, **kwargs):
        """Guarda la configuración forzando siempre la misma clave primaria.

        Args:
            *args: Argumentos posicionales del método save original.
            **kwargs: Opciones del método save original.
        """
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        """Devuelve una etiqueta legible de los porcentajes configurados.

        Returns:
            str: Comisión de compra y de venta vigentes.
        """
        return f"Compra {self.porcentaje_compra}% - Venta {self.porcentaje_venta}%"
