from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, FormView

from core.mixins import ClienteActivoRequiredMixin
from usuarios.models import obtener_cliente_activo

from .forms import CancelarTransaccionForm, CompraDivisaForm
from .models import EstadoTransaccion, Transaccion
from .services import (
    OperacionCambiariaError,
    calcular_compra,
    cancelar_transaccion,
    crear_transaccion_compra,
    obtener_cotizacion_actualizada,
    recalcular_con_nueva_tasa,
)


class CompraDivisaWebCreateView(ClienteActivoRequiredMixin, FormView):
    """Permite al cliente activo iniciar una compra de divisas."""
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

    def form_valid(self, form):
        """Registra la compra en estado pendiente y redirige a su detalle.

        Args:
            form (CompraDivisaForm): Formulario validado con la moneda, el
                monto y el destino de acreditación.

        Returns:
            django.http.HttpResponse: Redirección al detalle de la
            transacción creada, o el formulario con errores si la operación
            no pudo calcularse.
        """
        cliente = obtener_cliente_activo(self.request.user)

        try:
            transaccion = crear_transaccion_compra(
                cliente=cliente,
                usuario=self.request.user,
                moneda_codigo=form.cleaned_data["moneda"].codigo,
                monto_divisa=form.cleaned_data["monto_divisa"],
                destino=form.cleaned_data.get("destino_acreditacion"),
            )
        except OperacionCambiariaError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Operación {transaccion.id_transaccion} registrada. "
            "Revisá el detalle antes de continuar al pago.",
        )
        return redirect("transaccion-web-detail", id_transaccion=transaccion.id_transaccion)

    def get_context_data(self, **kwargs):
        """Prepara los textos y el menú del formulario de compra.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo y el título de la página.
        """
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_menu": "transacciones",
                "page_title": "Comprar divisas",
            }
        )
        return context


class TransaccionWebDetailView(ClienteActivoRequiredMixin, DetailView):
    """Muestra el desglose completo de una operación del cliente activo."""
    model = Transaccion
    template_name = "transacciones/transaccion_detail.html"
    context_object_name = "transaccion"
    pk_url_kwarg = "id_transaccion"

    def get_queryset(self):
        """Restringe la consulta a las transacciones del cliente activo.

        Returns:
            django.db.models.QuerySet: Transacciones pertenecientes al
            cliente activo del usuario.
        """
        return Transaccion.objects.filter(
            cliente=obtener_cliente_activo(self.request.user)
        ).select_related("moneda", "tasa_cambio", "destino_acreditacion")

    def get_context_data(self, **kwargs):
        """Marca el menú de operaciones como activo.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo seleccionado.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "transacciones"
        return context


class TransaccionRevalidarCotizacionView(ClienteActivoRequiredMixin, View):
    """Verifica que la cotización de una operación pendiente siga vigente."""

    def post(self, request, id_transaccion):
        """Compara la cotización registrada con la vigente antes del pago.

        Si la cotización no cambió, la operación puede continuar hacia el
        proceso de pago. Si cambió, se muestran la nueva tasa y los importes
        recalculados sin persistirlos, para que el cliente decida si acepta
        la nueva cotización o cancela la operación.

        Args:
            request (django.http.HttpRequest): Solicitud actual.
            id_transaccion (int): Identificador de la transacción.

        Returns:
            django.http.HttpResponse: Redirección al detalle si la
            cotización sigue vigente, o la pantalla de recotización.

        Raises:
            django.http.Http404: Si la transacción no existe o no pertenece
                al cliente activo.
        """
        transaccion = get_object_or_404(
            Transaccion,
            id_transaccion=id_transaccion,
            cliente=obtener_cliente_activo(request.user),
        )

        if transaccion.estado != EstadoTransaccion.PENDIENTE:
            messages.info(request, "La operación ya no está pendiente.")
            return redirect("transaccion-web-detail", id_transaccion=id_transaccion)

        try:
            tasa_nueva = obtener_cotizacion_actualizada(transaccion)
        except OperacionCambiariaError as error:
            messages.error(request, str(error))
            return redirect("transaccion-web-detail", id_transaccion=id_transaccion)

        if tasa_nueva is None:
            messages.success(
                request,
                "La cotización utilizada sigue vigente. Podés continuar con el pago.",
            )
            return redirect("transaccion-web-detail", id_transaccion=id_transaccion)

        try:
            recalculo = calcular_compra(
                transaccion.cliente,
                transaccion.moneda_id,
                transaccion.monto_divisa,
                tasa=tasa_nueva,
            )
        except OperacionCambiariaError as error:
            messages.error(request, str(error))
            return redirect("transaccion-web-detail", id_transaccion=id_transaccion)

        return render(
            request,
            "transacciones/transaccion_recotizacion.html",
            {
                "active_menu": "transacciones",
                "transaccion": transaccion,
                "tasa_nueva": tasa_nueva,
                "recalculo": recalculo,
            },
        )


class TransaccionAceptarNuevaTasaView(ClienteActivoRequiredMixin, View):
    """Aplica la cotización vigente sobre una operación pendiente."""

    def post(self, request, id_transaccion):
        """Recalcula la operación con la nueva cotización y vuelve al detalle.

        Args:
            request (django.http.HttpRequest): Solicitud actual.
            id_transaccion (int): Identificador de la transacción.

        Returns:
            django.http.HttpResponseRedirect: Redirección al detalle de la
            operación recalculada.

        Raises:
            django.http.Http404: Si la transacción no existe o no pertenece
                al cliente activo.
        """
        transaccion = get_object_or_404(
            Transaccion,
            id_transaccion=id_transaccion,
            cliente=obtener_cliente_activo(request.user),
        )

        try:
            recalcular_con_nueva_tasa(transaccion)
        except OperacionCambiariaError as error:
            messages.error(request, str(error))
            return redirect("transaccion-web-detail", id_transaccion=id_transaccion)

        messages.success(
            request,
            "La operación fue recalculada con la nueva cotización. "
            "Podés continuar con el pago.",
        )
        return redirect("transaccion-web-detail", id_transaccion=id_transaccion)


class TransaccionCancelarView(ClienteActivoRequiredMixin, View):
    """Permite cancelar una operación pendiente antes de confirmar el pago."""

    def get(self, request, id_transaccion):
        """Muestra la confirmación de cancelación de la operación.

        Args:
            request (django.http.HttpRequest): Solicitud actual.
            id_transaccion (int): Identificador de la transacción.

        Returns:
            django.http.HttpResponse: Página de confirmación.

        Raises:
            django.http.Http404: Si la transacción no existe o no pertenece
                al cliente activo.
        """
        transaccion = get_object_or_404(
            Transaccion,
            id_transaccion=id_transaccion,
            cliente=obtener_cliente_activo(request.user),
        )

        return render(
            request,
            "transacciones/transaccion_confirm_cancel.html",
            {
                "active_menu": "transacciones",
                "transaccion": transaccion,
                "form": CancelarTransaccionForm(),
            },
        )

    def post(self, request, id_transaccion):
        """Cancela la operación pendiente y vuelve a su detalle.

        Args:
            request (django.http.HttpRequest): Solicitud actual.
            id_transaccion (int): Identificador de la transacción.

        Returns:
            django.http.HttpResponseRedirect: Redirección al detalle de la
            operación cancelada.

        Raises:
            django.http.Http404: Si la transacción no existe o no pertenece
                al cliente activo.
        """
        transaccion = get_object_or_404(
            Transaccion,
            id_transaccion=id_transaccion,
            cliente=obtener_cliente_activo(request.user),
        )

        form = CancelarTransaccionForm(request.POST)
        motivo = form.cleaned_data["motivo_cancelacion"] if form.is_valid() else ""

        try:
            cancelar_transaccion(transaccion, motivo=motivo)
        except OperacionCambiariaError as error:
            messages.error(request, str(error))
            return redirect("transaccion-web-detail", id_transaccion=id_transaccion)

        messages.success(
            request,
            "La operación fue cancelada y queda registrada en tu historial.",
        )
        return redirect("transaccion-web-detail", id_transaccion=id_transaccion)
