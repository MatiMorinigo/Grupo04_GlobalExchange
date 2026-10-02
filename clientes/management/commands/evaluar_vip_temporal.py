from datetime import date

from django.core.management.base import BaseCommand, CommandError

from clientes.services import evaluar_vip_temporal


class Command(BaseCommand):
    """Ejecuta la evaluación mensual de promociones VIP temporales."""

    help = "Evalúa el volumen del mes anterior y asigna o renueva VIP temporal."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fecha",
            type=str,
            help="Fecha de referencia en formato YYYY-MM-DD. "
                 "Si se omite, utiliza la fecha actual.",
        )

    def handle(self, *args, **options):
        fecha_referencia = None

        if options["fecha"]:
            try:
                fecha_referencia = date.fromisoformat(options["fecha"])
            except ValueError as exc:
                raise CommandError(
                    "La fecha debe tener formato YYYY-MM-DD."
                ) from exc

        resultado = evaluar_vip_temporal(
            fecha_referencia=fecha_referencia
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Evaluación VIP completada. "
                f"Clientes evaluados: {resultado['evaluados']}. "
                f"Clientes actualizados: {resultado['actualizados']}."
            )
        )