import logging
from functools import cached_property

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView

from core.keycloak import tiene_rol
from core.mixins import AnalistaCambiarioRequiredMixin, ClienteActivoRequiredMixin
from integrations.proveedores_pago import (
    ConfirmacionInvalidaError,
    SimuladorBilleteraProveedor,
    StripeProveedor,
)
from pagos.models import MetodoPago
from usuarios.models import obtener_cliente_activo

from .forms import CompraDivisaForm, HistorialTransaccionFiltroForm, VentaDivisaForm
from .models import (
    ESTADOS_PAGO_ACTIVOS,
    EstadoPago,
    EstadoTransaccion,
    Pago,
    ProveedorPago,
    Transaccion,
)
from .services import (
    OperacionCambiariaError,
    PagoNoIniciableError,
    ResultadoProcesamiento,
    calcular_compra,
    calcular_venta,
    crear_transaccion_compra,
    crear_transaccion_venta,
    importe_a_cobrar,
    iniciar_pago,
    metodo_permite_pagar,
    obtener_tasa_vigente_compra,
    obtener_tasa_vigente_venta,
    procesar_resultado_pago,
)


logger = logging.getLogger(__name__)


class CompraDivisaWebCreateView(ClienteActivoRequiredMixin, FormView):
    """Guía la compra de divisas desde los datos de la operación hasta su registro.

    El formulario se resuelve en dos pasos sobre una única vista y una única
    URL, siguiendo el patrón que ya usa la edición de tasas de cambio: el
    primer envío solo calcula y muestra el resumen, y el segundo, marcado con
    el campo oculto ``confirmado``, registra la transacción.

    La operación se persiste recién al confirmar. Antes de hacerlo se verifica
    que la cotización utilizada para armar el resumen siga vigente; si cambió,
    se vuelve a mostrar el resumen recalculado con una advertencia, sin haber
    tocado la base de datos.
    """
    template_name = "transacciones/compra_form.html"
    form_class = CompraDivisaForm

    def get_form_kwargs(self):
        """Entrega al formulario el cliente activo del usuario.

        Returns:
            dict: Argumentos de construcción del formulario.
        """
        kwargs = super().get_form_kwargs()
        kwargs["cliente"] = obtener_cliente_activo(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        """Prepara los textos y el menú de la pantalla de compra.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo, el título y, salvo que se
            indique lo contrario, el modo de edición del formulario.
        """
        context = super().get_context_data(**kwargs)
        context.setdefault("modo_confirmacion", False)
        context.setdefault("advertencia_cotizacion", False)
        context.update(
            {
                "active_menu": "transacciones",
                "page_title": "Comprar divisas",
                "cliente_operando": obtener_cliente_activo(self.request.user),
            }
        )
        return context

    def form_valid(self, form):
        """Muestra el resumen o registra la operación, según el paso del flujo.

        Args:
            form (CompraDivisaForm): Formulario validado con los datos de la
                operación y el estado del paso de confirmación.

        Returns:
            django.http.HttpResponse: El resumen a confirmar, el resumen
            recalculado con una advertencia, o la redirección a la operación
            registrada.
        """
        cliente = obtener_cliente_activo(self.request.user)
        moneda = form.cleaned_data["moneda"]
        monto = form.cleaned_data["monto_divisa"]

        try:
            tasa_vigente = obtener_tasa_vigente_compra(moneda.codigo)
        except OperacionCambiariaError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        confirmado = form.cleaned_data.get("confirmado")
        id_tasa_vista = form.cleaned_data.get("id_tasa_vista")
        cotizacion_cambio = confirmado and id_tasa_vista != tasa_vigente.id_tasa

        if confirmado and not cotizacion_cambio:
            return self._registrar(form, cliente, moneda, monto, tasa_vigente)

        return self._mostrar_resumen(
            form,
            cliente,
            moneda,
            monto,
            tasa_vigente,
            advertencia=bool(cotizacion_cambio),
        )

    def _mostrar_resumen(self, form, cliente, moneda, monto, tasa, advertencia):
        """Calcula los importes y renderiza el resumen pendiente de confirmación.

        Args:
            form (CompraDivisaForm): Formulario ya validado.
            cliente (clientes.models.Cliente): Cliente que opera.
            moneda (cotizaciones.models.Moneda): Divisa a comprar.
            monto (decimal.Decimal): Cantidad de divisa.
            tasa (cotizaciones.models.TasaCambio): Cotización vigente.
            advertencia (bool): True si la cotización cambió mientras el
                cliente revisaba el resumen anterior.

        Returns:
            django.http.HttpResponse: Página del resumen, o el formulario con
            errores si los importes no pudieron calcularse.
        """
        try:
            resumen = calcular_compra(cliente, moneda.codigo, monto, tasa=tasa)
        except OperacionCambiariaError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        if advertencia:
            messages.warning(
                self.request,
                "La cotización cambió mientras revisabas la operación. "
                "Revisá los importes actualizados antes de confirmar.",
            )

        return self.render_to_response(
            self.get_context_data(
                form=form,
                modo_confirmacion=True,
                advertencia_cotizacion=advertencia,
                resumen=resumen,
                categoria_label=cliente.get_categoria_display(),
                tasa_vigente=tasa,
                destino=form.cleaned_data.get("destino_acreditacion"),
                metodo_pago=form.cleaned_data.get("metodo_pago"),
            )
        )

    def _registrar(self, form, cliente, moneda, monto, tasa):
        """Registra la transacción pendiente y redirige a su resumen.

        Args:
            form (CompraDivisaForm): Formulario ya validado.
            cliente (clientes.models.Cliente): Cliente que opera.
            moneda (cotizaciones.models.Moneda): Divisa a comprar.
            monto (decimal.Decimal): Cantidad de divisa.
            tasa (cotizaciones.models.TasaCambio): Cotización confirmada.

        Returns:
            django.http.HttpResponse: Redirección a la operación registrada,
            o el formulario con errores si no pudo crearse.
        """
        try:
            transaccion = crear_transaccion_compra(
                cliente=cliente,
                usuario=self.request.user,
                moneda_codigo=moneda.codigo,
                monto_divisa=monto,
                destino=form.cleaned_data.get("destino_acreditacion"),
                metodo_pago=form.cleaned_data.get("metodo_pago"),
                tasa=tasa,
            )
        except OperacionCambiariaError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Compra registrada con el número {transaccion.id_transaccion}.",
        )
        return redirect("transaccion-web-detail", id_transaccion=transaccion.id_transaccion)



class VentaDivisaWebCreateView(ClienteActivoRequiredMixin, FormView):
    """Guía la venta de divisas desde los datos de la operación hasta su registro.

    El cliente entrega moneda extranjera y recibe guaraníes. El formulario se
    resuelve en dos pasos sobre una única vista y una única URL, siguiendo el
    mismo patrón que la compra de divisas: el primer envío calcula y muestra el
    resumen, y el segundo, marcado con el campo oculto ``confirmado``, registra
    la transacción.

    La operación se persiste recién al confirmar. Antes de hacerlo se verifica
    que la cotización utilizada para armar el resumen siga vigente; si cambió,
    se vuelve a mostrar el resumen recalculado con una advertencia, sin haber
    tocado la base de datos.
    """

    template_name = "transacciones/venta_form.html"
    form_class = VentaDivisaForm

    def get_form_kwargs(self):
        """Entrega al formulario el cliente activo del usuario.

        Returns:
            dict: Argumentos de construcción del formulario.
        """
        kwargs = super().get_form_kwargs()
        kwargs["cliente"] = obtener_cliente_activo(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        """Prepara los textos y el menú de la pantalla de venta.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo, el título y, salvo que se
            indique lo contrario, el modo de edición del formulario.
        """
        context = super().get_context_data(**kwargs)
        context.setdefault("modo_confirmacion", False)
        context.setdefault("advertencia_cotizacion", False)
        context.update(
            {
                "active_menu": "venta",
                "page_title": "Vender divisas",
                "cliente_operando": obtener_cliente_activo(self.request.user),
            }
        )
        return context

    def form_valid(self, form):
        """Muestra el resumen o registra la operación, según el paso del flujo.

        Args:
            form (VentaDivisaForm): Formulario validado con los datos de la
                operación y el estado del paso de confirmación.

        Returns:
            django.http.HttpResponse: El resumen a confirmar, el resumen
            recalculado con una advertencia, o la redirección a la operación
            registrada.
        """
        cliente = obtener_cliente_activo(self.request.user)
        moneda = form.cleaned_data["moneda"]
        monto = form.cleaned_data["monto_divisa"]

        try:
            tasa_vigente = obtener_tasa_vigente_venta(moneda.codigo)
        except OperacionCambiariaError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        confirmado = form.cleaned_data.get("confirmado")
        id_tasa_vista = form.cleaned_data.get("id_tasa_vista")
        cotizacion_cambio = confirmado and id_tasa_vista != tasa_vigente.id_tasa

        if confirmado and not cotizacion_cambio:
            return self._registrar(form, cliente, moneda, monto, tasa_vigente)

        return self._mostrar_resumen(
            form,
            cliente,
            moneda,
            monto,
            tasa_vigente,
            advertencia=bool(cotizacion_cambio),
        )

    def _mostrar_resumen(self, form, cliente, moneda, monto, tasa, advertencia):
        """Calcula los importes y renderiza el resumen pendiente de confirmación.

        Args:
            form (VentaDivisaForm): Formulario ya validado.
            cliente (clientes.models.Cliente): Cliente que opera.
            moneda (cotizaciones.models.Moneda): Divisa a vender.
            monto (decimal.Decimal): Cantidad de divisa.
            tasa (cotizaciones.models.TasaCambio): Cotización vigente.
            advertencia (bool): True si la cotización cambió mientras el
                cliente revisaba el resumen anterior.

        Returns:
            django.http.HttpResponse: Página del resumen, o el formulario con
            errores si los importes no pudieron calcularse.
        """
        try:
            resumen = calcular_venta(cliente, moneda.codigo, monto, tasa=tasa)
        except OperacionCambiariaError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        if advertencia:
            messages.warning(
                self.request,
                "La cotización cambió mientras revisabas la operación. "
                "Revisá los importes actualizados antes de confirmar.",
            )

        return self.render_to_response(
            self.get_context_data(
                form=form,
                modo_confirmacion=True,
                advertencia_cotizacion=advertencia,
                resumen=resumen,
                categoria_label=cliente.get_categoria_display(),
                tasa_vigente=tasa,
                destino=form.cleaned_data.get("destino_acreditacion"),
                metodo_pago=form.cleaned_data.get("metodo_pago"),
            )
        )

    def _registrar(self, form, cliente, moneda, monto, tasa):
        """Registra la transacción pendiente y redirige a su resumen.

        Args:
            form (VentaDivisaForm): Formulario ya validado.
            cliente (clientes.models.Cliente): Cliente que opera.
            moneda (cotizaciones.models.Moneda): Divisa a vender.
            monto (decimal.Decimal): Cantidad de divisa.
            tasa (cotizaciones.models.TasaCambio): Cotización confirmada.

        Returns:
            django.http.HttpResponse: Redirección a la operación registrada,
            o el formulario con errores si no pudo crearse.
        """
        try:
            transaccion = crear_transaccion_venta(
                cliente=cliente,
                usuario=self.request.user,
                moneda_codigo=moneda.codigo,
                monto_divisa=monto,
                destino=form.cleaned_data.get("destino_acreditacion"),
                metodo_pago=form.cleaned_data.get("metodo_pago"),
                tasa=tasa,
            )
        except OperacionCambiariaError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Venta registrada con el número {transaccion.id_transaccion}.",
        )
        return redirect("transaccion-web-detail", id_transaccion=transaccion.id_transaccion)


class AccesoHistorialTransaccionMixin(LoginRequiredMixin):
    """Aplica el alcance general o por cliente activo a las consultas."""

    @cached_property
    def historial_general(self):
        """Indica si el usuario puede consultar operaciones de todo el sistema."""

        return tiene_rol(self.request, "administrador") or tiene_rol(
            self.request, "analista_cambiario"
        )

    @cached_property
    def cliente_activo(self):
        """Obtiene una sola vez el cliente seleccionado por el usuario."""

        return obtener_cliente_activo(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        """Bloquea al usuario común que no tenga un cliente activo."""

        if (
            request.user.is_authenticated
            and not self.historial_general
            and self.cliente_activo is None
        ):
            messages.info(
                request,
                "Necesitás tener un cliente activo para consultar el historial.",
            )
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """Devuelve todas las transacciones o solamente las del cliente activo."""

        queryset = Transaccion.objects.select_related(
            "cliente",
            "moneda",
            "tasa_cambio",
            "destino_acreditacion",
            "metodo_pago",
            "creada_por",
        )
        if self.historial_general:
            return queryset
        return queryset.filter(cliente=self.cliente_activo)


class TransaccionHistorialView(AccesoHistorialTransaccionMixin, ListView):
    """Lista las transacciones autorizadas y permite filtrarlas sin modificarlas."""

    model = Transaccion
    template_name = "transacciones/historial.html"
    context_object_name = "transacciones"
    paginate_by = 20

    def get_filtro(self):
        """Construye y conserva el formulario utilizado por la consulta."""

        if not hasattr(self, "_filtro"):
            self._filtro = HistorialTransaccionFiltroForm(
                self.request.GET or None,
                mostrar_cliente=self.historial_general,
            )
        return self._filtro

    def get_queryset(self):
        """Aplica al alcance autorizado los filtros válidos recibidos por GET."""

        queryset = super().get_queryset().order_by("-creada_en")
        filtro = self.get_filtro()
        if not filtro.is_valid():
            return queryset

        datos = filtro.cleaned_data
        if self.historial_general and datos.get("cliente"):
            queryset = queryset.filter(cliente=datos["cliente"])
        if datos.get("fecha_desde"):
            queryset = queryset.filter(creada_en__date__gte=datos["fecha_desde"])
        if datos.get("fecha_hasta"):
            queryset = queryset.filter(creada_en__date__lte=datos["fecha_hasta"])
        if datos.get("tipo_operacion"):
            queryset = queryset.filter(tipo_operacion=datos["tipo_operacion"])
        if datos.get("estado"):
            queryset = queryset.filter(estado=datos["estado"])
        return queryset

    def get_context_data(self, **kwargs):
        """Agrega el formulario, el alcance y los parámetros de paginación."""

        context = super().get_context_data(**kwargs)
        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        context.update(
            {
                "active_menu": "historial_transacciones",
                "filtro": self.get_filtro(),
                "historial_general": self.historial_general,
                "parametros_filtro": parametros.urlencode(),
            }
        )
        return context


class TransaccionWebDetailView(AccesoHistorialTransaccionMixin, DetailView):
    """Muestra una transaccion si pertenece al alcance autorizado."""
    model = Transaccion
    template_name = "transacciones/transaccion_detail.html"
    context_object_name = "transaccion"
    pk_url_kwarg = "id_transaccion"

    def get_queryset(self):
        """Reutiliza el alcance seguro definido para el historial."""

        return super().get_queryset()

    def get_context_data(self, **kwargs):
        """Agrega el menú activo y los datos de pago de la transacción.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo según el tipo de operación
            ('transacciones' para compras y 'venta' para ventas), los pagos
            registrados, el pago en curso si existe, el importe a pagar, si
            el usuario puede iniciar el pago y, tras un intento fallido o si
            el método actual no permite pagar, los métodos entre los que
            puede elegir.
        """
        context = super().get_context_data(**kwargs)
        transaccion = context["transaccion"]
        context["active_menu"] = (
            "venta"
            if transaccion.tipo_operacion == "VENTA"
            else "transacciones"
        )

        pagos = list(transaccion.pagos.select_related("moneda", "metodo_pago"))
        pago_activo = next((pago for pago in pagos if pago.estado in ESTADOS_PAGO_ACTIVOS), None)
        pago_confirmado = next(
            (pago for pago in pagos if pago.estado == EstadoPago.CONFIRMADO), None
        )
        monto_pago, moneda_pago = importe_a_cobrar(transaccion)
        es_cliente_de_la_operacion = (
            self.cliente_activo is not None
            and self.cliente_activo.pk == transaccion.cliente_id
        )
        puede_iniciar_pago = (
            transaccion.estado == EstadoTransaccion.PENDIENTE
            and pago_activo is None
            and es_cliente_de_la_operacion
        )
        # Se ofrece pagar con otro método cuando el intento anterior falló o
        # cuando el método actual ni siquiera permite iniciar el pago.
        hubo_intento_fallido = any(
            pago.estado in (EstadoPago.RECHAZADO, EstadoPago.ERROR) for pago in pagos
        )
        metodos_disponibles = []
        if puede_iniciar_pago and (
            hubo_intento_fallido or not metodo_permite_pagar(transaccion)
        ):
            metodos_disponibles = list(
                MetodoPago.objects.filter(cliente=self.cliente_activo, activo=True)
            )
        context.update(
            {
                "pagos": pagos,
                "pago_activo": pago_activo,
                "pago_confirmado": pago_confirmado,
                "monto_pago": monto_pago,
                "moneda_pago": moneda_pago,
                "puede_iniciar_pago": puede_iniciar_pago,
                "puede_cambiar_metodo": len(metodos_disponibles) > 1,
                "metodos_disponibles": metodos_disponibles,
            }
        )
        return context


class TransaccionComprobanteView(TransaccionWebDetailView):
    """Presenta el comprobante imprimible de una operación del cliente activo.

    Reutiliza el filtrado por cliente activo de la vista de detalle y solo
    cambia la plantilla, pensada para imprimirse o guardarse como PDF desde
    el navegador.
    """
    template_name = "transacciones/comprobante.html"


class TransaccionIniciarPagoView(ClienteActivoRequiredMixin, View):
    """Inicia el pago de una operación pendiente del cliente activo.

    Solo acepta POST. La transacción se busca dentro del cliente activo del
    usuario, por lo que nadie puede pagar operaciones de otro cliente, ni
    siquiera quienes pueden consultarlas en el historial general. El formulario
    puede incluir ``metodo_pago`` para pagar con otro método activo del
    cliente, por ejemplo después de un rechazo.
    """

    http_method_names = ["post"]

    def post(self, request, id_transaccion):
        """Solicita el pago al proveedor e informa el resultado.

        Args:
            request (django.http.HttpRequest): Solicitud del cliente.
            id_transaccion (int): Identificador de la operación a pagar.

        Returns:
            django.http.HttpResponse: Redirección al detalle de la operación,
            con un mensaje de éxito o con el motivo por el que no se pudo
            iniciar el pago.
        """
        cliente = obtener_cliente_activo(request.user)
        transaccion = get_object_or_404(
            Transaccion,
            id_transaccion=id_transaccion,
            cliente=cliente,
        )

        metodo_pago = None
        id_metodo = request.POST.get("metodo_pago", "").strip()
        if id_metodo:
            if id_metodo.isdigit():
                metodo_pago = MetodoPago.objects.filter(
                    pk=int(id_metodo), cliente=cliente, activo=True
                ).first()
            if metodo_pago is None:
                messages.error(
                    request,
                    "No se pudo iniciar el pago. El método de pago seleccionado no está disponible.",
                )
                return redirect("transaccion-web-detail", id_transaccion=id_transaccion)

        try:
            pago = iniciar_pago(transaccion, request.user, metodo_pago=metodo_pago)
        except PagoNoIniciableError as error:
            messages.error(request, f"No se pudo iniciar el pago. {error}")
        else:
            messages.success(
                request,
                f"Pago iniciado con {pago.get_proveedor_display()}. "
                f"Referencia: {pago.referencia_externa}. La operación se completará "
                "cuando el proveedor confirme el pago.",
            )
        return redirect("transaccion-web-detail", id_transaccion=id_transaccion)


@csrf_exempt
@require_POST
def webhook_stripe(request):
    """Recibe las notificaciones de Stripe sobre el resultado de los pagos.

    Stripe no envía token CSRF ni sesión: la autenticidad se comprueba con
    la firma del encabezado ``Stripe-Signature``. Una notificación con firma
    inválida responde 400 y no modifica nada. Las válidas responden 200 aun
    cuando no cambian ningún pago (evento ajeno, repetido o con datos que
    no coinciden), para que Stripe no las reintente.

    Args:
        request (django.http.HttpRequest): Solicitud enviada por Stripe.

    Returns:
        django.http.HttpResponse: Respuesta vacía con el código de estado.
    """
    try:
        resultado = StripeProveedor().interpretar_evento(
            request.body,
            request.META.get("HTTP_STRIPE_SIGNATURE", ""),
        )
    except ConfirmacionInvalidaError as error:
        logger.warning("Webhook de Stripe rechazado: %s", error)
        return HttpResponse(status=400)

    if resultado is None:
        return HttpResponse(status=200)

    procesamiento = procesar_resultado_pago(ProveedorPago.STRIPE, resultado)
    logger.info(
        "Webhook de Stripe para %s procesado: %s.",
        resultado.referencia_externa,
        procesamiento,
    )
    return HttpResponse(status=200)


class PagoSimuladoListView(LoginRequiredMixin, AnalistaCambiarioRequiredMixin, ListView):
    """Lista los pagos con billetera simulada que esperan aprobación o rechazo.

    Solo pueden verla analistas cambiarios y administradores, que hacen las
    veces de la billetera del cliente.
    """

    model = Pago
    template_name = "transacciones/pagos_simulados.html"
    context_object_name = "pagos"

    def get_queryset(self):
        """Devuelve los pagos simulados en proceso, del más antiguo al más reciente."""

        return (
            Pago.objects.filter(
                proveedor=ProveedorPago.SIMULADOR_BILLETERA,
                estado=EstadoPago.EN_PROCESO,
            )
            .select_related("transaccion__cliente", "metodo_pago", "moneda")
            .order_by("creado_en")
        )

    def get_context_data(self, **kwargs):
        """Marca la entrada del menú de pagos simulados como activa."""

        context = super().get_context_data(**kwargs)
        context["active_menu"] = "pagos_simulados"
        return context


class PagoSimuladoResolverView(LoginRequiredMixin, AnalistaCambiarioRequiredMixin, View):
    """Aprueba o rechaza un pago de la billetera simulada.

    La respuesta se aplica con ``procesar_resultado_pago``, la misma función
    que procesa los webhooks de Stripe, por lo que resolver dos veces el
    mismo pago no tiene efecto.
    """

    http_method_names = ["post"]

    def post(self, request, id_pago):
        """Aplica la decisión indicada en el formulario y vuelve al listado.

        Args:
            request (django.http.HttpRequest): Solicitud con el campo
                ``accion`` (``aprobar`` o ``rechazar``).
            id_pago (int): Pago del simulador a resolver.

        Returns:
            django.http.HttpResponse: Redirección al listado con el resultado.
        """
        pago = get_object_or_404(
            Pago, pk=id_pago, proveedor=ProveedorPago.SIMULADOR_BILLETERA
        )
        accion = request.POST.get("accion")
        if accion not in ("aprobar", "rechazar"):
            messages.error(request, "Acción no válida para el pago simulado.")
            return redirect("pago-simulado-list")

        resultado = SimuladorBilleteraProveedor().resultado_simulado(
            pago, aprobado=accion == "aprobar", usuario=request.user
        )
        procesamiento = procesar_resultado_pago(ProveedorPago.SIMULADOR_BILLETERA, resultado)
        operacion = pago.transaccion_id

        if procesamiento == ResultadoProcesamiento.CONFIRMADO:
            messages.success(
                request, f"Pago {pago.referencia_externa} aprobado. La operación {operacion} quedó completada."
            )
        elif procesamiento == ResultadoProcesamiento.RECHAZADO:
            messages.warning(
                request, f"Pago {pago.referencia_externa} rechazado. La operación {operacion} sigue pendiente."
            )
        elif procesamiento == ResultadoProcesamiento.DUPLICADO:
            messages.info(request, f"El pago {pago.referencia_externa} ya había sido resuelto.")
        else:
            messages.error(request, f"No se pudo procesar el pago {pago.referencia_externa}.")
        return redirect("pago-simulado-list")
