import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Migración inicial de la app pagos — crea la tabla MetodoPago (HU27)."""

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MetodoPago",
            fields=[
                (
                    "id_metodo_pago",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                (
                    "nombre",
                    models.CharField(
                        max_length=100,
                        unique=True,
                        verbose_name="Nombre",
                    ),
                ),
                (
                    "descripcion",
                    models.TextField(blank=True, verbose_name="Descripción"),
                ),
                (
                    "habilitado",
                    models.BooleanField(default=True, verbose_name="Habilitado"),
                ),
                (
                    "creado_en",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creado el"
                    ),
                ),
                (
                    "actualizado_en",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Última modificación"
                    ),
                ),
                (
                    "creado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="metodos_pago_creados",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creado por",
                    ),
                ),
                (
                    "modificado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="metodos_pago_modificados",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Modificado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Método de pago",
                "verbose_name_plural": "Métodos de pago",
                "ordering": ["nombre"],
            },
        ),
    ]
