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
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal

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


class DenominacionBillete(models.Model):
    """Catálogo de billetes admitidos; reutiliza las monedas de cotizaciones."""

    moneda = models.ForeignKey(
        "cotizaciones.Moneda", on_delete=models.PROTECT, related_name="denominaciones"
    )
    valor = models.DecimalField(
        max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["moneda_id", "valor"]
        verbose_name = "Denominación de billete"
        verbose_name_plural = "Denominaciones de billetes"
        constraints = [
            models.UniqueConstraint(fields=["moneda", "valor"], name="billete_moneda_valor_unico"),
            models.CheckConstraint(condition=models.Q(valor__gt=0), name="billete_valor_positivo"),
        ]

    def __str__(self):
        return f"{self.moneda_id} — {self.valor}"


class AperturaCaja(models.Model):
    """Sesión operativa independiente del horario programado de la asignación.

    Crear mediante ``cajas.services.abrir_caja`` para validar el inventario
    completo y la identidad OIDC dentro de una única transacción.
    """

    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        CERRADA = "CERRADA", "Cerrada"

    id_apertura = models.BigAutoField(primary_key=True)
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="aperturas")
    asignacion = models.ForeignKey(
        AsignacionCaja, on_delete=models.PROTECT, related_name="aperturas"
    )
    cajero_keycloak_id = models.UUIDField(editable=False, db_index=True)
    fecha_apertura = models.DateTimeField(default=timezone.now, editable=False)
    estado = models.CharField(max_length=7, choices=Estado.choices, default=Estado.ABIERTA)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_apertura"]
        verbose_name = "Apertura de caja"
        verbose_name_plural = "Aperturas de caja"
        constraints = [
            models.UniqueConstraint(
                fields=["caja"], condition=models.Q(estado="ABIERTA"),
                name="caja_apertura_activa_unica",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(estado="ABIERTA", fecha_cierre__isnull=True)
                    | models.Q(estado="CERRADA", fecha_cierre__isnull=False,
                               fecha_cierre__gte=models.F("fecha_apertura"))
                ),
                name="apertura_cierre_coherente",
            ),
        ]

    def clean(self):
        super().clean()
        if self.asignacion_id:
            asignacion = self.asignacion
            if (self.caja_id != asignacion.caja_id
                    or self.cajero_keycloak_id != asignacion.cajero_keycloak_id):
                raise ValidationError("La caja y el cajero deben coincidir con la asignación.")

    @property
    def saldos_iniciales(self):
        """Devuelve {código de moneda: Decimal}, sin conversión de divisas."""
        return dict(self.detalles_inventario.order_by().values("moneda_id").annotate(
            saldo=models.Sum(
                models.F("valor_denominacion") * models.F("cantidad"),
                output_field=models.DecimalField(max_digits=32, decimal_places=2),
            )
        ).values_list("moneda_id", "saldo").order_by("moneda_id"))

    @property
    def saldos_actuales(self):
        """Calcula el saldo teórico actual por moneda (saldo inicial + entregas - devoluciones)."""
        saldos = dict(self.saldos_iniciales)
        for remesa in self.remesas.all():
            m_id = remesa.moneda_id
            if m_id not in saldos:
                saldos[m_id] = Decimal("0.00")
            if remesa.tipo == "ENTREGA":
                saldos[m_id] += remesa.monto_total
            elif remesa.tipo == "DEVOLUCION":
                saldos[m_id] -= remesa.monto_total
        return saldos

    def obtener_saldo_actual(self, moneda_id):
        """Devuelve el saldo teórico disponible en esta apertura para la moneda dada."""
        return self.saldos_actuales.get(moneda_id, Decimal("0.00"))

    def obtener_inventario_actual(self, moneda_id=None):
        """Devuelve un diccionario con el stock actual de billetes por denominación."""
        qs_inicial = self.detalles_inventario.select_related("denominacion")
        if moneda_id:
            qs_inicial = qs_inicial.filter(moneda_id=moneda_id)

        inventario = {}
        for d in qs_inicial:
            inventario[d.denominacion_id] = {
                "denominacion": d.denominacion,
                "moneda_id": d.moneda_id,
                "valor": d.valor_denominacion,
                "cantidad": d.cantidad,
            }

        remesas = self.remesas.prefetch_related("detalles__denominacion").all()
        if moneda_id:
            remesas = remesas.filter(moneda_id=moneda_id)

        for r in remesas:
            factor = 1 if r.tipo == "ENTREGA" else -1
            for det in r.detalles.all():
                d_id = det.denominacion_id
                if d_id not in inventario:
                    inventario[d_id] = {
                        "denominacion": det.denominacion,
                        "moneda_id": det.denominacion.moneda_id,
                        "valor": det.valor_denominacion,
                        "cantidad": 0,
                    }
                inventario[d_id]["cantidad"] += factor * det.cantidad
        return inventario

    def __str__(self):
        return f"Apertura {self.pk} — {self.caja} ({self.get_estado_display()})"


class DetalleInventarioInicial(models.Model):
    """Conteo inicial y copia histórica de los valores del catálogo al abrir."""

    apertura = models.ForeignKey(
        AperturaCaja, on_delete=models.PROTECT, related_name="detalles_inventario"
    )
    denominacion = models.ForeignKey(
        DenominacionBillete, on_delete=models.PROTECT, related_name="detalles_iniciales"
    )
    moneda = models.ForeignKey("cotizaciones.Moneda", on_delete=models.PROTECT, editable=False)
    valor_denominacion = models.DecimalField(max_digits=18, decimal_places=2, editable=False)
    cantidad = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(2147483647)]
    )

    class Meta:
        ordering = ["moneda_id", "valor_denominacion"]
        constraints = [
            models.UniqueConstraint(
                fields=["apertura", "denominacion"], name="inventario_denominacion_unica"
            ),
            models.UniqueConstraint(
                fields=["apertura", "moneda", "valor_denominacion"],
                name="inventario_moneda_valor_unico",
            ),
            models.CheckConstraint(condition=models.Q(cantidad__gte=0), name="inventario_cantidad_no_negativa"),
            models.CheckConstraint(condition=models.Q(valor_denominacion__gt=0), name="inventario_valor_positivo"),
        ]

    @property
    def subtotal(self):
        return self.valor_denominacion * self.cantidad


class Remesa(models.Model):
    """Registro de transferencias de efectivo entre Tesorería y una caja (HU-36)."""

    class Tipo(models.TextChoices):
        ENTREGA = "ENTREGA", "Entrega (Tesorería → Caja)"
        DEVOLUCION = "DEVOLUCION", "Devolución (Caja → Tesorería)"

    id_remesa = models.BigAutoField(primary_key=True)
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="remesas")
    apertura = models.ForeignKey(
        AperturaCaja, on_delete=models.PROTECT, related_name="remesas"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    origen = models.CharField(max_length=150)
    destino = models.CharField(max_length=150)
    moneda = models.ForeignKey(
        "cotizaciones.Moneda", on_delete=models.PROTECT, related_name="remesas"
    )
    monto_total = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    fecha_hora = models.DateTimeField(default=timezone.now, editable=False)
    usuario_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="remesas_registradas",
    )
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-fecha_hora"]
        verbose_name = "Remesa de efectivo"
        verbose_name_plural = "Remesas de efectivo"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto_total__gt=0),
                name="remesa_monto_positivo",
            ),
        ]

    def clean(self):
        super().clean()
        if self.caja_id and self.apertura_id and self.apertura.caja_id != self.caja_id:
            raise ValidationError("La apertura seleccionada no corresponde a la caja indicada.")
        if self.tipo == self.Tipo.ENTREGA:
            if not self.origen:
                self.origen = "Tesorería"
            if not self.destino and self.caja_id:
                self.destino = f"Caja {self.caja.codigo} - {self.caja.nombre}"
        elif self.tipo == self.Tipo.DEVOLUCION:
            if not self.origen and self.caja_id:
                self.origen = f"Caja {self.caja.codigo} - {self.caja.nombre}"
            if not self.destino:
                self.destino = "Tesorería"

    def __str__(self):
        return f"Remesa #{self.pk} ({self.get_tipo_display()}) — {self.moneda_id} {self.monto_total}"


class DetalleRemesa(models.Model):
    """Desglose de billetes por denominación de una remesa de efectivo (HU-36)."""

    remesa = models.ForeignKey(
        Remesa, on_delete=models.CASCADE, related_name="detalles"
    )
    denominacion = models.ForeignKey(
        DenominacionBillete, on_delete=models.PROTECT, related_name="detalles_remesa"
    )
    valor_denominacion = models.DecimalField(max_digits=18, decimal_places=2, editable=False)
    cantidad = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(2147483647)]
    )

    class Meta:
        ordering = ["denominacion__valor"]
        verbose_name = "Detalle de remesa"
        verbose_name_plural = "Detalles de remesa"
        constraints = [
            models.UniqueConstraint(
                fields=["remesa", "denominacion"],
                name="remesa_denominacion_unica",
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name="remesa_cantidad_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_denominacion__gt=0),
                name="remesa_valor_denominacion_positivo",
            ),
        ]

    def clean(self):
        super().clean()
        if self.denominacion_id and self.remesa_id and self.denominacion.moneda_id != self.remesa.moneda_id:
            raise ValidationError("La denominación no corresponde a la moneda de la remesa.")

    def save(self, *args, **kwargs):
        if not self.valor_denominacion and self.denominacion_id:
            self.valor_denominacion = self.denominacion.valor
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return self.valor_denominacion * self.cantidad


class CierreCaja(models.Model):
    """Registro de cierre y arqueo de caja (HU-37)."""

    id_cierre = models.BigAutoField(primary_key=True)
    apertura = models.OneToOneField(
        AperturaCaja,
        on_delete=models.PROTECT,
        related_name="cierre",
    )
    fecha_cierre = models.DateTimeField(default=timezone.now, editable=False)
    usuario_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cierres_registrados",
    )
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-fecha_cierre"]
        verbose_name = "Cierre de caja"
        verbose_name_plural = "Cierres de caja"

    @property
    def caja(self):
        return self.apertura.caja

    @property
    def hay_diferencias(self):
        """Indica si al menos una moneda tuvo faltante o sobrante."""
        return any(d.diferencia != Decimal("0.00") for d in self.detalles.all())

    def __str__(self):
        return f"Cierre #{self.pk} — Apertura #{self.apertura_id} ({self.caja})"


class DetalleCierreCaja(models.Model):
    """Consolidado de arqueo por moneda con saldo teórico, físico y diferencia (HU-37)."""

    cierre = models.ForeignKey(
        CierreCaja,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    moneda = models.ForeignKey(
        "cotizaciones.Moneda",
        on_delete=models.PROTECT,
        related_name="detalles_cierre",
    )
    saldo_teorico = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )
    saldo_fisico = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )
    diferencia = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    class Meta:
        ordering = ["moneda__codigo"]
        verbose_name = "Detalle de cierre de caja"
        verbose_name_plural = "Detalles de cierre de caja"
        constraints = [
            models.UniqueConstraint(
                fields=["cierre", "moneda"],
                name="cierre_moneda_unica",
            ),
        ]

    @property
    def estado_arqueo(self):
        if self.diferencia > Decimal("0.00"):
            return "SOBRANTE"
        if self.diferencia < Decimal("0.00"):
            return "FALTANTE"
        return "CUADRADO"

    def __str__(self):
        return f"Cierre #{self.cierre_id} — {self.moneda_id}: Teórico {self.saldo_teorico}, Físico {self.saldo_fisico}, Dif {self.diferencia}"


class ToleranciaArqueo(models.Model):
    """Diferencia máxima tolerada en el arqueo para una moneda (HU-32).

    Se compara en valor absoluto, en la propia moneda, sin conversión. Una
    moneda sin fila se trata como tolerancia cero. El cero es un valor válido.
    """

    moneda = models.OneToOneField(
        "cotizaciones.Moneda",
        on_delete=models.PROTECT,
        related_name="tolerancia_arqueo",
    )
    monto_maximo = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Diferencia máxima tolerada",
    )
    fecha_modificacion = models.DateTimeField(auto_now=True)
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tolerancias_arqueo_modificadas",
    )

    class Meta:
        ordering = ["moneda__codigo"]
        verbose_name = "Tolerancia de arqueo"
        verbose_name_plural = "Tolerancias de arqueo"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto_maximo__gte=0),
                name="tolerancia_arqueo_no_negativa",
            ),
        ]

    def __str__(self):
        return f"{self.moneda_id}: {self.monto_maximo}"


class AlertaArqueo(models.Model):
    """Alerta generada cuando un cierre supera la tolerancia en alguna moneda (HU-32).

    Hay a lo sumo una por cierre, que a su vez es único por apertura.
    """

    id_alerta = models.BigAutoField(primary_key=True)
    cierre = models.OneToOneField(
        CierreCaja,
        on_delete=models.PROTECT,
        related_name="alerta",
    )
    fecha_creacion = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Alerta de arqueo"
        verbose_name_plural = "Alertas de arqueo"

    def __str__(self):
        return f"Alerta #{self.pk} — Cierre #{self.cierre_id}"


class DetalleAlertaArqueo(models.Model):
    """Moneda excedida de una alerta, con copia de la tolerancia aplicada."""

    alerta = models.ForeignKey(
        AlertaArqueo,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    moneda = models.ForeignKey(
        "cotizaciones.Moneda",
        on_delete=models.PROTECT,
        related_name="detalles_alerta_arqueo",
    )
    diferencia = models.DecimalField(max_digits=18, decimal_places=2)
    tolerancia_aplicada = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        ordering = ["moneda__codigo"]
        verbose_name = "Detalle de alerta de arqueo"
        verbose_name_plural = "Detalles de alerta de arqueo"
        constraints = [
            models.UniqueConstraint(
                fields=["alerta", "moneda"],
                name="alerta_arqueo_moneda_unica",
            ),
        ]

    @property
    def estado_arqueo(self):
        return "SOBRANTE" if self.diferencia > Decimal("0.00") else "FALTANTE"

    @property
    def diferencia_absoluta(self):
        return abs(self.diferencia)

    def __str__(self):
        return f"{self.moneda_id}: {self.diferencia} (límite {self.tolerancia_aplicada})"


class EnvioAlertaArqueo(models.Model):
    """Resultado del envío de una alerta a un destinatario."""

    class Estado(models.TextChoices):
        ENVIADA = "ENVIADA", "Enviada"
        FALLIDA = "FALLIDA", "Fallida"

    alerta = models.ForeignKey(
        AlertaArqueo,
        on_delete=models.CASCADE,
        related_name="envios",
    )
    email = models.CharField(max_length=254, blank=True, default="")
    rol = models.CharField(max_length=30)
    estado = models.CharField(max_length=7, choices=Estado.choices)
    error = models.TextField(blank=True, default="")
    fecha_envio = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["id"]
        verbose_name = "Envío de alerta de arqueo"
        verbose_name_plural = "Envíos de alertas de arqueo"

    def __str__(self):
        return f"{self.email or self.rol} — {self.get_estado_display()}"


class ConteoBilleteCierre(models.Model):
    """Conteo físico final de billetes por denominación en el arqueo (HU-37)."""

    cierre = models.ForeignKey(
        CierreCaja,
        on_delete=models.CASCADE,
        related_name="conteos_billetes",
    )
    denominacion = models.ForeignKey(
        DenominacionBillete,
        on_delete=models.PROTECT,
        related_name="conteos_cierre",
    )
    valor_denominacion = models.DecimalField(max_digits=18, decimal_places=2, editable=False)
    cantidad = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(2147483647)]
    )

    class Meta:
        ordering = ["denominacion__moneda__codigo", "denominacion__valor"]
        verbose_name = "Conteo de billete en cierre"
        verbose_name_plural = "Conteos de billetes en cierre"
        constraints = [
            models.UniqueConstraint(
                fields=["cierre", "denominacion"],
                name="cierre_denominacion_unica",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.valor_denominacion and self.denominacion_id:
            self.valor_denominacion = self.denominacion.valor
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return self.valor_denominacion * self.cantidad


