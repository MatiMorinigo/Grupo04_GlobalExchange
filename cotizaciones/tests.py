import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Moneda, TasaCambio


class CotizacionWebViewTests(TestCase):
    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )

    def test_cotizaciones_list_renders_empty_state(self):
        response = self.client.get(reverse("cotizacion-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Cotizaciones", content)
        self.assertIn("No hay tasas vigentes para mostrar", content)

    def test_cotizaciones_list_renders_current_rates(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(reverse("cotizacion-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("USD/PYG", content)
        self.assertIn("Gs 7200", content)
        self.assertIn("Gs 7350", content)
        self.assertNotIn("7200,0000", content)
        self.assertNotIn("7350,0000", content)
        self.assertNotIn(",0000", content)

    def test_cotizaciones_list_shows_variation(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7000.0000"),
            precio_venta=Decimal("7100.0000"),
            vigente=False,
            fecha_vigencia=timezone.now() - timezone.timedelta(days=1),
        )
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(reverse("cotizacion-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Subió", content)


class CotizacionApiTests(TestCase):
    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )

    def test_api_returns_current_rates(self):
        tasa = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(reverse("cotizacion-tasa-list"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id_tasa"], tasa.id_tasa)
        self.assertEqual(response.json()[0]["moneda_origen"], "USD")

    def test_api_pair_endpoint_returns_current_rate(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.get(
            reverse(
                "cotizacion-tasa-par-vigente",
                kwargs={"moneda_origen": "USD", "moneda_destino": "PYG"},
            ),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["moneda_destino"], "PYG")

    def test_api_filters_by_origin_currency(self):
        brl, _ = Moneda.objects.get_or_create(
            codigo="BRL",
            defaults={"nombre": "Real brasileño", "simbolo": "R$"},
        )
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )
        TasaCambio.objects.create(
            moneda_origen=brl,
            moneda_destino=self.pyg,
            precio_compra=Decimal("1300.0000"),
            precio_venta=Decimal("1450.0000"),
        )

        response = self.client.get(
            reverse("cotizacion-tasa-list"),
            {"moneda_origen": "BRL"},
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["moneda_origen"], "BRL")


class SimulacionConversionWebTests(TestCase):
    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )
        self.eur, _ = Moneda.objects.get_or_create(
            codigo="EUR",
            defaults={"nombre": "Euro", "simbolo": "€"},
        )

    def test_simulador_renders_form(self):
        response = self.client.get(reverse("cotizacion-simulador"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Simulador de conversión", content)
        self.assertIn("Moneda de origen", content)
        self.assertIn("Moneda de destino", content)
        self.assertIn("Seleccione una moneda", content)
        self.assertNotIn("Select an option", content)

    def test_simulador_calculates_foreign_currency_to_pyg(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.post(
            reverse("cotizacion-simulador"),
            {
                "moneda_origen": "USD",
                "moneda_destino": "PYG",
                "monto": "100.00",
            },
            HTTP_HOST="127.0.0.1",
        )
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Total estimado a recibir", content)
        self.assertIn("PYG", content)
        self.assertIn("720000", content)
        self.assertIn("Compra", content)

    def test_simulador_shows_error_without_current_rate(self):
        response = self.client.post(
            reverse("cotizacion-simulador"),
            {
                "moneda_origen": "EUR",
                "moneda_destino": "PYG",
                "monto": "100.00",
            },
            HTTP_HOST="127.0.0.1",
        )
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("No existe una tasa vigente", content)


class SimulacionConversionApiTests(TestCase):
    def setUp(self):
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní paraguayo", "simbolo": "Gs"},
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar estadounidense", "simbolo": "US$"},
        )
        self.eur, _ = Moneda.objects.get_or_create(
            codigo="EUR",
            defaults={"nombre": "Euro", "simbolo": "€"},
        )

    def test_api_simulates_foreign_currency_to_pyg(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.post(
            reverse("cotizacion-simulacion-create"),
            data=json.dumps(
                {
                    "moneda_origen": "USD",
                    "moneda_destino": "PYG",
                    "monto": "100.00",
                }
            ),
            content_type="application/json",
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tipo_tasa"], "compra")
        self.assertEqual(response.json()["total_final"], 720000.0)

    def test_api_simulates_pyg_to_foreign_currency(self):
        TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
        )

        response = self.client.post(
            reverse("cotizacion-simulacion-create"),
            data=json.dumps(
                {
                    "moneda_origen": "PYG",
                    "moneda_destino": "USD",
                    "monto": "100000.00",
                }
            ),
            content_type="application/json",
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tipo_tasa"], "venta")
        self.assertEqual(response.json()["total_final"], 13.61)

    def test_api_rejects_conversion_without_pyg(self):
        response = self.client.post(
            reverse("cotizacion-simulacion-create"),
            data=json.dumps(
                {
                    "moneda_origen": "USD",
                    "moneda_destino": "EUR",
                    "monto": "100.00",
                }
            ),
            content_type="application/json",
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("guaraníes", str(response.json()))
