from decimal import Decimal

from django.test import SimpleTestCase

from core.templatetags.formato_numeros import formato_numero


class FormatoNumeroTests(SimpleTestCase):
    def test_formatea_miles_y_elimina_decimales_innecesarios(self):
        casos = (
            (1000, 2, "1.000"),
            (1000000, 2, "1.000.000"),
            (Decimal("1355.0000"), 4, "1.355"),
            (Decimal("1355.5000"), 4, "1.355,5"),
            (Decimal("1355.1250"), 4, "1.355,125"),
            (Decimal("1355.1234"), 4, "1.355,1234"),
            (Decimal("1000000.50"), 2, "1.000.000,5"),
        )

        for valor, decimales, esperado in casos:
            with self.subTest(valor=valor, decimales=decimales):
                self.assertEqual(formato_numero(valor, decimales), esperado)

    def test_respeta_la_cantidad_maxima_de_decimales(self):
        self.assertEqual(formato_numero(Decimal("1234.5678"), 2), "1.234,57")
        self.assertEqual(formato_numero(Decimal("1234.5678"), 0), "1.235")

    def test_conserva_valores_no_numericos_y_vacios(self):
        self.assertEqual(formato_numero(None, 2), "")
        self.assertEqual(formato_numero("", 2), "")
        self.assertEqual(formato_numero("sin dato", 2), "sin dato")
