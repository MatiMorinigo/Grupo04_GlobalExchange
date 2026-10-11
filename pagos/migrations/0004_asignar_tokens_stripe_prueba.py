"""Asigna el token de Stripe a las tarjetas de prueba registradas antes de HU-15.

Como el número completo nunca se guardó, la tarjeta se reconoce por sus
últimos cuatro dígitos, que coinciden con los de las tarjetas de prueba
oficiales de Stripe.
"""

from django.db import migrations


TOKENS_POR_ULTIMOS_DIGITOS = {
    "4242": "pm_card_visa",
    "0002": "pm_card_chargeDeclined",
    "9995": "pm_card_chargeDeclinedInsufficientFunds",
}
TIPOS_TARJETA = ("TARJETA_CREDITO", "TARJETA_DEBITO")


def asignar_tokens(apps, schema_editor):
    """Completa el token de las tarjetas existentes que no lo tienen."""
    MetodoPago = apps.get_model("pagos", "MetodoPago")
    for digitos, token in TOKENS_POR_ULTIMOS_DIGITOS.items():
        MetodoPago.objects.filter(
            tipo__in=TIPOS_TARJETA,
            ultimos_cuatro_digitos=digitos,
            stripe_payment_method_id="",
        ).update(stripe_payment_method_id=token)


def quitar_tokens(apps, schema_editor):
    """Deja sin token a todas las tarjetas, como antes de la migración."""
    MetodoPago = apps.get_model("pagos", "MetodoPago")
    MetodoPago.objects.update(stripe_payment_method_id="")


class Migration(migrations.Migration):

    dependencies = [
        ("pagos", "0003_metodopago_stripe_payment_method_id"),
    ]

    operations = [
        migrations.RunPython(asignar_tokens, quitar_tokens),
    ]
