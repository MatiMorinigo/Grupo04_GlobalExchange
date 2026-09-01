from django.db import migrations


MONEDAS_BASE = [
    ("PYG", "Guaraní paraguayo", "Gs"),
    ("USD", "Dólar estadounidense", "US$"),
    ("BRL", "Real brasileño", "R$"),
    ("EUR", "Euro", "€"),
]


def cargar_monedas_base(apps, schema_editor):
    Moneda = apps.get_model("cotizaciones", "Moneda")

    for codigo, nombre, simbolo in MONEDAS_BASE:
        Moneda.objects.update_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "simbolo": simbolo,
                "activa": True,
            },
        )


def quitar_monedas_base(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cotizaciones", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar_monedas_base, quitar_monedas_base),
    ]
