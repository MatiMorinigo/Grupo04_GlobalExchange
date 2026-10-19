"""Comprueba la configuración del flujo de tarjetas de prueba de Stripe."""

from django.conf import settings
from django.core.checks import Error, Warning, register


@register("stripe")
def comprobar_stripe(app_configs, **kwargs):
    problemas = []
    clave = settings.STRIPE_SECRET_KEY
    secreto = settings.STRIPE_WEBHOOK_SECRET
    if not clave:
        problemas.append(Warning(
            "Los pagos con tarjeta no están configurados.",
            hint="Completá STRIPE_SECRET_KEY en .env con una clave sk_test_...",
            id="integrations.W001",
        ))
    elif not clave.startswith("sk_test_") or len(clave) <= len("sk_test_"):
        problemas.append(Error(
            "Este flujo de tarjetas requiere una clave de prueba de Stripe.",
            hint="Usá STRIPE_SECRET_KEY=sk_test_...; las tarjetas pm_card_* son de prueba.",
            id="integrations.E001",
        ))
    if not secreto:
        problemas.append(Warning(
            "Los pagos de Stripe no podrán confirmarse mediante el webhook.",
            hint="Ejecutá python manage.py configurar_stripe para preparar el webhook local.",
            id="integrations.W002",
        ))
    elif not secreto.startswith("whsec_") or len(secreto) <= len("whsec_"):
        problemas.append(Error(
            "STRIPE_WEBHOOK_SECRET debe ser un secreto whsec_...",
            hint="En desarrollo obtenelo con python manage.py configurar_stripe.",
            id="integrations.E002",
        ))
    return problemas
