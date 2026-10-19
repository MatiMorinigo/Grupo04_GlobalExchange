"""Prepara el webhook local usando la misma cuenta de Stripe que Django."""

import os
import re
import shutil
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from dotenv import dotenv_values, set_key


EVENTOS = "payment_intent.succeeded,payment_intent.payment_failed"


class Command(BaseCommand):
    help = "Configura en .env el webhook de Stripe CLI; opcionalmente escucha eventos locales."
    # Permite reparar un secreto de webhook ausente o incorrecto.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--escuchar", action="store_true", help="Mantiene Stripe CLI escuchando.")
        parser.add_argument("--puerto", type=int, default=8000, help="Puerto local de Django (8000).")

    def handle(self, *args, **options):
        clave = settings.STRIPE_SECRET_KEY
        if not clave.startswith("sk_test_") or len(clave) <= len("sk_test_"):
            raise CommandError("Configurá STRIPE_SECRET_KEY con una clave sk_test_... en .env.")
        if not 1 <= options["puerto"] <= 65535:
            raise CommandError("El puerto debe estar entre 1 y 65535.")
        ejecutable = shutil.which("stripe")
        if not ejecutable:
            raise CommandError("Instalá Stripe CLI y agregalo al PATH: https://docs.stripe.com/cli/install")
        archivo_env = settings.BASE_DIR / ".env"
        if not archivo_env.is_file():
            raise CommandError("Creá .env a partir de .env.example antes de configurar Stripe.")

        # La clave viaja por el entorno del proceso, no por argumentos ni logs.
        entorno = {**os.environ, "STRIPE_API_KEY": clave}
        comando = [ejecutable, "listen", "--events", EVENTOS, "--skip-update"]
        try:
            resultado = subprocess.run(
                [*comando, "--print-secret"], env=entorno,
                capture_output=True, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise CommandError("No se pudo ejecutar Stripe CLI. Verificá acceso a Internet y permisos.") from None
        secreto = resultado.stdout.strip()
        if resultado.returncode != 0 or not re.fullmatch(r"whsec_[A-Za-z0-9]+", secreto):
            # No reproducir la salida del CLI: puede contener credenciales.
            raise CommandError("Stripe CLI no pudo obtener el secreto. Verificá la clave de prueba y la conexión.")
        secreto_entorno = os.environ.get("STRIPE_WEBHOOK_SECRET")
        secreto_archivo = dotenv_values(archivo_env).get("STRIPE_WEBHOOK_SECRET", "")
        if (secreto_entorno is not None
                and secreto_entorno.strip() not in (secreto, secreto_archivo)):
            raise CommandError(
                "STRIPE_WEBHOOK_SECRET del entorno difiere del CLI y tiene prioridad sobre .env. "
                "Quitá esa variable del entorno y repetí el comando."
            )
        try:
            set_key(str(archivo_env), "STRIPE_WEBHOOK_SECRET", secreto, quote_mode="never")
        except OSError:
            raise CommandError("No se pudo actualizar .env. Verificá los permisos del archivo.") from None
        destino = f"http://127.0.0.1:{options['puerto']}{reverse('webhook-stripe')}"
        self.stdout.write(self.style.SUCCESS("Webhook de prueba configurado en .env sin mostrar credenciales."))
        self.stdout.write(f"Destino: {destino}")
        self.stdout.write("Iniciá o reiniciá Django para cargar el secreto actualizado.")
        if options["escuchar"]:
            self.stdout.write("Escuchando eventos de Stripe. Dejá esta terminal abierta; Ctrl+C para salir.")
            try:
                proceso = subprocess.run([*comando, "--forward-to", destino], env=entorno, check=False)
            except KeyboardInterrupt:
                return
            except OSError:
                raise CommandError("No se pudo iniciar la escucha de Stripe CLI.") from None
            if proceso.returncode:
                raise CommandError("La escucha de Stripe CLI terminó con un error.")
        else:
            self.stdout.write("Para escuchar: python manage.py configurar_stripe --escuchar")
