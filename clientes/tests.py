from django.test import TestCase
from django.urls import reverse

from .models import Cliente


class ClienteWebViewTests(TestCase):
    def test_clientes_list_renders(self):
        Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Demo",
            categoria="MINORISTA",
            tipo="FISICA",
        )

        response = self.client.get(reverse("cliente-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Listado de clientes", content)
        self.assertIn("Cliente Demo", content)
        self.assertIn(reverse("cliente-web-create"), content)

    def test_clientes_list_shows_empty_state(self):
        response = self.client.get(reverse("cliente-web-list"), HTTP_HOST="127.0.0.1")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("No hay clientes para mostrar", content)

    def test_clientes_create_inserts_record(self):
        response = self.client.post(
            reverse("cliente-web-create"),
            {
                "ruc": "80012345-6",
                "nombre": "Cliente Demo",
                "categoria": "MINORISTA",
                "tipo": "FISICA",
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("cliente-web-list"))
        self.assertTrue(Cliente.objects.filter(ruc="80012345-6").exists())

    def test_clientes_detail_renders_registered_data(self):
        cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Demo",
            categoria="CORPORATIVO",
            tipo="JURIDICA",
        )

        response = self.client.get(
            reverse("cliente-web-detail", kwargs={"id_cliente": cliente.id_cliente}),
            HTTP_HOST="127.0.0.1",
        )
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Detalle de cliente", content)
        self.assertIn("Cliente Demo", content)
        self.assertIn("Corporativo", content)

    def test_clientes_update_changes_record(self):
        cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Demo",
            categoria="MINORISTA",
            tipo="FISICA",
        )

        response = self.client.post(
            reverse("cliente-web-update", kwargs={"id_cliente": cliente.id_cliente}),
            {
                "ruc": "80012345-6",
                "nombre": "Cliente Actualizado",
                "categoria": "VIP",
                "tipo": "FISICA",
            },
            HTTP_HOST="127.0.0.1",
        )
        cliente.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("cliente-web-detail", kwargs={"id_cliente": cliente.id_cliente}),
        )
        self.assertEqual(cliente.nombre, "Cliente Actualizado")
        self.assertEqual(cliente.categoria, "VIP")

    def test_clientes_deactivate_marks_record_inactive(self):
        cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Demo",
            categoria="MINORISTA",
            tipo="FISICA",
        )

        response = self.client.post(
            reverse("cliente-web-deactivate", kwargs={"id_cliente": cliente.id_cliente}),
            HTTP_HOST="127.0.0.1",
        )
        cliente.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("cliente-web-detail", kwargs={"id_cliente": cliente.id_cliente}),
        )
        self.assertFalse(cliente.activo)
