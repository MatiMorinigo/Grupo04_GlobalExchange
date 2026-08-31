from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("clientes", "0003_alter_cliente_categoria"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SolicitudAsociacion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "Pendiente"),
                            ("APROBADA", "Aprobada"),
                            ("RECHAZADA", "Rechazada"),
                        ],
                        default="PENDIENTE",
                        max_length=10,
                        verbose_name="Estado",
                    ),
                ),
                (
                    "fecha_solicitud",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Fecha de solicitud",
                    ),
                ),
                (
                    "fecha_resolucion",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Fecha de resolución",
                    ),
                ),
                (
                    "cliente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="solicitudes_asociacion",
                        to="clientes.cliente",
                        verbose_name="Cliente",
                    ),
                ),
                (
                    "resuelto_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="solicitudes_resueltas",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Resuelto por",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="solicitudes_asociacion",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Usuario",
                    ),
                ),
            ],
            options={
                "verbose_name": "Solicitud de asociación",
                "verbose_name_plural": "Solicitudes de asociación",
                "ordering": ["-fecha_solicitud"],
            },
        ),
        migrations.CreateModel(
            name="UsuarioCliente",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "usuario",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="perfil",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Usuario",
                    ),
                ),
                (
                    "cliente_activo",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="usuarios_activos",
                        to="clientes.cliente",
                        verbose_name="Cliente activo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Asociación usuario-cliente",
                "verbose_name_plural": "Asociaciones usuario-cliente",
            },
        ),
        migrations.AddConstraint(
            model_name="solicitudasociacion",
            constraint=models.UniqueConstraint(
                condition=models.Q(estado="PENDIENTE"),
                fields=["usuario", "cliente"],
                name="unique_solicitud_pendiente",
            ),
        ),
    ]
