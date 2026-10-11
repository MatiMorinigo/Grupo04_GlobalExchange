from django.core.management.base import BaseCommand

from transacciones.services import sincronizar_pagos_stripe


class Command(BaseCommand):
    """Consulta a Stripe los pagos en proceso y aplica su resultado."""

    help = (
        "Consulta en Stripe los pagos que siguen sin confirmar y los confirma o "
        "rechaza. Es el respaldo del webhook cuando la notificación no llegó."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--id-pago",
            type=int,
            help="Consulta solamente el pago indicado.",
        )

    def handle(self, *args, **options):
        resumen = sincronizar_pagos_stripe(id_pago=options["id_pago"])

        mensaje = (
            "Sincronización completada. "
            f"Pagos consultados: {resumen['consultados']}. "
            f"Confirmados: {resumen['confirmados']}. "
            f"Rechazados: {resumen['rechazados']}. "
            f"Sin cambios: {resumen['sin_cambios']}. "
            f"Errores: {resumen['errores']}."
        )
        estilo = self.style.WARNING if resumen["errores"] else self.style.SUCCESS
        self.stdout.write(estilo(mensaje))
