from functools import cached_property

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import DetailView, FormView, ListView

from core.keycloak import tiene_rol
from core.mixins import ClienteActivoRequiredMixin
from usuarios.models import obtener_cliente_activo

from .forms import CompraDivisaForm, HistorialTransaccionFiltroForm
from .models import Transaccion
from .services import (
    OperacionCambiariaError,
    calcular_compra,
    crear_transaccion_compra,
    obtener_tasa_vigente_compra,
)


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
        """Marca el menú de operaciones como activo.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo seleccionado.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "historial_transacciones"
        return context


class TransaccionComprobanteView(TransaccionWebDetailView):
    """Presenta el comprobante imprimible de una operación del cliente activo.

    Reutiliza el filtrado por cliente activo de la vista de detalle y solo
    cambia la plantilla, pensada para imprimirse o guardarse como PDF desde
    el navegador.
    """
    template_name = "transacciones/comprobante.html"
