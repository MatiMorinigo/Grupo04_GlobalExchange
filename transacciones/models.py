from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from clientes.models import CategoriaCliente, Cliente
from cotizaciones.models import Moneda, TasaCambio


User = get_user_model()
PYG = "PYG"


class TipoOperacion(models.TextChoices):
    """Define la operacion desde la perspectiva del cliente."""

    COMPRA = "COMPRA", "Compra de divisas"
    VENTA = "VENTA", "Venta de divisas"


class EstadoTransaccion(models.TextChoices):
    """Define las etapas principales del ciclo de vida de una transaccion."""

    PENDIENTE = "PENDIENTE", "Pendiente"
    COMPLETADA = "COMPLETADA", "Completada"
    CANCELADA = "CANCELADA", "Cancelada"
    ANULADA = "ANULADA", "Anulada"


class EtapaCancelacion(models.TextChoices):
    """Identifica en que momento se cancelo una transaccion sin pago."""

    PREVIA_PAGO = "PREVIA_PAGO", "Durante el proceso previo al pago"


class Transaccion(models.Model):
    """Conserva las condiciones e importes aplicados a una operacion cambiaria.

    Todas las operaciones involucran PYG y una moneda extranjera. El tipo de
    operacion determina si el cliente entrega o recibe los guaranies.
    """

    id_transaccion = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="transacciones",
        verbose_name="Cliente",
    )
    creada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transacciones_creadas",
        verbose_name="Creada por",
    )
    tipo_operacion = models.CharField(
        max_length=6,
        choices=TipoOperacion.choices,
        verbose_name="Tipo de operacion",
    )
    moneda = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="transacciones",
        verbose_name="Moneda extranjera",
    )
    tasa_cambio = models.ForeignKey(
        TasaCambio,
        on_delete=models.PROTECT,
        related_name="transacciones",
        verbose_name="Tasa de cambio",
    )
    destino_acreditacion = models.ForeignKey(
        "destinos.DestinoAcreditacion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transacciones",
        verbose_name="Destino de acreditacion",
    )
    metodo_pago = models.ForeignKey(
        "pagos.MetodoPago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transacciones",
        verbose_name="Metodo de pago",
    )
    tasa_aplicada = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="Tasa aplicada",
    )
    fecha_vigencia_tasa = models.DateTimeField(
        verbose_name="Vigencia de la tasa aplicada",
    )
    monto_divisa = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Monto en divisa",
    )
    subtotal_pyg = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Subtotal en PYG",
    )
    categoria_aplicada = models.CharField(
        max_length=11,
        choices=CategoriaCliente.choices,
        verbose_name="Categoria aplicada",
    )
    beneficio_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("30.00")),
        ],
        verbose_name="Porcentaje de beneficio",
    )
    limite_beneficio_pyg = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Limite de beneficio en PYG",
    )
    monto_beneficiado_pyg = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Monto beneficiado en PYG",
    )
    beneficio_monto_pyg = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Beneficio en PYG",
    )
    comision_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Porcentaje de comision",
    )
    comision_monto_pyg = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Comision en PYG",
    )
    total_pyg = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Total final en PYG",
    )
    estado = models.CharField(
        max_length=10,
        choices=EstadoTransaccion.choices,
        default=EstadoTransaccion.PENDIENTE,
        verbose_name="Estado",
    )
    cancelada_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Cancelada el",
    )
    etapa_cancelacion = models.CharField(
        max_length=20,
        choices=EtapaCancelacion.choices,
        null=True,
        blank=True,
        verbose_name="Etapa de cancelacion",
    )
    motivo_cancelacion = models.TextField(
        blank=True,
        verbose_name="Motivo de cancelacion",
    )
    completada_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Completada el",
    )
    creada_en = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Creada el",
    )
    actualizada_en = models.DateTimeField(
        auto_now=True,
        verbose_name="Ultima actualizacion",
    )

    class Meta:
        """Define orden, presentacion, filtros frecuentes e integridad."""

        ordering = ["-creada_en"]
        verbose_name = "Transaccion"
        verbose_name_plural = "Transacciones"
        indexes = [
            models.Index(
                fields=["cliente", "-creada_en"],
                name="trans_cliente_fecha_idx",
            ),
            models.Index(
                fields=["estado", "-creada_en"],
                name="trans_estado_fecha_idx",
            ),
            models.Index(
                fields=["tipo_operacion", "-creada_en"],
                name="trans_tipo_fecha_idx",
            ),
            models.Index(
                fields=["moneda", "-creada_en"],
                name="trans_moneda_fecha_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(moneda=PYG),
                name="transaccion_moneda_no_pyg",
            ),
            models.CheckConstraint(
                condition=Q(tasa_aplicada__gt=0),
                name="transaccion_tasa_positiva",
            ),
            models.CheckConstraint(
                condition=Q(monto_divisa__gt=0),
                name="transaccion_monto_divisa_positivo",
            ),
            models.CheckConstraint(
                condition=Q(subtotal_pyg__gte=0),
                name="transaccion_subtotal_no_negativo",
            ),
            models.CheckConstraint(
                condition=Q(
                    beneficio_porcentaje__gte=0,
                    beneficio_porcentaje__lte=30,
                ),
                name="transaccion_beneficio_pct_valido",
            ),
            models.CheckConstraint(
                condition=Q(limite_beneficio_pyg__gte=0),
                name="transaccion_limite_benef_no_neg",
            ),
            models.CheckConstraint(
                condition=Q(monto_beneficiado_pyg__gte=0),
                name="transaccion_monto_benef_no_neg",
            ),
            models.CheckConstraint(
                condition=Q(monto_beneficiado_pyg__lte=models.F("subtotal_pyg")),
                name="transaccion_monto_benef_subtotal",
            ),
            models.CheckConstraint(
                condition=Q(monto_beneficiado_pyg__lte=models.F("limite_beneficio_pyg")),
                name="transaccion_monto_benef_limite",
            ),
            models.CheckConstraint(
                condition=Q(beneficio_monto_pyg__gte=0),
                name="transaccion_beneficio_no_neg",
            ),
            models.CheckConstraint(
                condition=Q(
                    comision_porcentaje__gte=0,
                    comision_porcentaje__lte=100,
                ),
                name="transaccion_comision_pct_valida",
            ),
            models.CheckConstraint(
                condition=Q(comision_monto_pyg__gte=0),
                name="transaccion_comision_no_neg",
            ),
            models.CheckConstraint(
                condition=Q(total_pyg__gte=0),
                name="transaccion_total_no_negativo",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        estado=EstadoTransaccion.CANCELADA,
                        cancelada_en__isnull=False,
                        etapa_cancelacion__isnull=False,
                    )
                    | Q(
                        ~Q(estado=EstadoTransaccion.CANCELADA),
                        cancelada_en__isnull=True,
                        etapa_cancelacion__isnull=True,
                    )
                ),
                name="transaccion_cancelacion_coherente",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        estado__in=[
                            EstadoTransaccion.COMPLETADA,
                            EstadoTransaccion.ANULADA,
                        ],
                        completada_en__isnull=False,
                    )
                    | Q(
                        estado__in=[
                            EstadoTransaccion.PENDIENTE,
                            EstadoTransaccion.CANCELADA,
                        ],
                        completada_en__isnull=True,
                    )
                ),
                name="transaccion_finalizacion_coherente",
            ),
        ]

    def clean(self):
        """Valida la moneda, el par de la tasa y las fechas del estado."""

        super().clean()
        errores = {}

        if self.moneda_id == PYG:
            errores["moneda"] = "La moneda de la transaccion debe ser extranjera."

        if self.tasa_cambio_id and self.moneda_id:
            tasa = self.tasa_cambio
            if tasa.moneda_origen_id != self.moneda_id or tasa.moneda_destino_id != PYG:
                errores["tasa_cambio"] = (
                    "La tasa debe corresponder al par entre la moneda "
                    "seleccionada y PYG."
                )
            elif self.tipo_operacion in TipoOperacion.values:
                tasa_esperada = (
                    tasa.precio_venta
                    if self.tipo_operacion == TipoOperacion.COMPRA
                    else tasa.precio_compra
                )
                if self.tasa_aplicada != tasa_esperada:
                    errores["tasa_aplicada"] = (
                        "La compra debe usar el precio de venta y la venta "
                        "debe usar el precio de compra."
                    )

            if self.fecha_vigencia_tasa != tasa.fecha_vigencia:
                errores["fecha_vigencia_tasa"] = (
                    "La vigencia registrada debe coincidir con la tasa aplicada."
                )

        if self.destino_acreditacion_id:
            destino = self.destino_acreditacion
            if destino.cliente_id != self.cliente_id:
                errores["destino_acreditacion"] = (
                    "El destino de acreditacion debe pertenecer al mismo cliente."
                )
            elif destino.moneda_id != self.moneda_id:
                errores["destino_acreditacion"] = (
                    "El destino de acreditacion debe admitir la moneda de la operacion."
                )

        if self.metodo_pago_id and self.metodo_pago.cliente_id != self.cliente_id:
            errores["metodo_pago"] = (
                "El metodo de pago debe pertenecer al mismo cliente."
            )

        if self.estado == EstadoTransaccion.CANCELADA:
            if not self.cancelada_en:
                errores["cancelada_en"] = "Una transaccion cancelada debe registrar la fecha."
            if not self.etapa_cancelacion:
                errores["etapa_cancelacion"] = (
                    "Una transaccion cancelada debe registrar la etapa de cancelacion."
                )
        elif self.cancelada_en or self.etapa_cancelacion:
            errores["estado"] = (
                "Solo una transaccion cancelada puede contener datos de cancelacion."
            )

        if self.estado in (EstadoTransaccion.COMPLETADA, EstadoTransaccion.ANULADA):
            if not self.completada_en:
                errores["completada_en"] = (
                    "Una transaccion completada o anulada debe registrar su finalizacion."
                )
        elif self.completada_en:
            errores["estado"] = (
                "Solo una transaccion completada o anulada puede tener fecha de finalizacion."
            )

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        """Devuelve una etiqueta breve para listados administrativos."""

        return (
            f"Transaccion {self.id_transaccion} - "
            f"{self.get_tipo_operacion_display()} {self.moneda_id}"
        )
