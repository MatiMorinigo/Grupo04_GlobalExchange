from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clientes", "0006_alter_configuracionbeneficiocategoria_limite_mensual_pyg_and_more"),
        ("cotizaciones", "0005_merge_scrum51_scrum57"),
    ]

    operations = [
        migrations.CreateModel(
            name="Transaccion",
            fields=[
                ("id_transaccion", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "tipo_operacion",
                    models.CharField(
                        choices=[("COMPRA", "Compra de divisas"), ("VENTA", "Venta de divisas")],
                        max_length=6,
                        verbose_name="Tipo de operacion",
                    ),
                ),
                (
                    "tasa_aplicada",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))],
                        verbose_name="Tasa aplicada",
                    ),
                ),
                ("fecha_vigencia_tasa", models.DateTimeField(verbose_name="Vigencia de la tasa aplicada")),
                (
                    "monto_divisa",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                        verbose_name="Monto en divisa",
                    ),
                ),
                (
                    "subtotal_pyg",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        verbose_name="Subtotal en PYG",
                    ),
                ),
                (
                    "categoria_aplicada",
                    models.CharField(
                        choices=[
                            ("MINORISTA", "Minorista"),
                            ("CORPORATIVO", "Corporativo"),
                            ("VIP", "VIP"),
                        ],
                        max_length=11,
                        verbose_name="Categoria aplicada",
                    ),
                ),
                (
                    "beneficio_porcentaje",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=5,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00")),
                            django.core.validators.MaxValueValidator(Decimal("30.00")),
                        ],
                        verbose_name="Porcentaje de beneficio",
                    ),
                ),
                (
                    "limite_beneficio_pyg",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        verbose_name="Limite de beneficio en PYG",
                    ),
                ),
                (
                    "monto_beneficiado_pyg",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        verbose_name="Monto beneficiado en PYG",
                    ),
                ),
                (
                    "beneficio_monto_pyg",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        verbose_name="Beneficio en PYG",
                    ),
                ),
                (
                    "comision_porcentaje",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=5,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00")),
                            django.core.validators.MaxValueValidator(Decimal("100.00")),
                        ],
                        verbose_name="Porcentaje de comision",
                    ),
                ),
                (
                    "comision_monto_pyg",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        verbose_name="Comision en PYG",
                    ),
                ),
                (
                    "total_pyg",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        verbose_name="Total final en PYG",
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "Pendiente"),
                            ("COMPLETADA", "Completada"),
                            ("CANCELADA", "Cancelada"),
                            ("ANULADA", "Anulada"),
                        ],
                        default="PENDIENTE",
                        max_length=10,
                        verbose_name="Estado",
                    ),
                ),
                ("cancelada_en", models.DateTimeField(blank=True, null=True, verbose_name="Cancelada el")),
                (
                    "etapa_cancelacion",
                    models.CharField(
                        blank=True,
                        choices=[("PREVIA_PAGO", "Durante el proceso previo al pago")],
                        max_length=20,
                        null=True,
                        verbose_name="Etapa de cancelacion",
                    ),
                ),
                ("motivo_cancelacion", models.TextField(blank=True, verbose_name="Motivo de cancelacion")),
                ("completada_en", models.DateTimeField(blank=True, null=True, verbose_name="Completada el")),
                ("creada_en", models.DateTimeField(auto_now_add=True, verbose_name="Creada el")),
                ("actualizada_en", models.DateTimeField(auto_now=True, verbose_name="Ultima actualizacion")),
                (
                    "cliente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transacciones",
                        to="clientes.cliente",
                        verbose_name="Cliente",
                    ),
                ),
                (
                    "creada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="transacciones_creadas",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creada por",
                    ),
                ),
                (
                    "moneda",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transacciones",
                        to="cotizaciones.moneda",
                        verbose_name="Moneda extranjera",
                    ),
                ),
                (
                    "tasa_cambio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transacciones",
                        to="cotizaciones.tasacambio",
                        verbose_name="Tasa de cambio",
                    ),
                ),
            ],
            options={
                "verbose_name": "Transaccion",
                "verbose_name_plural": "Transacciones",
                "ordering": ["-creada_en"],
                "indexes": [
                    models.Index(fields=["cliente", "-creada_en"], name="trans_cliente_fecha_idx"),
                    models.Index(fields=["estado", "-creada_en"], name="trans_estado_fecha_idx"),
                    models.Index(fields=["tipo_operacion", "-creada_en"], name="trans_tipo_fecha_idx"),
                    models.Index(fields=["moneda", "-creada_en"], name="trans_moneda_fecha_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("moneda", "PYG"), _negated=True),
                        name="transaccion_moneda_no_pyg",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("tasa_aplicada__gt", 0)),
                        name="transaccion_tasa_positiva",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("monto_divisa__gt", 0)),
                        name="transaccion_monto_divisa_positivo",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("subtotal_pyg__gte", 0)),
                        name="transaccion_subtotal_no_negativo",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("beneficio_porcentaje__gte", 0),
                            ("beneficio_porcentaje__lte", 30),
                        ),
                        name="transaccion_beneficio_pct_valido",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("limite_beneficio_pyg__gte", 0)),
                        name="transaccion_limite_benef_no_neg",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("monto_beneficiado_pyg__gte", 0)),
                        name="transaccion_monto_benef_no_neg",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("monto_beneficiado_pyg__lte", models.F("subtotal_pyg"))),
                        name="transaccion_monto_benef_subtotal",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("monto_beneficiado_pyg__lte", models.F("limite_beneficio_pyg"))),
                        name="transaccion_monto_benef_limite",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("beneficio_monto_pyg__gte", 0)),
                        name="transaccion_beneficio_no_neg",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("comision_porcentaje__gte", 0),
                            ("comision_porcentaje__lte", 100),
                        ),
                        name="transaccion_comision_pct_valida",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("comision_monto_pyg__gte", 0)),
                        name="transaccion_comision_no_neg",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("total_pyg__gte", 0)),
                        name="transaccion_total_no_negativo",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("cancelada_en__isnull", False),
                                ("estado", "CANCELADA"),
                                ("etapa_cancelacion__isnull", False),
                            )
                            | models.Q(
                                models.Q(("estado", "CANCELADA"), _negated=True),
                                ("cancelada_en__isnull", True),
                                ("etapa_cancelacion__isnull", True),
                            )
                        ),
                        name="transaccion_cancelacion_coherente",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("completada_en__isnull", False),
                                ("estado__in", ["COMPLETADA", "ANULADA"]),
                            )
                            | models.Q(
                                ("completada_en__isnull", True),
                                ("estado__in", ["PENDIENTE", "CANCELADA"]),
                            )
                        ),
                        name="transaccion_finalizacion_coherente",
                    ),
                ],
            },
        ),
    ]
