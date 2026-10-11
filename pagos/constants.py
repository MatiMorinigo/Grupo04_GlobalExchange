"""Catálogos compartidos por los formularios que registran datos de pago o acreditación."""


PROVEEDORES_BILLETERA = [
    ("Tigo Money", "Tigo Money"),
    ("Personal Pay", "Personal Pay"),
    ("Giros Claro", "Giros Claro"),
]
"""list[tuple[str, str]]: Proveedores de billetera electrónica admitidos.

Se comparte entre los métodos de pago del cliente y sus destinos de
acreditación para que ambos ofrezcan exactamente el mismo catálogo.
"""


TARJETAS_PRUEBA_STRIPE = {
    "4242424242424242": "pm_card_visa",
    "4000000000000002": "pm_card_chargeDeclined",
    "4000000000009995": "pm_card_chargeDeclinedInsufficientFunds",
}
"""dict[str, str]: Tarjetas de prueba oficiales de Stripe y su token de pago.

Al registrar una de estas tarjetas se guarda el token ``pm_card_*`` que
Stripe acepta en modo test, en lugar del número. La primera es aprobada,
la segunda rechazada por el emisor y la tercera rechazada por fondos
insuficientes. Cualquier otra tarjeta queda sin token y no puede pagarse en
línea.
"""
