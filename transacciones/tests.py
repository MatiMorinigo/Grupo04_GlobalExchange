from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import BigAutoField
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes.models import (
    CategoriaCliente,
    Cliente,
    ConfiguracionBeneficioCategoria,
    TipoCliente,
)
from cotizaciones.models import ConfiguracionComision, Moneda, TasaCambio
from destinos.models import (
    DestinoAcreditacion,
    TipoCuentaBancaria,
    TipoDestinoAcreditacion,
)
from usuarios.models import UsuarioCliente

from .models import (
    EstadoTransaccion,
    EtapaCancelacion,
    TipoOperacion,
    Transaccion,
)
from .services import (
    OperacionCambiariaError,
    calcular_compra,
    cancelar_transaccion,
    crear_transaccion_compra,
)


User = get_user_model()

MIDDLEWARE_SIN_OIDC = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


class TransaccionModelTests(TestCase):
    """Prueba la estructura y las reglas de integridad de las transacciones."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user(username="operador")
        cls.cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente de prueba",
            categoria=CategoriaCliente.VIP,
            tipo=TipoCliente.FISICA,
        )
        cls.pyg = Moneda.objects.get(codigo="PYG")
        cls.usd = Moneda.objects.get(codigo="USD")
        cls.eur = Moneda.objects.get(codigo="EUR")
        cls.tasa_usd = TasaCambio.objects.create(
            moneda_origen=cls.usd,
            moneda_destino=cls.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
            vigente=True,
        )
        cls.tasa_eur = TasaCambio.objects.create(
            moneda_origen=cls.eur,
            moneda_destino=cls.pyg,
            precio_compra=Decimal("8100.0000"),
            precio_venta=Decimal("8250.0000"),
            vigente=True,
        )

    def crear_transaccion(self, **cambios):
        """Construye una transaccion valida y permite sobrescribir campos."""

        datos = {
            "cliente": self.cliente,
            "creada_por": self.usuario,
            "tipo_operacion": TipoOperacion.COMPRA,
            "moneda": self.usd,
            "tasa_cambio": self.tasa_usd,
            "tasa_aplicada": self.tasa_usd.precio_venta,
            "fecha_vigencia_tasa": self.tasa_usd.fecha_vigencia,
            "monto_divisa": Decimal("100.00"),
            "subtotal_pyg": Decimal("735000.00"),
            "categoria_aplicada": CategoriaCliente.VIP,
            "beneficio_porcentaje": Decimal("5.00"),
            "limite_beneficio_pyg": Decimal("50000000.00"),
            "monto_beneficiado_pyg": Decimal("735000.00"),
            "beneficio_monto_pyg": Decimal("36750.00"),
            "comision_porcentaje": Decimal("1.00"),
            "comision_monto_pyg": Decimal("7350.00"),
            "total_pyg": Decimal("705600.00"),
        }
        datos.update(cambios)
        return Transaccion(**datos)

    def test_utiliza_big_auto_field_como_clave_primaria(self):
        campo = Transaccion._meta.get_field("id_transaccion")

        self.assertIsInstance(campo, BigAutoField)

    def test_transaccion_valida_inicia_pendiente(self):
        transaccion = self.crear_transaccion()

        transaccion.full_clean()
        transaccion.save()

        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)
        self.assertIsNotNone(transaccion.id_transaccion)

    def test_rechaza_pyg_como_moneda_extranjera(self):
        transaccion = self.crear_transaccion(moneda=self.pyg)

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("moneda", contexto.exception.message_dict)

    def test_rechaza_tasa_de_otra_moneda(self):
        transaccion = self.crear_transaccion(tasa_cambio=self.tasa_eur)

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("tasa_cambio", contexto.exception.message_dict)

    def test_compra_exige_precio_de_venta(self):
        transaccion = self.crear_transaccion(
            tasa_aplicada=self.tasa_usd.precio_compra,
        )

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("tasa_aplicada", contexto.exception.message_dict)

    def test_venta_utiliza_precio_de_compra(self):
        transaccion = self.crear_transaccion(
            tipo_operacion=TipoOperacion.VENTA,
            tasa_aplicada=self.tasa_usd.precio_compra,
        )

        transaccion.full_clean()

    def test_cancelada_exige_fecha_y_etapa(self):
        transaccion = self.crear_transaccion(estado=EstadoTransaccion.CANCELADA)

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("cancelada_en", contexto.exception.message_dict)
        self.assertIn("etapa_cancelacion", contexto.exception.message_dict)

    def test_cancelacion_previa_al_pago_es_valida(self):
        transaccion = self.crear_transaccion(
            estado=EstadoTransaccion.CANCELADA,
            cancelada_en=timezone.now(),
            etapa_cancelacion=EtapaCancelacion.PREVIA_PAGO,
            motivo_cancelacion="El cliente rechazo la nueva cotizacion.",
        )

        transaccion.full_clean()

    def test_completada_exige_fecha(self):
        transaccion = self.crear_transaccion(estado=EstadoTransaccion.COMPLETADA)

        with self.assertRaises(ValidationError) as contexto:
            transaccion.full_clean()

        self.assertIn("completada_en", contexto.exception.message_dict)

    def test_rechaza_monto_beneficiado_superior_al_limite(self):
        transaccion = self.crear_transaccion(
            limite_beneficio_pyg=Decimal("100000.00"),
            monto_beneficiado_pyg=Decimal("100001.00"),
        )

        with self.assertRaises(ValidationError):
            transaccion.full_clean()

    def test_tasa_y_condiciones_quedan_guardadas_como_snapshot(self):
        transaccion = self.crear_transaccion()
        transaccion.full_clean()
        transaccion.save()

        self.tasa_usd.precio_venta = Decimal("7400.0000")
        self.tasa_usd.save(update_fields=["precio_venta"])

        transaccion.refresh_from_db()
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7350.0000"))
        self.assertEqual(transaccion.beneficio_porcentaje, Decimal("5.00"))
        self.assertEqual(transaccion.comision_porcentaje, Decimal("1.00"))

    def test_aceptar_nueva_tasa_actualiza_la_misma_transaccion(self):
        transaccion = self.crear_transaccion()
        transaccion.full_clean()
        transaccion.save()
        identificador_original = transaccion.id_transaccion

        self.tasa_usd.vigente = False
        self.tasa_usd.save(update_fields=["vigente"])
        tasa_nueva = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7250.0000"),
            precio_venta=Decimal("7400.0000"),
            vigente=True,
        )

        transaccion.tasa_cambio = tasa_nueva
        transaccion.tasa_aplicada = tasa_nueva.precio_venta
        transaccion.fecha_vigencia_tasa = tasa_nueva.fecha_vigencia
        transaccion.subtotal_pyg = Decimal("740000.00")
        transaccion.monto_beneficiado_pyg = Decimal("740000.00")
        transaccion.beneficio_monto_pyg = Decimal("37000.00")
        transaccion.comision_monto_pyg = Decimal("7400.00")
        transaccion.total_pyg = Decimal("710400.00")
        transaccion.full_clean()
        transaccion.save()

        self.assertEqual(transaccion.id_transaccion, identificador_original)
        self.assertEqual(Transaccion.objects.count(), 1)
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7400.0000"))


def _configurar_beneficio(categoria, porcentaje, limite):
    """Ajusta el beneficio de una categoria para los calculos de prueba."""

    configuracion = ConfiguracionBeneficioCategoria.objects.get(categoria=categoria)
    configuracion.porcentaje_beneficio = Decimal(porcentaje)
    configuracion.limite_mensual_pyg = Decimal(limite)
    configuracion.save()
    return configuracion


def _configurar_comision(compra):
    """Ajusta la comision de compra vigente para los calculos de prueba."""

    configuracion = ConfiguracionComision.obtener()
    configuracion.porcentaje_compra = Decimal(compra)
    configuracion.save()
    return configuracion


class CalculoCompraTests(TestCase):
    """Prueba la formula de calculo de una compra de divisas."""

    @classmethod
    def setUpTestData(cls):
        cls.cliente_vip = Cliente.objects.create(
            ruc="80000101-1",
            nombre="Cliente VIP",
            categoria=CategoriaCliente.VIP,
            tipo=TipoCliente.FISICA,
        )
        cls.cliente_minorista = Cliente.objects.create(
            ruc="80000102-2",
            nombre="Cliente Minorista",
            categoria=CategoriaCliente.MINORISTA,
            tipo=TipoCliente.FISICA,
        )
        cls.pyg = Moneda.objects.get(codigo="PYG")
        cls.usd = Moneda.objects.get(codigo="USD")
        cls.tasa_usd = TasaCambio.objects.create(
            moneda_origen=cls.usd,
            moneda_destino=cls.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
            vigente=True,
        )

    def test_compra_usa_el_precio_de_venta(self):
        calculo = calcular_compra(self.cliente_minorista, "USD", Decimal("100.00"))

        self.assertEqual(calculo["tasa_aplicada"], Decimal("7350.0000"))
        self.assertEqual(calculo["subtotal_pyg"], Decimal("735000.00"))

    def test_compra_con_beneficio_y_comision_reproduce_los_importes_esperados(self):
        _configurar_beneficio(CategoriaCliente.VIP, "5.00", "50000000.00")
        _configurar_comision("1.00")

        calculo = calcular_compra(self.cliente_vip, "USD", Decimal("100.00"))

        self.assertEqual(calculo["subtotal_pyg"], Decimal("735000.00"))
        self.assertEqual(calculo["beneficio_monto_pyg"], Decimal("36750.00"))
        self.assertEqual(calculo["comision_monto_pyg"], Decimal("7350.00"))
        self.assertEqual(calculo["total_pyg"], Decimal("705600.00"))

    def test_beneficio_se_acota_al_limite_configurado(self):
        _configurar_beneficio(CategoriaCliente.VIP, "5.00", "100000.00")
        _configurar_comision("0.00")

        calculo = calcular_compra(self.cliente_vip, "USD", Decimal("100.00"))

        self.assertEqual(calculo["monto_beneficiado_pyg"], Decimal("100000.00"))
        self.assertEqual(calculo["beneficio_monto_pyg"], Decimal("5000.00"))
        self.assertEqual(calculo["total_pyg"], Decimal("730000.00"))

    def test_limite_en_cero_desactiva_el_beneficio(self):
        _configurar_beneficio(CategoriaCliente.VIP, "5.00", "0.00")
        _configurar_comision("0.00")

        calculo = calcular_compra(self.cliente_vip, "USD", Decimal("100.00"))

        self.assertEqual(calculo["beneficio_monto_pyg"], Decimal("0.00"))
        self.assertEqual(calculo["total_pyg"], Decimal("735000.00"))

    def test_comision_se_toma_de_la_configuracion_del_sistema(self):
        _configurar_beneficio(CategoriaCliente.MINORISTA, "0.00", "0.00")
        _configurar_comision("2.50")

        calculo = calcular_compra(self.cliente_minorista, "USD", Decimal("100.00"))

        self.assertEqual(calculo["comision_porcentaje"], Decimal("2.50"))
        self.assertEqual(calculo["comision_monto_pyg"], Decimal("18375.00"))
        self.assertEqual(calculo["total_pyg"], Decimal("753375.00"))

    def test_rechaza_monto_no_positivo(self):
        with self.assertRaises(OperacionCambiariaError):
            calcular_compra(self.cliente_minorista, "USD", Decimal("0.00"))

    def test_rechaza_guaranies_como_moneda_de_la_operacion(self):
        with self.assertRaises(OperacionCambiariaError):
            calcular_compra(self.cliente_minorista, "PYG", Decimal("100.00"))

    def test_rechaza_moneda_sin_cotizacion_vigente(self):
        with self.assertRaises(OperacionCambiariaError):
            calcular_compra(self.cliente_minorista, "BRL", Decimal("100.00"))

    def test_rechaza_moneda_deshabilitada(self):
        self.usd.activa = False
        self.usd.save(update_fields=["activa"])

        with self.assertRaises(OperacionCambiariaError):
            calcular_compra(self.cliente_minorista, "USD", Decimal("100.00"))


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class CompraDivisaWebTests(TestCase):
    """Prueba el flujo web de compra de divisas hasta el paso previo al pago."""

    def setUp(self):
        self.user = User.objects.create_user(username="compradora", password="testpass123")
        self.client.force_login(self.user)

        self.cliente = Cliente.objects.create(
            ruc="80000201-1",
            nombre="Cliente Comprador",
            categoria=CategoriaCliente.VIP,
            tipo=TipoCliente.FISICA,
        )
        self.otro_cliente = Cliente.objects.create(
            ruc="80000202-2",
            nombre="Cliente Ajeno",
            categoria=CategoriaCliente.VIP,
            tipo=TipoCliente.FISICA,
        )
        self.perfil = UsuarioCliente.objects.create(
            usuario=self.user, cliente_activo=self.cliente
        )

        self.pyg = Moneda.objects.get(codigo="PYG")
        self.usd = Moneda.objects.get(codigo="USD")
        self.eur = Moneda.objects.get(codigo="EUR")
        self.tasa_usd = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
            vigente=True,
        )

        _configurar_beneficio(CategoriaCliente.VIP, "5.00", "50000000.00")
        _configurar_comision("1.00")

    def _crear_destino(self, cliente=None, moneda=None, **cambios):
        datos = {
            "cliente": cliente or self.cliente,
            "tipo": TipoDestinoAcreditacion.CUENTA_BANCARIA,
            "titular": "Juan Perez",
            "documento_titular": "1234567",
            "moneda": moneda or self.usd,
            "banco": "Banco Continental",
            "tipo_cuenta": TipoCuentaBancaria.CAJA_AHORRO,
            "numero_cuenta": "1234567890",
            "activo": True,
        }
        datos.update(cambios)
        return DestinoAcreditacion.objects.create(**datos)

    def _publicar_nueva_tasa(self, precio_venta):
        self.tasa_usd.vigente = False
        self.tasa_usd.save(update_fields=["vigente"])
        return TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7250.0000"),
            precio_venta=Decimal(precio_venta),
            vigente=True,
        )

    def test_sin_cliente_activo_redirige_a_home(self):
        self.perfil.cliente_activo = None
        self.perfil.save(update_fields=["cliente_activo"])

        response = self.client.get(reverse("compra-web-create"), HTTP_HOST="127.0.0.1")

        self.assertRedirects(response, reverse("home"))

    def test_compra_crea_la_transaccion_en_estado_pendiente(self):
        response = self.client.post(
            reverse("compra-web-create"),
            {"moneda": "USD", "monto_divisa": "100.00"},
            HTTP_HOST="127.0.0.1",
        )

        transaccion = Transaccion.objects.get()
        self.assertRedirects(
            response,
            reverse("transaccion-web-detail", args=[transaccion.id_transaccion]),
        )
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)
        self.assertEqual(transaccion.tipo_operacion, TipoOperacion.COMPRA)
        self.assertEqual(transaccion.cliente, self.cliente)
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7350.0000"))
        self.assertEqual(transaccion.total_pyg, Decimal("705600.00"))

    def test_compra_rechaza_destino_en_otra_moneda(self):
        destino_eur = self._crear_destino(moneda=self.eur, numero_cuenta="5555555555")

        response = self.client.post(
            reverse("compra-web-create"),
            {
                "moneda": "USD",
                "monto_divisa": "100.00",
                "destino_acreditacion": destino_eur.id_destino,
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaccion.objects.exists())

    def test_compra_rechaza_destino_de_otro_cliente(self):
        ajeno = self._crear_destino(cliente=self.otro_cliente, numero_cuenta="9999999999")

        response = self.client.post(
            reverse("compra-web-create"),
            {
                "moneda": "USD",
                "monto_divisa": "100.00",
                "destino_acreditacion": ajeno.id_destino,
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaccion.objects.exists())

    def test_compra_acepta_destino_propio_en_la_misma_moneda(self):
        destino = self._crear_destino()

        self.client.post(
            reverse("compra-web-create"),
            {
                "moneda": "USD",
                "monto_divisa": "100.00",
                "destino_acreditacion": destino.id_destino,
            },
            HTTP_HOST="127.0.0.1",
        )

        transaccion = Transaccion.objects.get()
        self.assertEqual(transaccion.destino_acreditacion, destino)

    def test_revalidar_sin_cambios_permite_continuar(self):
        transaccion = crear_transaccion_compra(
            self.cliente, self.user, "USD", Decimal("100.00")
        )

        response = self.client.post(
            reverse("transaccion-web-revalidar", args=[transaccion.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(
            response,
            reverse("transaccion-web-detail", args=[transaccion.id_transaccion]),
        )
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7350.0000"))

    def test_revalidar_con_cotizacion_nueva_muestra_los_importes_recalculados(self):
        transaccion = crear_transaccion_compra(
            self.cliente, self.user, "USD", Decimal("100.00")
        )
        self._publicar_nueva_tasa("7400.0000")

        response = self.client.post(
            reverse("transaccion-web-revalidar", args=[transaccion.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transacciones/transaccion_recotizacion.html")
        self.assertEqual(response.context["recalculo"]["total_pyg"], Decimal("710400.00"))

        # La recotizacion es solo una previsualizacion: no persiste nada.
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7350.0000"))

    def test_aceptar_nueva_tasa_actualiza_la_misma_transaccion(self):
        transaccion = crear_transaccion_compra(
            self.cliente, self.user, "USD", Decimal("100.00")
        )
        identificador = transaccion.id_transaccion
        tasa_nueva = self._publicar_nueva_tasa("7400.0000")

        response = self.client.post(
            reverse("transaccion-web-aceptar-tasa", args=[identificador]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(
            response, reverse("transaccion-web-detail", args=[identificador])
        )
        transaccion.refresh_from_db()
        self.assertEqual(Transaccion.objects.count(), 1)
        self.assertEqual(transaccion.id_transaccion, identificador)
        self.assertEqual(transaccion.tasa_cambio_id, tasa_nueva.id_tasa)
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7400.0000"))
        self.assertEqual(transaccion.subtotal_pyg, Decimal("740000.00"))
        self.assertEqual(transaccion.beneficio_monto_pyg, Decimal("37000.00"))
        self.assertEqual(transaccion.comision_monto_pyg, Decimal("7400.00"))
        self.assertEqual(transaccion.total_pyg, Decimal("710400.00"))

    def test_confirmacion_de_cancelacion_se_renderiza(self):
        transaccion = crear_transaccion_compra(
            self.cliente, self.user, "USD", Decimal("100.00")
        )

        response = self.client.get(
            reverse("transaccion-web-cancelar", args=[transaccion.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transacciones/transaccion_confirm_cancel.html")
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)

    def test_cancelar_deja_la_operacion_cancelada_y_previa_al_pago(self):
        transaccion = crear_transaccion_compra(
            self.cliente, self.user, "USD", Decimal("100.00")
        )

        response = self.client.post(
            reverse("transaccion-web-cancelar", args=[transaccion.id_transaccion]),
            {"motivo_cancelacion": "El cliente rechazo la nueva cotizacion."},
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(
            response,
            reverse("transaccion-web-detail", args=[transaccion.id_transaccion]),
        )
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.CANCELADA)
        self.assertNotEqual(transaccion.estado, EstadoTransaccion.ANULADA)
        self.assertEqual(transaccion.etapa_cancelacion, EtapaCancelacion.PREVIA_PAGO)
        self.assertIsNotNone(transaccion.cancelada_en)
        self.assertIsNone(transaccion.completada_en)

    def test_cancelar_conserva_los_importes_de_la_operacion(self):
        transaccion = crear_transaccion_compra(
            self.cliente, self.user, "USD", Decimal("100.00")
        )

        self.client.post(
            reverse("transaccion-web-cancelar", args=[transaccion.id_transaccion]),
            {"motivo_cancelacion": ""},
            HTTP_HOST="127.0.0.1",
        )

        transaccion.refresh_from_db()
        self.assertEqual(transaccion.total_pyg, Decimal("705600.00"))
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7350.0000"))

    def test_no_se_puede_cancelar_dos_veces(self):
        transaccion = crear_transaccion_compra(
            self.cliente, self.user, "USD", Decimal("100.00")
        )
        cancelar_transaccion(transaccion, motivo="Primera cancelacion.")

        self.client.post(
            reverse("transaccion-web-cancelar", args=[transaccion.id_transaccion]),
            {"motivo_cancelacion": "Segunda cancelacion."},
            HTTP_HOST="127.0.0.1",
        )

        transaccion.refresh_from_db()
        self.assertEqual(transaccion.motivo_cancelacion, "Primera cancelacion.")

    def test_no_puede_ver_la_operacion_de_otro_cliente(self):
        ajena = crear_transaccion_compra(
            self.otro_cliente, self.user, "USD", Decimal("100.00")
        )

        response = self.client.get(
            reverse("transaccion-web-detail", args=[ajena.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)

    def test_no_puede_cancelar_la_operacion_de_otro_cliente(self):
        ajena = crear_transaccion_compra(
            self.otro_cliente, self.user, "USD", Decimal("100.00")
        )

        response = self.client.post(
            reverse("transaccion-web-cancelar", args=[ajena.id_transaccion]),
            {"motivo_cancelacion": "Intento indebido."},
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)
        ajena.refresh_from_db()
        self.assertEqual(ajena.estado, EstadoTransaccion.PENDIENTE)
