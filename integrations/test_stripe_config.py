"""Verifica la separación del modo de prueba y la preparación del webhook."""

import os
import subprocess
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from dotenv import dotenv_values

from .checks import comprobar_stripe


@override_settings(STRIPE_SECRET_KEY="sk_test_prueba", STRIPE_WEBHOOK_SECRET="whsec_prueba")
class ConfiguracionStripeTests(SimpleTestCase):
    def test_configuracion_de_prueba_valida(self):
        self.assertEqual(comprobar_stripe(None), [])

    def test_clave_live_rechazada_sin_exponerla(self):
        with override_settings(STRIPE_SECRET_KEY="sk_live_no_publicar"):
            problemas = comprobar_stripe(None)
        self.assertEqual([p.id for p in problemas], ["integrations.E001"])
        self.assertNotIn("sk_live_no_publicar", str(problemas))

    def test_faltan_credenciales(self):
        with override_settings(STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET=""):
            self.assertEqual(
                [p.id for p in comprobar_stripe(None)],
                ["integrations.W001", "integrations.W002"],
            )

    def test_secreto_incorrecto(self):
        with override_settings(STRIPE_WEBHOOK_SECRET="sk_test_equivocado"):
            self.assertEqual([p.id for p in comprobar_stripe(None)], ["integrations.E002"])


@override_settings(STRIPE_SECRET_KEY="sk_test_privada")
class ConfigurarStripeCommandTests(SimpleTestCase):
    def setUp(self):
        temporal = TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.archivo = self.raiz / ".env"
        self.original = "# Conservar configuración\nDB_NAME=global_exchange\nSTRIPE_WEBHOOK_SECRET=whsec_anterior\n"
        self.archivo.write_text(self.original, encoding="utf-8")
        configuracion = override_settings(BASE_DIR=self.raiz)
        configuracion.enable()
        self.addCleanup(configuracion.disable)
        entorno = patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_anterior"})
        entorno.start()
        self.addCleanup(entorno.stop)
        cli = patch("integrations.management.commands.configurar_stripe.shutil.which", return_value="stripe.exe")
        cli.start()
        self.addCleanup(cli.stop)
        proceso = patch("integrations.management.commands.configurar_stripe.subprocess.run")
        self.run = proceso.start()
        self.addCleanup(proceso.stop)
        self.run.return_value = subprocess.CompletedProcess([], 0, "whsec_nuevo\n", "")
        self.salida = StringIO()

    def test_actualiza_solo_el_secreto_sin_mostrar_credenciales(self):
        call_command("configurar_stripe", stdout=self.salida)
        valores = dotenv_values(self.archivo)
        self.assertEqual(valores["STRIPE_WEBHOOK_SECRET"], "whsec_nuevo")
        self.assertEqual(valores["DB_NAME"], "global_exchange")
        self.assertIn("# Conservar configuración", self.archivo.read_text(encoding="utf-8"))
        self.assertNotIn("whsec_nuevo", self.salida.getvalue())
        self.assertNotIn("sk_test_privada", self.salida.getvalue())
        argumentos, opciones = self.run.call_args
        self.assertNotIn("sk_test_privada", str(argumentos))
        self.assertEqual(opciones["env"]["STRIPE_API_KEY"], "sk_test_privada")

    def test_error_cli_no_modifica_env_ni_expone_salida(self):
        self.run.return_value = subprocess.CompletedProcess([], 1, "sk_test_privada", "whsec_privado")
        with self.assertRaises(CommandError) as contexto:
            call_command("configurar_stripe", stdout=self.salida)
        self.assertNotIn("sk_test_privada", str(contexto.exception))
        self.assertNotIn("whsec_privado", str(contexto.exception))
        self.assertEqual(self.archivo.read_text(encoding="utf-8"), self.original)

    def test_timeout_no_modifica_env(self):
        self.run.side_effect = subprocess.TimeoutExpired("stripe", 30)
        with self.assertRaises(CommandError):
            call_command("configurar_stripe", stdout=self.salida)
        self.assertEqual(self.archivo.read_text(encoding="utf-8"), self.original)

    def test_rechaza_variable_del_sistema_que_oculta_env(self):
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_otroSistema"}):
            with self.assertRaisesMessage(CommandError, "tiene prioridad"):
                call_command("configurar_stripe", stdout=self.salida)
        self.assertEqual(self.archivo.read_text(encoding="utf-8"), self.original)

    def test_no_contacta_cli_con_clave_live(self):
        with override_settings(STRIPE_SECRET_KEY="sk_live_privada"):
            with self.assertRaises(CommandError):
                call_command("configurar_stripe", stdout=self.salida)
        self.run.assert_not_called()

    def test_listener_usa_la_ruta_real_y_el_puerto_elegido(self):
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, "whsec_nuevo\n", ""),
            subprocess.CompletedProcess([], 0),
        ]
        call_command("configurar_stripe", escuchar=True, puerto=8001, stdout=self.salida)
        comando = self.run.call_args.args[0]
        self.assertEqual(comando[-2:], ["--forward-to", "http://127.0.0.1:8001/transacciones/webhooks/stripe/"])
        self.assertIn("payment_intent.succeeded,payment_intent.payment_failed", comando)
