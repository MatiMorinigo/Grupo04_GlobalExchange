from django.db import migrations


def cargar_configuracion_comision(apps, schema_editor):
    ConfiguracionComision = apps.get_model(
        "cotizaciones",
        "ConfiguracionComision",
    )

    ConfiguracionComision.objects.get_or_create(
        pk=1,
        defaults={
            "porcentaje_compra": 0,
            "porcentaje_venta": 0,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("cotizaciones", "0006_configuracioncomision"),
    ]

    operations = [
        migrations.RunPython(
            cargar_configuracion_comision,
            migrations.RunPython.noop,
        ),
    ]
