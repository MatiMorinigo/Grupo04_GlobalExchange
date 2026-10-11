import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import stripe

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.db.models import BigAutoField
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .forms import VentaDivisaForm

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
from integrations.proveedores_pago import ResultadoPago, SimuladorBilleteraProveedor
from integrations.proveedores_pago.stripe_proveedor import a_unidad_minima
from pagos.models import MetodoPago, TipoMetodoPago
from usuarios.models import UsuarioCliente

from .models import (
    EstadoPago,
    EstadoTransaccion,
    EtapaCancelacion,
    Pago,
    ProveedorPago,
    TipoOperacion,
    Transaccion,
)
from .services import (
    OperacionCambiariaError,
    PagoNoIniciableError,
    ResultadoProcesamiento,
    calcular_compra,
    crear_transaccion_compra,
    calcular_venta,
    iniciar_pago,
    procesar_resultado_pago,
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

    def test_destino_acreditacion_en_venta_acepta_pyg(self):
        destino_pyg = DestinoAcreditacion.objects.create(
            cliente=self.cliente,
            moneda=self.pyg,
            tipo=TipoDestinoAcreditacion.CUENTA_BANCARIA,
            banco="Banco PYG",
            tipo_cuenta=TipoCuentaBancaria.CAJA_AHORRO,
            numero_cuenta="111111",
            titular="Titular Test",
            documento_titular="1234567",
            alias="Cuenta PYG",
        )
        transaccion = self.crear_transaccion(
            tipo_operacion=TipoOperacion.VENTA,
            moneda=self.usd,
            tasa_aplicada=self.tasa_usd.precio_compra,
            destino_acreditacion=destino_pyg,
        )
        transaccion.full_clean()  # No debe lanzar ValidationError

    def test_destino_acreditacion_en_venta_rechaza_otra_moneda(self):
        destino_usd = DestinoAcreditacion.objects.create(
            cliente=self.cliente,
            moneda=self.usd,
            tipo=TipoDestinoAcreditacion.CUENTA_BANCARIA,
            banco="Banco USD",
            tipo_cuenta=TipoCuentaBancaria.CAJA_AHORRO,
            numero_cuenta="222222",
            titular="Titular Test",
            documento_titular="1234567",
            alias="Cuenta USD",
        )
        transaccion = self.crear_transaccion(
            tipo_operacion=TipoOperacion.VENTA,
            moneda=self.usd,
            tasa_aplicada=self.tasa_usd.precio_compra,
            destino_acreditacion=destino_usd,
        )
        with self.assertRaises(ValidationError) as ctx:
            transaccion.full_clean()
        self.assertIn("destino_acreditacion", ctx.exception.message_dict)



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
            
    def test_compra_aplica_beneficio_vip_a_cliente_con_vip_temporal(self):
        _configurar_beneficio(
            CategoriaCliente.VIP,
            "5.00",
            "50000000.00",
        )
        _configurar_comision("0.00")

        self.cliente_minorista.vip_vigente_hasta = (
            timezone.localdate() + timedelta(days=30)
        )
        self.cliente_minorista.save(
            update_fields=["vip_vigente_hasta"]
        )

        calculo = calcular_compra(
            self.cliente_minorista,
            "USD",
            Decimal("100.00"),
        )

        self.assertEqual(
            self.cliente_minorista.categoria,
            CategoriaCliente.MINORISTA,
        )
        self.assertEqual(
            calculo["categoria_aplicada"],
            CategoriaCliente.VIP,
        )
        self.assertEqual(
            calculo["beneficio_monto_pyg"],
            Decimal("36750.00"),
        )
        self.assertEqual(
            calculo["total_pyg"],
            Decimal("698250.00"),
        )

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

        self.metodo_pago = self._crear_metodo_pago()

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

    def _crear_metodo_pago(self, cliente=None, **cambios):
        datos = {
            "cliente": cliente or self.cliente,
            "tipo": TipoMetodoPago.TARJETA_CREDITO,
            "titular": "Juan Perez",
            "ultimos_cuatro_digitos": "1486",
            "fecha_vencimiento": "12/30",
            "activo": True,
        }
        datos.update(cambios)
        return MetodoPago.objects.create(**datos)

    def _datos(self, **cambios):
        datos = {
            "moneda": "USD",
            "monto_divisa": "100.00",
            "metodo_pago": self.metodo_pago.id_metodo_pago,
        }
        datos.update(cambios)
        return datos

    def test_sin_cliente_activo_redirige_a_home(self):
        self.perfil.cliente_activo = None
        self.perfil.save(update_fields=["cliente_activo"])

        response = self.client.get(reverse("compra-web-create"), HTTP_HOST="127.0.0.1")

        self.assertRedirects(response, reverse("home"))

    def test_primer_envio_muestra_el_resumen_sin_persistir(self):
        response = self.client.post(
            reverse("compra-web-create"), self._datos(), HTTP_HOST="127.0.0.1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["modo_confirmacion"])
        self.assertFalse(response.context["advertencia_cotizacion"])
        self.assertEqual(Transaccion.objects.count(), 0)

    def test_resumen_expone_el_desglose_calculado(self):
        response = self.client.post(
            reverse("compra-web-create"), self._datos(), HTTP_HOST="127.0.0.1"
        )

        resumen = response.context["resumen"]
        self.assertEqual(resumen["subtotal_pyg"], Decimal("735000.00"))
        self.assertEqual(resumen["beneficio_monto_pyg"], Decimal("36750.00"))
        self.assertEqual(resumen["comision_monto_pyg"], Decimal("7350.00"))
        self.assertEqual(resumen["total_pyg"], Decimal("705600.00"))

    def test_confirmar_registra_la_transaccion_pendiente(self):
        response = self.client.post(
            reverse("compra-web-create"),
            self._datos(confirmado="True", id_tasa_vista=self.tasa_usd.id_tasa),
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

    def test_confirmar_guarda_el_metodo_de_pago_elegido(self):
        self.client.post(
            reverse("compra-web-create"),
            self._datos(confirmado="True", id_tasa_vista=self.tasa_usd.id_tasa),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(Transaccion.objects.get().metodo_pago, self.metodo_pago)

    def test_confirmar_con_cotizacion_cambiada_advierte_y_no_persiste(self):
        self._publicar_nueva_tasa("7400.0000")

        response = self.client.post(
            reverse("compra-web-create"),
            self._datos(confirmado="True", id_tasa_vista=self.tasa_usd.id_tasa),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["modo_confirmacion"])
        self.assertTrue(response.context["advertencia_cotizacion"])
        self.assertEqual(response.context["resumen"]["total_pyg"], Decimal("710400.00"))
        self.assertEqual(Transaccion.objects.count(), 0)

    def test_confirmar_de_nuevo_tras_la_advertencia_registra_con_la_tasa_nueva(self):
        tasa_nueva = self._publicar_nueva_tasa("7400.0000")

        self.client.post(
            reverse("compra-web-create"),
            self._datos(confirmado="True", id_tasa_vista=tasa_nueva.id_tasa),
            HTTP_HOST="127.0.0.1",
        )

        transaccion = Transaccion.objects.get()
        self.assertEqual(transaccion.tasa_cambio_id, tasa_nueva.id_tasa)
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7400.0000"))
        self.assertEqual(transaccion.total_pyg, Decimal("710400.00"))

    def test_metodo_de_pago_es_obligatorio(self):
        datos = self._datos()
        datos.pop("metodo_pago")

        response = self.client.post(
            reverse("compra-web-create"), datos, HTTP_HOST="127.0.0.1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["modo_confirmacion"])
        self.assertIn("metodo_pago", response.context["form"].errors)
        self.assertEqual(Transaccion.objects.count(), 0)

    def test_rechaza_metodo_de_pago_de_otro_cliente(self):
        ajeno = self._crear_metodo_pago(cliente=self.otro_cliente)

        response = self.client.post(
            reverse("compra-web-create"),
            self._datos(metodo_pago=ajeno.id_metodo_pago),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("metodo_pago", response.context["form"].errors)
        self.assertEqual(Transaccion.objects.count(), 0)

    def test_rechaza_metodo_de_pago_inactivo(self):
        inactivo = self._crear_metodo_pago(activo=False, ultimos_cuatro_digitos="4444")

        response = self.client.post(
            reverse("compra-web-create"),
            self._datos(metodo_pago=inactivo.id_metodo_pago),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("metodo_pago", response.context["form"].errors)

    def test_rechaza_destino_en_otra_moneda(self):
        destino_eur = self._crear_destino(moneda=self.eur, numero_cuenta="5555555555")

        response = self.client.post(
            reverse("compra-web-create"),
            self._datos(destino_acreditacion=destino_eur.id_destino),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("destino_acreditacion", response.context["form"].errors)
        self.assertEqual(Transaccion.objects.count(), 0)

    def test_rechaza_destino_de_otro_cliente(self):
        ajeno = self._crear_destino(cliente=self.otro_cliente, numero_cuenta="9999999999")

        response = self.client.post(
            reverse("compra-web-create"),
            self._datos(destino_acreditacion=ajeno.id_destino),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("destino_acreditacion", response.context["form"].errors)

    def test_acepta_destino_propio_en_la_misma_moneda(self):
        destino = self._crear_destino()

        self.client.post(
            reverse("compra-web-create"),
            self._datos(
                confirmado="True",
                id_tasa_vista=self.tasa_usd.id_tasa,
                destino_acreditacion=destino.id_destino,
            ),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(Transaccion.objects.get().destino_acreditacion, destino)

    def test_detalle_indica_que_la_operacion_esta_pendiente(self):
        transaccion = crear_transaccion_compra(
            self.cliente,
            self.user,
            "USD",
            Decimal("100.00"),
            metodo_pago=self.metodo_pago,
        )

        response = self.client.get(
            reverse("transaccion-web-detail", args=[transaccion.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PENDIENTE")
        self.assertContains(
            response,
            reverse("transaccion-web-comprobante", args=[transaccion.id_transaccion]),
        )

    def test_comprobante_se_renderiza_para_la_operacion_propia(self):
        transaccion = crear_transaccion_compra(
            self.cliente,
            self.user,
            "USD",
            Decimal("100.00"),
            metodo_pago=self.metodo_pago,
        )

        response = self.client.get(
            reverse("transaccion-web-comprobante", args=[transaccion.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transacciones/comprobante.html")
        self.assertContains(response, "PENDIENTE")

    def test_no_puede_ver_la_operacion_de_otro_cliente(self):
        ajena = crear_transaccion_compra(
            self.otro_cliente, self.user, "USD", Decimal("100.00")
        )

        response = self.client.get(
            reverse("transaccion-web-detail", args=[ajena.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)

    def test_no_puede_ver_el_comprobante_de_otro_cliente(self):
        ajena = crear_transaccion_compra(
            self.otro_cliente, self.user, "USD", Decimal("100.00")
        )

        response = self.client.get(
            reverse("transaccion-web-comprobante", args=[ajena.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)

    def test_formulario_muestra_el_cliente_con_el_que_se_opera(self):
        response = self.client.get(reverse("compra-web-create"), HTTP_HOST="127.0.0.1")

        self.assertContains(response, "Operando con el cliente")
        self.assertContains(response, "Cliente Comprador")
        self.assertContains(response, "80000201-1")
        self.assertNotContains(response, "Cliente Ajeno")

    def test_formulario_orienta_sobre_como_cambiar_de_cliente(self):
        response = self.client.get(reverse("compra-web-create"), HTTP_HOST="127.0.0.1")

        self.assertContains(response, "¿Querés operar con otro cliente?")
        self.assertContains(response, f'<a href="{reverse("home")}">menú principal</a>')

    def test_formulario_con_errores_sigue_mostrando_el_cliente(self):
        datos = self._datos()
        datos.pop("monto_divisa")

        response = self.client.post(
            reverse("compra-web-create"), datos, HTTP_HOST="127.0.0.1"
        )

        self.assertFalse(response.context["modo_confirmacion"])
        self.assertContains(response, "Operando con el cliente")
        self.assertContains(response, "Cliente Comprador")

    def test_resumen_muestra_el_cliente_y_la_orientacion(self):
        response = self.client.post(
            reverse("compra-web-create"), self._datos(), HTTP_HOST="127.0.0.1"
        )

        self.assertTrue(response.context["modo_confirmacion"])
        self.assertContains(response, "Operando con el cliente")
        self.assertContains(response, "Cliente Comprador")
        self.assertContains(response, "80000201-1")
        self.assertContains(response, "¿Querés operar con otro cliente?")

    def test_resumen_con_advertencia_de_cotizacion_conserva_el_cliente(self):
        self._publicar_nueva_tasa("7400.0000")

        response = self.client.post(
            reverse("compra-web-create"),
            self._datos(confirmado="True", id_tasa_vista=self.tasa_usd.id_tasa),
            HTTP_HOST="127.0.0.1",
        )

        self.assertTrue(response.context["advertencia_cotizacion"])
        self.assertContains(response, "Cliente Comprador")

    def test_cada_usuario_ve_el_cliente_que_tiene_activo(self):
        self.perfil.cliente_activo = self.otro_cliente
        self.perfil.save(update_fields=["cliente_activo"])

        response = self.client.get(reverse("compra-web-create"), HTTP_HOST="127.0.0.1")

        self.assertContains(response, "Cliente Ajeno")
        self.assertContains(response, "80000202-2")
        self.assertNotContains(response, "Cliente Comprador")

    def test_compra_registrada_muestra_el_cliente_de_la_operacion_sin_orientacion(self):
        transaccion = crear_transaccion_compra(
            self.cliente,
            self.user,
            "USD",
            Decimal("100.00"),
            metodo_pago=self.metodo_pago,
        )

        response = self.client.get(
            reverse("transaccion-web-detail", args=[transaccion.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, "Cliente de la operación")
        self.assertContains(response, "Cliente Comprador")
        self.assertNotContains(response, "Operando con el cliente")
        self.assertNotContains(response, "¿Querés operar con otro cliente?")

    def test_cambiar_de_cliente_a_mitad_del_flujo_no_registra_la_compra(self):
        # El método de pago elegido en el resumen pertenece al cliente original.
        self.perfil.cliente_activo = self.otro_cliente
        self.perfil.save(update_fields=["cliente_activo"])

        response = self.client.post(
            reverse("compra-web-create"),
            self._datos(confirmado="True", id_tasa_vista=self.tasa_usd.id_tasa),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("metodo_pago", response.context["form"].errors)
        self.assertEqual(Transaccion.objects.count(), 0)


class VentaDivisaFormTests(TestCase):
    """Prueba las validaciones y el comportamiento de VentaDivisaForm."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user(username="operador_venta")
        cls.cliente = Cliente.objects.create(
            ruc="80012345-6",
            nombre="Cliente Vendedor",
            categoria=CategoriaCliente.VIP,
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
        cls.metodo_pago = MetodoPago.objects.create(
            cliente=cls.cliente,
            tipo=TipoMetodoPago.TARJETA_CREDITO,
            titular="Cliente Vendedor",
            ultimos_cuatro_digitos="1234",
            fecha_vencimiento="12/30",
            activo=True,
        )

    def test_formulario_valido_con_datos_correctos(self):
        form = VentaDivisaForm(
            data={
                "moneda": "USD",
                "monto_divisa": "100.00",
                "metodo_pago": self.metodo_pago.pk,
            },
            cliente=self.cliente,
        )
        self.assertTrue(form.is_valid())

    def test_formulario_requiere_metodo_pago(self):
        form = VentaDivisaForm(
            data={
                "moneda": "USD",
                "monto_divisa": "100.00",
            },
            cliente=self.cliente,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("metodo_pago", form.errors)


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC)
class HistorialTransaccionesWebTests(TestCase):
    """Prueba los criterios de aceptación del historial de transacciones."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="usuario_historial",
            password="testpass123",
        )
        self.client.force_login(self.user)
        self.cliente_uno = Cliente.objects.create(
            ruc="80000301-1",
            nombre="Cliente Uno",
            categoria=CategoriaCliente.VIP,
            tipo=TipoCliente.FISICA,
        )
        self.cliente_dos = Cliente.objects.create(
            ruc="80000302-2",
            nombre="Cliente Dos",
            categoria=CategoriaCliente.MINORISTA,
            tipo=TipoCliente.FISICA,
        )
        self.perfil = UsuarioCliente.objects.create(
            usuario=self.user,
            cliente_activo=self.cliente_uno,
        )
        self.pyg = Moneda.objects.get(codigo="PYG")
        self.usd = Moneda.objects.get(codigo="USD")
        self.tasa = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
            vigente=True,
        )
        self.compra = self._crear_transaccion(self.cliente_uno)
        self.venta = self._crear_transaccion(
            self.cliente_uno,
            tipo=TipoOperacion.VENTA,
            estado=EstadoTransaccion.COMPLETADA,
        )
        self.cancelada = self._crear_transaccion(
            self.cliente_uno,
            estado=EstadoTransaccion.CANCELADA,
        )
        self.ajena = self._crear_transaccion(self.cliente_dos)

    def _crear_transaccion(
        self,
        cliente,
        tipo=TipoOperacion.COMPRA,
        estado=EstadoTransaccion.PENDIENTE,
    ):
        """Crea datos validos sin depender de los formularios de compra o venta."""

        es_compra = tipo == TipoOperacion.COMPRA
        subtotal = Decimal("735000.00") if es_compra else Decimal("720000.00")
        comision = Decimal("7350.00") if es_compra else Decimal("7200.00")
        total = subtotal + comision if es_compra else subtotal - comision
        ahora = timezone.now()
        transaccion = Transaccion(
            cliente=cliente,
            creada_por=self.user,
            tipo_operacion=tipo,
            moneda=self.usd,
            tasa_cambio=self.tasa,
            tasa_aplicada=(
                self.tasa.precio_venta if es_compra else self.tasa.precio_compra
            ),
            fecha_vigencia_tasa=self.tasa.fecha_vigencia,
            monto_divisa=Decimal("100.00"),
            subtotal_pyg=subtotal,
            categoria_aplicada=cliente.categoria,
            beneficio_porcentaje=Decimal("0.00"),
            limite_beneficio_pyg=Decimal("0.00"),
            monto_beneficiado_pyg=Decimal("0.00"),
            beneficio_monto_pyg=Decimal("0.00"),
            comision_porcentaje=Decimal("1.00"),
            comision_monto_pyg=comision,
            total_pyg=total,
            estado=estado,
            cancelada_en=(
                ahora if estado == EstadoTransaccion.CANCELADA else None
            ),
            etapa_cancelacion=(
                EtapaCancelacion.PREVIA_PAGO
                if estado == EstadoTransaccion.CANCELADA
                else None
            ),
            motivo_cancelacion=(
                "El cliente canceló antes del pago."
                if estado == EstadoTransaccion.CANCELADA
                else ""
            ),
            completada_en=(
                ahora
                if estado in (
                    EstadoTransaccion.COMPLETADA,
                    EstadoTransaccion.ANULADA,
                )
                else None
            ),
        )
        transaccion.full_clean()
        transaccion.save()
        return transaccion

    def _ids_visibles(self, response):
        """Devuelve los identificadores incluidos en la pagina del historial."""

        return {
            transaccion.id_transaccion
            for transaccion in response.context["transacciones"]
        }

    def _roles(self, *roles_permitidos):
        """Simula los roles de Keycloak necesarios para cada prueba."""

        return patch(
            "transacciones.views.tiene_rol",
            side_effect=lambda request, rol: rol in roles_permitidos,
        )

    def test_usuario_ve_solo_transacciones_del_cliente_activo(self):
        # Un cliente no debe ver operaciones pertenecientes a otro cliente.
        response = self.client.get(
            reverse("transaccion-web-historial"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertSetEqual(
            self._ids_visibles(response),
            {self.compra.pk, self.venta.pk, self.cancelada.pk},
        )

    def test_cambiar_cliente_activo_cambia_el_historial(self):
        # El historial debe seguir al cliente que el usuario tenga seleccionado.
        self.perfil.cliente_activo = self.cliente_dos
        self.perfil.save(update_fields=["cliente_activo"])

        response = self.client.get(
            reverse("transaccion-web-historial"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertSetEqual(self._ids_visibles(response), {self.ajena.pk})

    def test_usuario_no_puede_forzar_otro_cliente_con_el_filtro(self):
        # Cambiar la URL no debe saltar la restricción del cliente activo.
        response = self.client.get(
            reverse("transaccion-web-historial"),
            {"cliente": self.cliente_dos.pk},
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotIn(self.ajena.pk, self._ids_visibles(response))
        self.assertIn(self.compra.pk, self._ids_visibles(response))

    def test_usuario_sin_cliente_activo_no_accede_al_historial(self):
        # Un usuario comun necesita seleccionar un cliente activo.
        self.perfil.cliente_activo = None
        self.perfil.save(update_fields=["cliente_activo"])

        response = self.client.get(
            reverse("transaccion-web-historial"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("home"))

    def test_administrador_ve_el_historial_general_sin_cliente_activo(self):
        # El administrador puede consultar operaciones de todos los clientes.
        self.perfil.cliente_activo = None
        self.perfil.save(update_fields=["cliente_activo"])

        with self._roles("administrador"):
            response = self.client.get(
                reverse("transaccion-web-historial"),
                HTTP_HOST="127.0.0.1",
            )

        self.assertSetEqual(
            self._ids_visibles(response),
            {self.compra.pk, self.venta.pk, self.cancelada.pk, self.ajena.pk},
        )
        self.assertTrue(response.context["historial_general"])

    def test_analista_ve_el_historial_general(self):
        # El analista cambiario tiene el mismo alcance de consulta general.
        with self._roles("analista_cambiario"):
            response = self.client.get(
                reverse("transaccion-web-historial"),
                HTTP_HOST="127.0.0.1",
            )

        self.assertIn(self.ajena.pk, self._ids_visibles(response))

    def test_historial_muestra_los_datos_requeridos(self):
        # La tabla debe mostrar todos los datos pedidos por la historia.
        response = self.client.get(
            reverse("transaccion-web-historial"),
            HTTP_HOST="127.0.0.1",
        )

        for encabezado in (
            "ID",
            "Fecha y hora",
            "Cliente",
            "Operación",
            "Moneda",
            "Monto",
            "Tasa aplicada",
            "Comisión",
            "Total",
            "Estado",
        ):
            self.assertContains(response, encabezado)
        self.assertContains(response, str(self.compra.id_transaccion))
        self.assertContains(response, "Cliente Uno")
        self.assertContains(response, "Compra de divisas")
        self.assertContains(response, "USD")
        self.assertContains(response, "Pendiente")

    def test_historial_incluye_ventas_y_canceladas(self):
        # El listado debe aceptar tipos y estados aunque sus flujos lleguen despues.
        response = self.client.get(
            reverse("transaccion-web-historial"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, "Venta de divisas")
        self.assertContains(response, "Cancelada")

    def test_filtro_general_por_cliente(self):
        # El filtro de cliente solo debe devolver operaciones de ese cliente.
        with self._roles("administrador"):
            response = self.client.get(
                reverse("transaccion-web-historial"),
                {"cliente": self.cliente_dos.pk},
                HTTP_HOST="127.0.0.1",
            )

        self.assertSetEqual(self._ids_visibles(response), {self.ajena.pk})

    def test_filtros_por_tipo_y_estado(self):
        # Los filtros pueden combinarse para encontrar una operación concreta.
        response = self.client.get(
            reverse("transaccion-web-historial"),
            {
                "tipo_operacion": TipoOperacion.VENTA,
                "estado": EstadoTransaccion.COMPLETADA,
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertSetEqual(self._ids_visibles(response), {self.venta.pk})

    def test_filtro_por_fecha(self):
        # El rango de fechas debe excluir operaciones que queden fuera.
        fecha_antigua = timezone.now() - timedelta(days=10)
        Transaccion.objects.filter(pk=self.compra.pk).update(
            creada_en=fecha_antigua
        )

        response = self.client.get(
            reverse("transaccion-web-historial"),
            {"fecha_desde": timezone.localdate().isoformat()},
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotIn(self.compra.pk, self._ids_visibles(response))
        self.assertIn(self.venta.pk, self._ids_visibles(response))

    def test_cliente_puede_abrir_el_detalle_de_su_transaccion(self):
        # Una fila propia lleva a un detalle visible y de solo consulta.
        response = self.client.get(
            reverse("transaccion-web-detail", args=[self.compra.pk]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Uno")
        self.assertContains(response, "Ir al historial")

    def test_cliente_no_puede_abrir_el_detalle_ajeno(self):
        # Escribir una URL ajena manualmente debe responder que no existe.
        response = self.client.get(
            reverse("transaccion-web-detail", args=[self.ajena.pk]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 404)

    def test_administrador_puede_abrir_un_detalle_ajeno(self):
        # El alcance general tambien debe aplicarse a la pantalla de detalle.
        with self._roles("administrador"):
            response = self.client.get(
                reverse("transaccion-web-detail", args=[self.ajena.pk]),
                HTTP_HOST="127.0.0.1",
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Dos")

    def test_detalle_de_venta_usa_textos_de_venta(self):
        # El detalle debe explicar correctamente una venta futura.
        response = self.client.get(
            reverse("transaccion-web-detail", args=[self.venta.pk]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, "Venta")
        self.assertContains(response, "Monto entregado")
        self.assertContains(response, "Comisión de venta")
        self.assertContains(response, "Total a recibir")

    def test_historial_no_ofrece_editar_ni_eliminar(self):
        # La historia permite consultar, pero no cambiar ni borrar registros.
        response = self.client.get(
            reverse("transaccion-web-historial"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(response, ">Editar<")
        self.assertNotContains(response, ">Eliminar<")

    def test_historial_rechaza_solicitudes_post(self):
        # Un POST no debe modificar datos desde la pantalla de historial.
        cantidad_antes = Transaccion.objects.count()

        response = self.client.post(
            reverse("transaccion-web-historial"),
            {"estado": EstadoTransaccion.CANCELADA},
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Transaccion.objects.count(), cantidad_antes)

class CalculoVentaVIPTemporalTests(TestCase):
    """Prueba que una venta respete la categoría VIP temporal."""

    @classmethod
    def setUpTestData(cls):
        cls.cliente = Cliente.objects.create(
            ruc="80000901-1",
            nombre="Cliente Minorista con VIP temporal",
            categoria=CategoriaCliente.MINORISTA,
            tipo=TipoCliente.FISICA,
        )

        cls.pyg = Moneda.objects.get(codigo="PYG")
        cls.usd = Moneda.objects.get(codigo="USD")

        cls.tasa = TasaCambio.objects.create(
            moneda_origen=cls.usd,
            moneda_destino=cls.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
            vigente=True,
        )

    def test_venta_aplica_beneficio_vip_a_cliente_con_vip_temporal(self):
        _configurar_beneficio(
            CategoriaCliente.VIP,
            "5.00",
            "50000000.00",
        )

        self.cliente.vip_vigente_hasta = (
            timezone.localdate() + timedelta(days=30)
        )
        self.cliente.save(update_fields=["vip_vigente_hasta"])

        calculo = calcular_venta(
            self.cliente,
            "USD",
            Decimal("100.00"),
        )

        self.assertEqual(
            self.cliente.categoria,
            CategoriaCliente.MINORISTA,
        )

        self.assertEqual(
            calculo["categoria_aplicada"],
            CategoriaCliente.VIP,
        )

        self.assertEqual(
            calculo["beneficio_monto_pyg"],
            Decimal("36000.00"),
        )

        self.assertEqual(
            calculo["total_pyg"],
            Decimal("756000.00"),
        )


CREAR_PAYMENT_INTENT = "integrations.proveedores_pago.stripe_proveedor.stripe.PaymentIntent.create"


def _intento_aceptado(id_intento="pi_aceptado"):
    """Simula el PaymentIntent que Stripe devuelve al aceptar un cobro."""

    return SimpleNamespace(id=id_intento, status="succeeded")


def _rechazo_tarjeta(id_intento="pi_rechazado"):
    """Simula el error que Stripe lanza al rechazar una tarjeta."""

    cuerpo = {
        "error": {
            "type": "card_error",
            "code": "card_declined",
            "decline_code": "generic_decline",
            "message": "Your card was declined.",
            "payment_intent": {"id": id_intento, "object": "payment_intent"},
        }
    }
    return stripe.CardError("Your card was declined.", None, "card_declined", json_body=cuerpo)


class PagoTestMixin:
    """Prepara un cliente con tarjeta, billetera y operaciones para pagar."""

    def setUp(self):
        self.user = User.objects.create_user(username="pagador", password="testpass123")
        self.cliente = Cliente.objects.create(
            ruc="80000401-1",
            nombre="Cliente Pagador",
            categoria=CategoriaCliente.MINORISTA,
            tipo=TipoCliente.FISICA,
        )
        self.otro_cliente = Cliente.objects.create(
            ruc="80000402-2",
            nombre="Cliente Ajeno",
            categoria=CategoriaCliente.MINORISTA,
            tipo=TipoCliente.FISICA,
        )
        self.perfil = UsuarioCliente.objects.create(usuario=self.user, cliente_activo=self.cliente)
        self.pyg = Moneda.objects.get(codigo="PYG")
        self.usd = Moneda.objects.get(codigo="USD")
        self.tasa = TasaCambio.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            precio_compra=Decimal("7200.0000"),
            precio_venta=Decimal("7350.0000"),
            vigente=True,
        )
        self.tarjeta = self._crear_metodo(self.cliente)
        self.billetera = self._crear_metodo(
            self.cliente,
            tipo=TipoMetodoPago.BILLETERA_ELECTRONICA,
            ultimos_cuatro_digitos="",
            fecha_vencimiento="",
            stripe_payment_method_id="",
            proveedor_billetera="Tigo Money",
            numero_billetera="0981123456",
        )

    def _crear_metodo(self, cliente, **cambios):
        """Crea un método de pago activo; por defecto una tarjeta de prueba aprobada."""

        datos = {
            "cliente": cliente,
            "tipo": TipoMetodoPago.TARJETA_CREDITO,
            "titular": "Titular de prueba",
            "ultimos_cuatro_digitos": "4242",
            "fecha_vencimiento": "12/30",
            "stripe_payment_method_id": "pm_card_visa",
            "activo": True,
        }
        datos.update(cambios)
        return MetodoPago.objects.create(**datos)

    def _crear_transaccion(
        self,
        tipo=TipoOperacion.COMPRA,
        estado=EstadoTransaccion.PENDIENTE,
        metodo_pago=None,
        cliente=None,
    ):
        """Crea una operación válida de 100 USD con el método de pago indicado."""

        cliente = cliente or self.cliente
        if metodo_pago is None and cliente == self.cliente:
            metodo_pago = self.tarjeta
        es_compra = tipo == TipoOperacion.COMPRA
        subtotal = Decimal("735000.00") if es_compra else Decimal("720000.00")
        comision = Decimal("7350.00") if es_compra else Decimal("7200.00")
        ahora = timezone.now()
        transaccion = Transaccion(
            cliente=cliente,
            creada_por=self.user,
            tipo_operacion=tipo,
            moneda=self.usd,
            tasa_cambio=self.tasa,
            tasa_aplicada=self.tasa.precio_venta if es_compra else self.tasa.precio_compra,
            fecha_vigencia_tasa=self.tasa.fecha_vigencia,
            metodo_pago=metodo_pago,
            monto_divisa=Decimal("100.00"),
            subtotal_pyg=subtotal,
            categoria_aplicada=cliente.categoria,
            comision_porcentaje=Decimal("1.00"),
            comision_monto_pyg=comision,
            total_pyg=subtotal + comision if es_compra else subtotal - comision,
            estado=estado,
            cancelada_en=ahora if estado == EstadoTransaccion.CANCELADA else None,
            etapa_cancelacion=(
                EtapaCancelacion.PREVIA_PAGO if estado == EstadoTransaccion.CANCELADA else None
            ),
            completada_en=(
                ahora
                if estado in (EstadoTransaccion.COMPLETADA, EstadoTransaccion.ANULADA)
                else None
            ),
        )
        transaccion.full_clean()
        transaccion.save()
        return transaccion


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class IniciarPagoServicioTests(PagoTestMixin, TestCase):
    """Prueba los criterios de aceptación de HU-15 sobre el servicio de pago."""

    def test_compra_con_tarjeta_registra_pago_en_proceso_sin_completar_la_operacion(self):
        transaccion = self._crear_transaccion()

        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_compra")) as crear:
            pago = iniciar_pago(transaccion, self.user)

        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)
        self.assertEqual(pago.proveedor, ProveedorPago.STRIPE)
        self.assertEqual(pago.referencia_externa, "pi_compra")
        self.assertEqual(pago.monto, Decimal("742350.00"))
        self.assertEqual(pago.moneda_id, "PYG")
        self.assertEqual(pago.metodo_pago, self.tarjeta)
        self.assertEqual(pago.iniciado_por, self.user)
        self.assertEqual(crear.call_args.kwargs["amount"], 742350)
        self.assertEqual(crear.call_args.kwargs["currency"], "pyg")
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)
        self.assertIsNone(transaccion.completada_en)

    def test_total_con_decimales_se_cobra_en_guaranies_enteros(self):
        transaccion = self._crear_transaccion()
        Transaccion.objects.filter(pk=transaccion.pk).update(total_pyg=Decimal("742350.50"))

        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado()) as crear:
            pago = iniciar_pago(transaccion, self.user)

        self.assertEqual(pago.monto, Decimal("742351.00"))
        self.assertEqual(crear.call_args.kwargs["amount"], 742351)

    def test_venta_con_tarjeta_cobra_la_divisa_entregada(self):
        transaccion = self._crear_transaccion(tipo=TipoOperacion.VENTA)

        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_venta")) as crear:
            pago = iniciar_pago(transaccion, self.user)

        self.assertEqual(pago.monto, Decimal("100.00"))
        self.assertEqual(pago.moneda_id, "USD")
        self.assertEqual(crear.call_args.kwargs["amount"], 10000)
        self.assertEqual(crear.call_args.kwargs["currency"], "usd")

    def test_compra_con_billetera_usa_el_simulador(self):
        transaccion = self._crear_transaccion(metodo_pago=self.billetera)

        with patch(CREAR_PAYMENT_INTENT) as crear:
            pago = iniciar_pago(transaccion, self.user)

        crear.assert_not_called()
        self.assertEqual(pago.proveedor, ProveedorPago.SIMULADOR_BILLETERA)
        self.assertTrue(pago.referencia_externa.startswith("SIM-"))
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)
        self.assertEqual(pago.moneda_id, "PYG")

    def test_venta_con_billetera_cobra_la_divisa_en_el_simulador(self):
        transaccion = self._crear_transaccion(tipo=TipoOperacion.VENTA, metodo_pago=self.billetera)

        pago = iniciar_pago(transaccion, self.user)

        self.assertEqual(pago.proveedor, ProveedorPago.SIMULADOR_BILLETERA)
        self.assertEqual(pago.monto, Decimal("100.00"))
        self.assertEqual(pago.moneda_id, "USD")
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)

    def test_solo_se_pagan_operaciones_pendientes(self):
        for estado in (
            EstadoTransaccion.COMPLETADA,
            EstadoTransaccion.CANCELADA,
            EstadoTransaccion.ANULADA,
        ):
            with self.subTest(estado=estado):
                transaccion = self._crear_transaccion(estado=estado)

                with patch(CREAR_PAYMENT_INTENT) as crear:
                    with self.assertRaisesMessage(PagoNoIniciableError, "estado pendiente"):
                        iniciar_pago(transaccion, self.user)

                crear.assert_not_called()
                self.assertFalse(transaccion.pagos.exists())

    def test_metodo_inactivo_no_permite_iniciar_el_pago(self):
        transaccion = self._crear_transaccion()
        self.tarjeta.activo = False
        self.tarjeta.save(update_fields=["activo"])

        with patch(CREAR_PAYMENT_INTENT) as crear:
            with self.assertRaisesMessage(PagoNoIniciableError, "método de pago activo"):
                iniciar_pago(transaccion, self.user)

        crear.assert_not_called()
        self.assertFalse(Pago.objects.exists())

    def test_operacion_sin_metodo_no_permite_iniciar_el_pago(self):
        transaccion = self._crear_transaccion()
        Transaccion.objects.filter(pk=transaccion.pk).update(metodo_pago=None)

        with self.assertRaisesMessage(PagoNoIniciableError, "método de pago activo"):
            iniciar_pago(transaccion, self.user)

        self.assertFalse(Pago.objects.exists())

    def test_tarjeta_sin_token_no_esta_habilitada(self):
        tarjeta = self._crear_metodo(
            self.cliente, ultimos_cuatro_digitos="4444", stripe_payment_method_id=""
        )
        transaccion = self._crear_transaccion(metodo_pago=tarjeta)

        with patch(CREAR_PAYMENT_INTENT) as crear:
            with self.assertRaisesMessage(PagoNoIniciableError, "no está habilitada"):
                iniciar_pago(transaccion, self.user)

        crear.assert_not_called()
        self.assertFalse(Pago.objects.exists())

    def test_rechazo_del_proveedor_registra_la_referencia_y_no_completa(self):
        transaccion = self._crear_transaccion()

        with patch(CREAR_PAYMENT_INTENT, side_effect=_rechazo_tarjeta("pi_rechazado")):
            with self.assertRaisesMessage(PagoNoIniciableError, "rechazada por el emisor"):
                iniciar_pago(transaccion, self.user)

        pago = transaccion.pagos.get()
        self.assertEqual(pago.estado, EstadoPago.RECHAZADO)
        self.assertEqual(pago.referencia_externa, "pi_rechazado")
        self.assertIn("card_declined", pago.mensaje_proveedor)
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)
        self.assertIsNone(transaccion.completada_en)

    def test_falla_de_comunicacion_registra_error_y_no_completa(self):
        transaccion = self._crear_transaccion()

        with patch(CREAR_PAYMENT_INTENT, side_effect=stripe.APIConnectionError("timeout")):
            with self.assertRaisesMessage(PagoNoIniciableError, "No pudimos comunicarnos"):
                iniciar_pago(transaccion, self.user)

        pago = transaccion.pagos.get()
        self.assertEqual(pago.estado, EstadoPago.ERROR)
        self.assertIsNone(pago.referencia_externa)
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)

    def test_no_se_inicia_un_segundo_pago_mientras_otro_esta_en_proceso(self):
        transaccion = self._crear_transaccion()
        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_primero")):
            iniciar_pago(transaccion, self.user)

        with patch(CREAR_PAYMENT_INTENT) as crear:
            with self.assertRaisesMessage(PagoNoIniciableError, "Ya hay un pago en proceso"):
                iniciar_pago(transaccion, self.user)

        crear.assert_not_called()
        self.assertEqual(transaccion.pagos.count(), 1)

    def test_se_puede_reintentar_despues_de_un_rechazo(self):
        transaccion = self._crear_transaccion()
        with patch(CREAR_PAYMENT_INTENT, side_effect=_rechazo_tarjeta("pi_rechazado")):
            with self.assertRaises(PagoNoIniciableError):
                iniciar_pago(transaccion, self.user)

        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_reintento")):
            pago = iniciar_pago(transaccion, self.user)

        self.assertEqual(pago.referencia_externa, "pi_reintento")
        self.assertEqual(transaccion.pagos.count(), 2)

    def test_la_base_impide_dos_pagos_activos_para_la_misma_operacion(self):
        transaccion = self._crear_transaccion()
        datos = {
            "transaccion": transaccion,
            "proveedor": ProveedorPago.STRIPE,
            "monto": Decimal("1000.00"),
            "moneda": self.pyg,
            "estado": EstadoPago.EN_PROCESO,
        }
        Pago.objects.create(referencia_externa="pi_uno", **datos)

        with self.assertRaises(IntegrityError):
            Pago.objects.create(referencia_externa="pi_dos", **datos)


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC, STRIPE_SECRET_KEY="sk_test_dummy")
class IniciarPagoWebTests(PagoTestMixin, TestCase):
    """Prueba la acción web de pago y su presentación en el detalle."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def _roles(self, *roles_permitidos):
        """Simula los roles de Keycloak necesarios para cada prueba."""

        return patch(
            "transacciones.views.tiene_rol",
            side_effect=lambda request, rol: rol in roles_permitidos,
        )

    def _pagar(self, transaccion):
        return self.client.post(
            reverse("transaccion-web-iniciar-pago", args=[transaccion.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

    def _detalle(self, transaccion, *roles):
        with self._roles(*roles):
            return self.client.get(
                reverse("transaccion-web-detail", args=[transaccion.id_transaccion]),
                HTTP_HOST="127.0.0.1",
            )

    def _mensajes(self, response):
        return [str(mensaje) for mensaje in response.wsgi_request._messages]

    def test_pago_iniciado_redirige_al_detalle_con_la_referencia(self):
        transaccion = self._crear_transaccion()

        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_web")):
            response = self._pagar(transaccion)

        self.assertRedirects(
            response,
            reverse("transaccion-web-detail", args=[transaccion.id_transaccion]),
            fetch_redirect_response=False,
        )
        self.assertTrue(any("pi_web" in mensaje for mensaje in self._mensajes(response)))

    def test_rechazo_informa_al_usuario(self):
        transaccion = self._crear_transaccion()

        with patch(CREAR_PAYMENT_INTENT, side_effect=_rechazo_tarjeta()):
            response = self._pagar(transaccion)

        self.assertTrue(
            any(
                "No se pudo iniciar el pago" in mensaje and "rechazada" in mensaje
                for mensaje in self._mensajes(response)
            )
        )
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)

    def test_no_permite_pagar_operaciones_de_otro_cliente(self):
        ajena = self._crear_transaccion(
            cliente=self.otro_cliente,
            metodo_pago=self._crear_metodo(self.otro_cliente),
        )

        with self._roles("administrador"), patch(CREAR_PAYMENT_INTENT) as crear:
            response = self._pagar(ajena)

        self.assertEqual(response.status_code, 404)
        crear.assert_not_called()
        self.assertFalse(Pago.objects.exists())

    def test_solo_acepta_post(self):
        transaccion = self._crear_transaccion()

        response = self.client.get(
            reverse("transaccion-web-iniciar-pago", args=[transaccion.id_transaccion]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 405)

    def test_usuario_anonimo_es_redirigido_al_login(self):
        transaccion = self._crear_transaccion()
        self.client.logout()

        response = self._pagar(transaccion)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Pago.objects.exists())

    def test_detalle_muestra_el_boton_de_pago_si_esta_pendiente(self):
        transaccion = self._crear_transaccion()

        response = self._detalle(transaccion)

        self.assertTrue(response.context["puede_iniciar_pago"])
        self.assertContains(
            response,
            reverse("transaccion-web-iniciar-pago", args=[transaccion.id_transaccion]),
        )

    def test_detalle_oculta_el_boton_y_muestra_la_referencia_con_pago_en_proceso(self):
        transaccion = self._crear_transaccion()
        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_en_proceso")):
            iniciar_pago(transaccion, self.user)

        response = self._detalle(transaccion)

        self.assertFalse(response.context["puede_iniciar_pago"])
        self.assertContains(response, "pi_en_proceso")
        self.assertContains(response, "Pago en proceso")

    def test_detalle_no_ofrece_pagar_una_operacion_completada(self):
        transaccion = self._crear_transaccion(estado=EstadoTransaccion.COMPLETADA)

        response = self._detalle(transaccion)

        self.assertFalse(response.context["puede_iniciar_pago"])

    def test_detalle_no_ofrece_pagar_una_operacion_ajena_al_administrador(self):
        ajena = self._crear_transaccion(
            cliente=self.otro_cliente,
            metodo_pago=self._crear_metodo(self.otro_cliente),
        )

        response = self._detalle(ajena, "administrador")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["puede_iniciar_pago"])


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class CambiarMetodoPagoServicioTests(PagoTestMixin, TestCase):
    """Prueba que se pueda pagar con otro método después de un rechazo."""

    def _rechazar_primer_intento(self, transaccion):
        with patch(CREAR_PAYMENT_INTENT, side_effect=_rechazo_tarjeta("pi_rechazado")):
            with self.assertRaises(PagoNoIniciableError):
                iniciar_pago(transaccion, self.user)

    def test_despues_de_un_rechazo_se_paga_con_otro_metodo(self):
        transaccion = self._crear_transaccion()
        self._rechazar_primer_intento(transaccion)

        pago = iniciar_pago(transaccion, self.user, metodo_pago=self.billetera)

        self.assertEqual(pago.proveedor, ProveedorPago.SIMULADOR_BILLETERA)
        self.assertEqual(pago.metodo_pago, self.billetera)
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.metodo_pago, self.billetera)
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)

    def test_los_intentos_anteriores_conservan_su_metodo(self):
        transaccion = self._crear_transaccion()
        self._rechazar_primer_intento(transaccion)

        iniciar_pago(transaccion, self.user, metodo_pago=self.billetera)

        anterior = transaccion.pagos.get(estado=EstadoPago.RECHAZADO)
        self.assertEqual(anterior.metodo_pago, self.tarjeta)
        self.assertEqual(transaccion.pagos.count(), 2)

    def test_se_puede_cambiar_a_otra_tarjeta(self):
        otra = self._crear_metodo(self.cliente, ultimos_cuatro_digitos="4242")
        transaccion = self._crear_transaccion()
        self._rechazar_primer_intento(transaccion)

        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_otra")) as crear:
            pago = iniciar_pago(transaccion, self.user, metodo_pago=otra)

        self.assertEqual(pago.referencia_externa, "pi_otra")
        self.assertEqual(pago.metodo_pago, otra)
        self.assertEqual(crear.call_args.kwargs["payment_method"], "pm_card_visa")

    def test_metodo_de_otro_cliente_no_esta_disponible(self):
        ajeno = self._crear_metodo(self.otro_cliente)
        transaccion = self._crear_transaccion()

        with patch(CREAR_PAYMENT_INTENT) as crear:
            with self.assertRaisesMessage(PagoNoIniciableError, "no está disponible"):
                iniciar_pago(transaccion, self.user, metodo_pago=ajeno)

        crear.assert_not_called()
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.metodo_pago, self.tarjeta)
        self.assertFalse(Pago.objects.exists())

    def test_metodo_inactivo_no_esta_disponible(self):
        inactivo = self._crear_metodo(self.cliente, activo=False)
        transaccion = self._crear_transaccion()

        with self.assertRaisesMessage(PagoNoIniciableError, "no está disponible"):
            iniciar_pago(transaccion, self.user, metodo_pago=inactivo)

        transaccion.refresh_from_db()
        self.assertEqual(transaccion.metodo_pago, self.tarjeta)

    def test_metodo_no_habilitado_no_reemplaza_al_de_la_operacion(self):
        sin_token = self._crear_metodo(
            self.cliente, ultimos_cuatro_digitos="4444", stripe_payment_method_id=""
        )
        transaccion = self._crear_transaccion()

        with self.assertRaisesMessage(PagoNoIniciableError, "no está habilitada"):
            iniciar_pago(transaccion, self.user, metodo_pago=sin_token)

        transaccion.refresh_from_db()
        self.assertEqual(transaccion.metodo_pago, self.tarjeta)
        self.assertFalse(Pago.objects.exists())

    def test_indicar_el_mismo_metodo_equivale_a_no_indicar_ninguno(self):
        transaccion = self._crear_transaccion()

        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_mismo")):
            pago = iniciar_pago(transaccion, self.user, metodo_pago=self.tarjeta)

        self.assertEqual(pago.metodo_pago, self.tarjeta)
        self.assertEqual(pago.referencia_externa, "pi_mismo")


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC, STRIPE_SECRET_KEY="sk_test_dummy")
class CambiarMetodoPagoWebTests(PagoTestMixin, TestCase):
    """Prueba la elección de otro método desde el detalle de la operación."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.transaccion = self._crear_transaccion()

    def _roles(self):
        return patch("transacciones.views.tiene_rol", return_value=False)

    def _detalle(self):
        with self._roles():
            return self.client.get(
                reverse("transaccion-web-detail", args=[self.transaccion.id_transaccion]),
                HTTP_HOST="127.0.0.1",
            )

    def _pagar(self, **datos):
        return self.client.post(
            reverse("transaccion-web-iniciar-pago", args=[self.transaccion.id_transaccion]),
            datos,
            HTTP_HOST="127.0.0.1",
        )

    def _mensajes(self, response):
        return [str(mensaje) for mensaje in response.wsgi_request._messages]

    def _rechazar_primer_intento(self):
        with patch(CREAR_PAYMENT_INTENT, side_effect=_rechazo_tarjeta()):
            self._pagar()

    def test_antes_de_un_intento_fallido_no_se_ofrece_cambiar_de_metodo(self):
        response = self._detalle()

        self.assertTrue(response.context["puede_iniciar_pago"])
        self.assertFalse(response.context["puede_cambiar_metodo"])
        self.assertNotContains(response, 'name="metodo_pago"')

    def test_despues_de_un_rechazo_se_ofrecen_los_metodos_activos(self):
        inactivo = self._crear_metodo(self.cliente, activo=False, ultimos_cuatro_digitos="1111")
        ajeno = self._crear_metodo(self.otro_cliente, ultimos_cuatro_digitos="2222")
        self._rechazar_primer_intento()

        response = self._detalle()

        self.assertTrue(response.context["puede_cambiar_metodo"])
        self.assertContains(response, 'name="metodo_pago"')
        ofrecidos = {m.pk for m in response.context["metodos_disponibles"]}
        self.assertEqual(ofrecidos, {self.tarjeta.pk, self.billetera.pk})
        self.assertNotIn(inactivo.pk, ofrecidos)
        self.assertNotIn(ajeno.pk, ofrecidos)

    def test_con_un_solo_metodo_se_mantiene_el_boton_de_reintento(self):
        self.billetera.activo = False
        self.billetera.save(update_fields=["activo"])
        self._rechazar_primer_intento()

        response = self._detalle()

        self.assertTrue(response.context["puede_iniciar_pago"])
        self.assertFalse(response.context["puede_cambiar_metodo"])
        self.assertNotContains(response, 'name="metodo_pago"')

    def test_se_paga_con_el_metodo_elegido(self):
        self._rechazar_primer_intento()

        response = self._pagar(metodo_pago=str(self.billetera.pk))

        self.assertTrue(
            any("Simulador de billetera" in mensaje for mensaje in self._mensajes(response))
        )
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.metodo_pago, self.billetera)
        self.assertEqual(self.transaccion.pagos.count(), 2)
        self.assertEqual(self.transaccion.estado, EstadoTransaccion.PENDIENTE)

    def test_rechaza_un_metodo_de_otro_cliente(self):
        ajeno = self._crear_metodo(self.otro_cliente)

        with patch(CREAR_PAYMENT_INTENT) as crear:
            response = self._pagar(metodo_pago=str(ajeno.pk))

        crear.assert_not_called()
        self.assertTrue(
            any("no está disponible" in mensaje for mensaje in self._mensajes(response))
        )
        self.assertFalse(Pago.objects.exists())

    def test_rechaza_un_identificador_invalido(self):
        with patch(CREAR_PAYMENT_INTENT) as crear:
            response = self._pagar(metodo_pago="abc")

        crear.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Pago.objects.exists())


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC, STRIPE_SECRET_KEY="sk_test_dummy")
class CambiarMetodoPagoVentaTests(PagoTestMixin, TestCase):
    """Prueba el cambio de método de pago en una venta de divisas."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.transaccion = self._crear_transaccion(tipo=TipoOperacion.VENTA)

    def _detalle(self):
        with patch("transacciones.views.tiene_rol", return_value=False):
            return self.client.get(
                reverse("transaccion-web-detail", args=[self.transaccion.id_transaccion]),
                HTTP_HOST="127.0.0.1",
            )

    def _pagar(self, **datos):
        return self.client.post(
            reverse("transaccion-web-iniciar-pago", args=[self.transaccion.id_transaccion]),
            datos,
            HTTP_HOST="127.0.0.1",
        )

    def _mensajes(self, response):
        return [str(mensaje) for mensaje in response.wsgi_request._messages]

    def test_venta_rechazada_ofrece_elegir_otro_metodo(self):
        with patch(CREAR_PAYMENT_INTENT, side_effect=_rechazo_tarjeta()):
            self._pagar()

        response = self._detalle()

        self.assertTrue(response.context["puede_cambiar_metodo"])
        self.assertContains(response, 'name="metodo_pago"')
        self.assertContains(response, "Pagar 100 USD")

    def test_venta_se_paga_con_la_billetera_despues_de_un_rechazo(self):
        with patch(CREAR_PAYMENT_INTENT, side_effect=_rechazo_tarjeta()):
            self._pagar()

        response = self._pagar(metodo_pago=str(self.billetera.pk))

        self.assertTrue(
            any("Simulador de billetera" in mensaje for mensaje in self._mensajes(response))
        )
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.metodo_pago, self.billetera)
        pago = self.transaccion.pagos.get(estado=EstadoPago.EN_PROCESO)
        self.assertEqual(pago.monto, Decimal("100.00"))
        self.assertEqual(pago.moneda_id, "USD")
        self.assertEqual(self.transaccion.estado, EstadoTransaccion.PENDIENTE)

    def test_metodo_sin_token_ofrece_elegir_otro_sin_haber_intentado_pagar(self):
        sin_token = self._crear_metodo(
            self.cliente, ultimos_cuatro_digitos="4444", stripe_payment_method_id=""
        )
        Transaccion.objects.filter(pk=self.transaccion.pk).update(metodo_pago=sin_token)

        response = self._detalle()

        self.assertFalse(self.transaccion.pagos.exists())
        self.assertTrue(response.context["puede_cambiar_metodo"])
        self.assertContains(response, "no permite iniciar el pago")

    def test_metodo_sin_token_se_reemplaza_por_otro_habilitado(self):
        sin_token = self._crear_metodo(
            self.cliente, ultimos_cuatro_digitos="4444", stripe_payment_method_id=""
        )
        Transaccion.objects.filter(pk=self.transaccion.pk).update(metodo_pago=sin_token)

        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado("pi_venta_nueva")):
            self._pagar(metodo_pago=str(self.tarjeta.pk))

        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.metodo_pago, self.tarjeta)
        self.assertEqual(self.transaccion.pagos.get().referencia_externa, "pi_venta_nueva")

    def test_metodo_inactivo_ofrece_elegir_otro(self):
        self.tarjeta.activo = False
        self.tarjeta.save(update_fields=["activo"])
        otra = self._crear_metodo(self.cliente, ultimos_cuatro_digitos="1111")

        response = self._detalle()

        self.assertTrue(response.context["puede_cambiar_metodo"])
        ofrecidos = {m.pk for m in response.context["metodos_disponibles"]}
        self.assertEqual(ofrecidos, {self.billetera.pk, otra.pk})

    def test_metodo_habilitado_sin_intentos_no_muestra_el_selector(self):
        response = self._detalle()

        self.assertFalse(response.context["puede_cambiar_metodo"])
        self.assertNotContains(response, 'name="metodo_pago"')


# --- HU-18: confirmación automática de pago ---------------------------------

SECRETO_WEBHOOK = "whsec_prueba"
CONSULTAR_PAYMENT_INTENT = "integrations.proveedores_pago.stripe_proveedor.stripe.PaymentIntent.retrieve"


def _resultado_de(pago, aprobado=True, **cambios):
    """Construye el resultado que informaría el proveedor para un pago."""

    datos = {
        "referencia_externa": pago.referencia_externa,
        "aprobado": aprobado,
        "id_pago": pago.pk,
        "monto": pago.monto,
        "moneda": pago.moneda_id,
        "detalle": "" if aprobado else "card_declined: Your card was declined.",
    }
    datos.update(cambios)
    return ResultadoPago(**datos)


def _payment_intent_de(pago, estado="succeeded"):
    """PaymentIntent de Stripe que corresponde a un pago registrado."""

    return {
        "id": pago.referencia_externa,
        "object": "payment_intent",
        "status": estado,
        "amount": a_unidad_minima(pago.monto, pago.moneda_id),
        "currency": pago.moneda_id.lower(),
        "metadata": {"id_pago": str(pago.pk), "id_transaccion": str(pago.transaccion_id)},
        "last_payment_error": None,
    }


def _webhook_firmado(tipo, intento, secreto=SECRETO_WEBHOOK, id_evento="evt_1"):
    payload = json.dumps(
        {"id": id_evento, "object": "event", "type": tipo, "data": {"object": intento}}
    )
    return payload, stripe.WebhookSignature.generate_signature_header(payload, secreto)


class ConfirmacionPagoTestMixin(PagoTestMixin):
    """Agrega a los datos de pago helpers para iniciar pagos ya en proceso."""

    def _iniciar_con_tarjeta(self, transaccion=None, referencia="pi_ok"):
        transaccion = transaccion or self._crear_transaccion()
        with patch(CREAR_PAYMENT_INTENT, return_value=_intento_aceptado(referencia)):
            return iniciar_pago(transaccion, self.user)

    def _iniciar_con_billetera(self, tipo=TipoOperacion.COMPRA):
        transaccion = self._crear_transaccion(tipo=tipo, metodo_pago=self.billetera)
        return iniciar_pago(transaccion, self.user)


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class ProcesarResultadoPagoTests(ConfirmacionPagoTestMixin, TestCase):
    """Prueba los criterios de aceptación de HU-18 sobre la función idempotente."""

    def test_confirmacion_completa_la_operacion_y_registra_la_fecha(self):
        pago = self._iniciar_con_tarjeta(referencia="pi_confirmado")

        resultado = procesar_resultado_pago(ProveedorPago.STRIPE, _resultado_de(pago))

        self.assertEqual(resultado, ResultadoProcesamiento.CONFIRMADO)
        pago.refresh_from_db()
        transaccion = pago.transaccion
        transaccion.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.CONFIRMADO)
        self.assertIsNotNone(pago.confirmado_en)
        self.assertEqual(pago.referencia_externa, "pi_confirmado")
        self.assertEqual(transaccion.estado, EstadoTransaccion.COMPLETADA)
        self.assertEqual(transaccion.completada_en, pago.confirmado_en)

    def test_notificacion_repetida_no_completa_dos_veces(self):
        pago = self._iniciar_con_tarjeta()
        procesar_resultado_pago(ProveedorPago.STRIPE, _resultado_de(pago))
        pago.refresh_from_db()
        transaccion = Transaccion.objects.get(pk=pago.transaccion_id)
        confirmado_en, completada_en = pago.confirmado_en, transaccion.completada_en

        resultado = procesar_resultado_pago(ProveedorPago.STRIPE, _resultado_de(pago))

        self.assertEqual(resultado, ResultadoProcesamiento.DUPLICADO)
        pago.refresh_from_db()
        transaccion.refresh_from_db()
        self.assertEqual(pago.confirmado_en, confirmado_en)
        self.assertEqual(transaccion.completada_en, completada_en)

    def test_rechazo_no_completa_la_operacion_y_permite_reintentar(self):
        pago = self._iniciar_con_tarjeta()

        resultado = procesar_resultado_pago(
            ProveedorPago.STRIPE, _resultado_de(pago, aprobado=False)
        )

        self.assertEqual(resultado, ResultadoProcesamiento.RECHAZADO)
        pago.refresh_from_db()
        transaccion = Transaccion.objects.get(pk=pago.transaccion_id)
        self.assertEqual(pago.estado, EstadoPago.RECHAZADO)
        self.assertIsNone(pago.confirmado_en)
        self.assertIn("card_declined", pago.mensaje_proveedor)
        self.assertEqual(transaccion.estado, EstadoTransaccion.PENDIENTE)
        self.assertIsNone(transaccion.completada_en)

        nuevo = self._iniciar_con_tarjeta(transaccion, referencia="pi_reintento")
        self.assertEqual(nuevo.estado, EstadoPago.EN_PROCESO)

    def test_un_rechazo_despues_de_confirmar_no_cambia_nada(self):
        pago = self._iniciar_con_tarjeta()
        procesar_resultado_pago(ProveedorPago.STRIPE, _resultado_de(pago))

        resultado = procesar_resultado_pago(
            ProveedorPago.STRIPE, _resultado_de(pago, aprobado=False)
        )

        self.assertEqual(resultado, ResultadoProcesamiento.DUPLICADO)
        self.assertEqual(Transaccion.objects.get(pk=pago.transaccion_id).estado, EstadoTransaccion.COMPLETADA)

    def test_monto_distinto_no_se_acepta(self):
        pago = self._iniciar_con_tarjeta()

        resultado = procesar_resultado_pago(
            ProveedorPago.STRIPE, _resultado_de(pago, monto=Decimal("1.00"))
        )

        self.assertEqual(resultado, ResultadoProcesamiento.INVALIDO)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)
        self.assertEqual(
            Transaccion.objects.get(pk=pago.transaccion_id).estado, EstadoTransaccion.PENDIENTE
        )

    def test_moneda_distinta_no_se_acepta(self):
        pago = self._iniciar_con_tarjeta()

        resultado = procesar_resultado_pago(ProveedorPago.STRIPE, _resultado_de(pago, moneda="USD"))

        self.assertEqual(resultado, ResultadoProcesamiento.INVALIDO)

    def test_referencia_distinta_no_se_acepta(self):
        pago = self._iniciar_con_tarjeta(referencia="pi_original")

        resultado = procesar_resultado_pago(
            ProveedorPago.STRIPE, _resultado_de(pago, referencia_externa="pi_otro")
        )

        self.assertEqual(resultado, ResultadoProcesamiento.INVALIDO)
        pago.refresh_from_db()
        self.assertEqual(pago.referencia_externa, "pi_original")
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)

    def test_pago_desconocido_se_ignora(self):
        resultado = procesar_resultado_pago(
            ProveedorPago.STRIPE,
            ResultadoPago(referencia_externa="pi_ajeno", aprobado=True),
        )

        self.assertEqual(resultado, ResultadoProcesamiento.IGNORADO)

    def test_resultado_de_otro_proveedor_no_afecta_al_pago(self):
        pago = self._iniciar_con_tarjeta()

        resultado = procesar_resultado_pago(ProveedorPago.SIMULADOR_BILLETERA, _resultado_de(pago))

        self.assertEqual(resultado, ResultadoProcesamiento.IGNORADO)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)

    def test_pago_con_error_de_comunicacion_puede_confirmarse_despues(self):
        transaccion = self._crear_transaccion()
        with patch(CREAR_PAYMENT_INTENT, side_effect=stripe.APIConnectionError("timeout")):
            with self.assertRaises(PagoNoIniciableError):
                iniciar_pago(transaccion, self.user)
        pago = transaccion.pagos.get()

        resultado = procesar_resultado_pago(
            ProveedorPago.STRIPE, _resultado_de(pago, referencia_externa="pi_tardio")
        )

        self.assertEqual(resultado, ResultadoProcesamiento.CONFIRMADO)
        pago.refresh_from_db()
        self.assertEqual(pago.referencia_externa, "pi_tardio")
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.COMPLETADA)

    def test_confirmacion_sobre_operacion_no_pendiente_queda_para_revision(self):
        pago = self._iniciar_con_tarjeta()
        Transaccion.objects.filter(pk=pago.transaccion_id).update(
            estado=EstadoTransaccion.CANCELADA,
            cancelada_en=timezone.now(),
            etapa_cancelacion=EtapaCancelacion.PREVIA_PAGO,
        )

        resultado = procesar_resultado_pago(ProveedorPago.STRIPE, _resultado_de(pago))

        self.assertEqual(resultado, ResultadoProcesamiento.CONFIRMADO)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.CONFIRMADO)
        self.assertIn("requiere revisión", pago.mensaje_proveedor)
        transaccion = Transaccion.objects.get(pk=pago.transaccion_id)
        self.assertEqual(transaccion.estado, EstadoTransaccion.CANCELADA)
        self.assertIsNone(transaccion.completada_en)

    def test_confirmacion_temprana_no_es_pisada_al_terminar_de_iniciar_el_pago(self):
        transaccion = self._crear_transaccion()

        def crear_y_notificar(**kwargs):
            # El webhook llega antes de que Stripe responda a la creación del cobro.
            id_pago = int(kwargs["metadata"]["id_pago"])
            pago = Pago.objects.get(pk=id_pago)
            procesar_resultado_pago(
                ProveedorPago.STRIPE,
                ResultadoPago(
                    referencia_externa="pi_temprano",
                    aprobado=True,
                    id_pago=id_pago,
                    monto=pago.monto,
                    moneda=pago.moneda_id,
                ),
            )
            return _intento_aceptado("pi_temprano")

        with patch(CREAR_PAYMENT_INTENT, side_effect=crear_y_notificar):
            pago = iniciar_pago(transaccion, self.user)

        self.assertEqual(pago.estado, EstadoPago.CONFIRMADO)
        self.assertEqual(pago.referencia_externa, "pi_temprano")
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, EstadoTransaccion.COMPLETADA)

    def test_billetera_aprobada_completa_una_venta(self):
        pago = self._iniciar_con_billetera(tipo=TipoOperacion.VENTA)

        resultado = procesar_resultado_pago(
            ProveedorPago.SIMULADOR_BILLETERA,
            SimuladorBilleteraProveedor().resultado_simulado(pago, aprobado=True),
        )

        self.assertEqual(resultado, ResultadoProcesamiento.CONFIRMADO)
        self.assertEqual(
            Transaccion.objects.get(pk=pago.transaccion_id).estado, EstadoTransaccion.COMPLETADA
        )


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET=SECRETO_WEBHOOK)
class WebhookStripeTests(ConfirmacionPagoTestMixin, TestCase):
    """Prueba el endpoint que recibe las notificaciones de Stripe."""

    def setUp(self):
        super().setUp()
        # Stripe no envía sesión ni token CSRF.
        self.stripe = Client(enforce_csrf_checks=True)

    def _enviar(self, payload, firma):
        return self.stripe.post(
            reverse("webhook-stripe"),
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=firma,
            HTTP_HOST="127.0.0.1",
        )

    def test_pago_aprobado_completa_la_operacion(self):
        pago = self._iniciar_con_tarjeta()

        response = self._enviar(*_webhook_firmado("payment_intent.succeeded", _payment_intent_de(pago)))

        self.assertEqual(response.status_code, 200)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.CONFIRMADO)
        self.assertEqual(
            Transaccion.objects.get(pk=pago.transaccion_id).estado, EstadoTransaccion.COMPLETADA
        )

    def test_evento_reenviado_no_completa_dos_veces(self):
        pago = self._iniciar_con_tarjeta()
        evento = _webhook_firmado("payment_intent.succeeded", _payment_intent_de(pago))
        self._enviar(*evento)
        completada_en = Transaccion.objects.get(pk=pago.transaccion_id).completada_en

        response = self._enviar(*evento)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Transaccion.objects.get(pk=pago.transaccion_id).completada_en, completada_en
        )

    def test_pago_rechazado_deja_la_operacion_pendiente(self):
        pago = self._iniciar_con_tarjeta()
        intento = _payment_intent_de(pago, estado="requires_payment_method")
        intento["last_payment_error"] = {"code": "card_declined", "decline_code": "generic_decline",
                                         "message": "Your card was declined."}

        response = self._enviar(*_webhook_firmado("payment_intent.payment_failed", intento))

        self.assertEqual(response.status_code, 200)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.RECHAZADO)
        self.assertEqual(
            Transaccion.objects.get(pk=pago.transaccion_id).estado, EstadoTransaccion.PENDIENTE
        )

    def test_firma_invalida_responde_400_sin_cambios(self):
        pago = self._iniciar_con_tarjeta()
        payload, firma = _webhook_firmado(
            "payment_intent.succeeded", _payment_intent_de(pago), secreto="whsec_falso"
        )

        response = self._enviar(payload, firma)

        self.assertEqual(response.status_code, 400)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)

    def test_sin_firma_responde_400(self):
        payload, _ = _webhook_firmado("payment_intent.succeeded", {"id": "pi_x"})

        response = self._enviar(payload, "")

        self.assertEqual(response.status_code, 400)

    def test_evento_irrelevante_responde_200(self):
        response = self._enviar(*_webhook_firmado("customer.created", {"id": "cus_1", "object": "customer"}))

        self.assertEqual(response.status_code, 200)

    def test_pago_ajeno_al_sistema_responde_200_sin_cambios(self):
        intento = {"id": "pi_trigger", "object": "payment_intent", "status": "succeeded",
                   "amount": 2000, "currency": "usd", "metadata": {}, "last_payment_error": None}

        response = self._enviar(*_webhook_firmado("payment_intent.succeeded", intento))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pago.objects.filter(estado=EstadoPago.CONFIRMADO).exists())

    def test_solo_acepta_post(self):
        response = self.stripe.get(reverse("webhook-stripe"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 405)


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC, STRIPE_SECRET_KEY="sk_test_dummy")
class PagosSimuladosWebTests(ConfirmacionPagoTestMixin, TestCase):
    """Prueba la pantalla en la que analistas y administradores resuelven pagos simulados."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def _como(self, *roles):
        return patch("core.mixins.tiene_rol", side_effect=lambda request, rol: rol in roles)

    def _resolver(self, pago, accion, *roles):
        with self._como(*roles or ("analista_cambiario",)):
            return self.client.post(
                reverse("pago-simulado-resolver", args=[pago.pk]),
                {"accion": accion},
                HTTP_HOST="127.0.0.1",
            )

    def _mensajes(self, response):
        return [str(mensaje) for mensaje in response.wsgi_request._messages]

    def test_analista_ve_los_pagos_simulados_en_proceso(self):
        pendiente = self._iniciar_con_billetera()
        self._iniciar_con_tarjeta()

        with self._como("analista_cambiario"):
            response = self.client.get(reverse("pago-simulado-list"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["pagos"]), [pendiente])
        self.assertContains(response, pendiente.referencia_externa)

    def test_administrador_tambien_accede(self):
        with self._como("administrador"):
            response = self.client.get(reverse("pago-simulado-list"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 200)

    def test_usuario_sin_rol_no_accede(self):
        pago = self._iniciar_con_billetera()

        with self._como():
            listado = self.client.get(reverse("pago-simulado-list"), HTTP_HOST="127.0.0.1")
        respuesta = self._resolver(pago, "aprobar", "usuario")

        self.assertEqual(listado.status_code, 403)
        self.assertEqual(respuesta.status_code, 403)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)

    def test_aprobar_completa_la_operacion(self):
        pago = self._iniciar_con_billetera()

        response = self._resolver(pago, "aprobar")

        self.assertRedirects(response, reverse("pago-simulado-list"), fetch_redirect_response=False)
        self.assertTrue(any("quedó completada" in mensaje for mensaje in self._mensajes(response)))
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.CONFIRMADO)
        self.assertEqual(
            Transaccion.objects.get(pk=pago.transaccion_id).estado, EstadoTransaccion.COMPLETADA
        )

    def test_rechazar_deja_la_operacion_pendiente(self):
        pago = self._iniciar_con_billetera()

        response = self._resolver(pago, "rechazar")

        self.assertTrue(any("sigue pendiente" in mensaje for mensaje in self._mensajes(response)))
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.RECHAZADO)
        self.assertIn(self.user.username, pago.mensaje_proveedor)
        self.assertEqual(
            Transaccion.objects.get(pk=pago.transaccion_id).estado, EstadoTransaccion.PENDIENTE
        )

    def test_resolver_dos_veces_no_tiene_efecto(self):
        pago = self._iniciar_con_billetera()
        self._resolver(pago, "aprobar")

        response = self._resolver(pago, "rechazar")

        self.assertTrue(any("ya había sido resuelto" in mensaje for mensaje in self._mensajes(response)))
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.CONFIRMADO)

    def test_un_pago_de_stripe_no_se_resuelve_desde_el_simulador(self):
        pago = self._iniciar_con_tarjeta()

        response = self._resolver(pago, "aprobar")

        self.assertEqual(response.status_code, 404)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)

    def test_accion_invalida_no_modifica_el_pago(self):
        pago = self._iniciar_con_billetera()

        response = self._resolver(pago, "borrar")

        self.assertTrue(any("Acción no válida" in mensaje for mensaje in self._mensajes(response)))
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)


@override_settings(MIDDLEWARE=MIDDLEWARE_SIN_OIDC, STRIPE_SECRET_KEY="sk_test_dummy")
class DetalleConfirmacionPagoTests(ConfirmacionPagoTestMixin, TestCase):
    """Prueba cómo el detalle de la operación informa la confirmación del pago."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def _detalle(self, transaccion_id):
        with patch("transacciones.views.tiene_rol", return_value=False):
            return self.client.get(
                reverse("transaccion-web-detail", args=[transaccion_id]),
                HTTP_HOST="127.0.0.1",
            )

    def test_con_pago_en_proceso_la_pagina_se_actualiza_sola(self):
        pago = self._iniciar_con_tarjeta()

        response = self._detalle(pago.transaccion_id)

        self.assertContains(response, 'http-equiv="refresh"')

    def test_pago_confirmado_se_muestra_con_su_fecha(self):
        pago = self._iniciar_con_tarjeta(referencia="pi_detalle")
        procesar_resultado_pago(ProveedorPago.STRIPE, _resultado_de(pago))

        response = self._detalle(pago.transaccion_id)

        self.assertEqual(response.context["pago_confirmado"].pk, pago.pk)
        self.assertContains(response, "Pago confirmado por Stripe")
        self.assertContains(response, "pi_detalle")
        self.assertContains(response, "COMPLETADA")
        self.assertNotContains(response, 'http-equiv="refresh"')
        self.assertFalse(response.context["puede_iniciar_pago"])

    def test_pago_simulado_en_proceso_informa_que_espera_la_billetera(self):
        pago = self._iniciar_con_billetera()

        response = self._detalle(pago.transaccion_id)

        self.assertContains(response, "Esperando la aprobación del pago en la billetera")


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class SincronizarPagosComandoTests(ConfirmacionPagoTestMixin, TestCase):
    """Prueba el comando de respaldo que consulta los pagos en Stripe."""

    def _ejecutar(self, *args):
        salida = StringIO()
        call_command("sincronizar_pagos", *args, stdout=salida)
        return salida.getvalue()

    def test_pago_cobrado_en_stripe_se_confirma(self):
        pago = self._iniciar_con_tarjeta()

        with patch(CONSULTAR_PAYMENT_INTENT, return_value=_payment_intent_de(pago)):
            salida = self._ejecutar()

        self.assertIn("Confirmados: 1", salida)
        self.assertEqual(
            Transaccion.objects.get(pk=pago.transaccion_id).estado, EstadoTransaccion.COMPLETADA
        )

    def test_pago_todavia_en_proceso_queda_sin_cambios(self):
        pago = self._iniciar_con_tarjeta()

        with patch(CONSULTAR_PAYMENT_INTENT, return_value=_payment_intent_de(pago, estado="processing")):
            salida = self._ejecutar()

        self.assertIn("Sin cambios: 1", salida)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)

    def test_pago_rechazado_en_stripe_se_registra(self):
        pago = self._iniciar_con_tarjeta()

        with patch(
            CONSULTAR_PAYMENT_INTENT,
            return_value=_payment_intent_de(pago, estado="requires_payment_method"),
        ):
            salida = self._ejecutar()

        self.assertIn("Rechazados: 1", salida)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.RECHAZADO)

    def test_error_de_comunicacion_se_informa_y_no_cambia_el_pago(self):
        pago = self._iniciar_con_tarjeta()

        with patch(CONSULTAR_PAYMENT_INTENT, side_effect=stripe.APIConnectionError("timeout")):
            salida = self._ejecutar()

        self.assertIn("Errores: 1", salida)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.EN_PROCESO)

    def test_no_consulta_pagos_del_simulador_ni_ya_resueltos(self):
        self._iniciar_con_billetera()
        confirmado = self._iniciar_con_tarjeta(referencia="pi_ya_confirmado")
        procesar_resultado_pago(ProveedorPago.STRIPE, _resultado_de(confirmado))

        with patch(CONSULTAR_PAYMENT_INTENT) as consultar:
            salida = self._ejecutar()

        consultar.assert_not_called()
        self.assertIn("Pagos consultados: 0", salida)

    def test_puede_limitarse_a_un_pago(self):
        primero = self._iniciar_con_tarjeta(referencia="pi_primero")
        self._iniciar_con_tarjeta(referencia="pi_segundo")

        with patch(CONSULTAR_PAYMENT_INTENT, return_value=_payment_intent_de(primero)) as consultar:
            salida = self._ejecutar("--id-pago", str(primero.pk))

        self.assertEqual(consultar.call_count, 1)
        self.assertIn("Pagos consultados: 1", salida)
