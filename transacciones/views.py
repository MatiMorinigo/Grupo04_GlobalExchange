from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import DetailView, FormView

from core.mixins import ClienteActivoRequiredMixin
from usuarios.models import obtener_cliente_activo

from .forms import CompraDivisaForm
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


class TransaccionWebDetailView(ClienteActivoRequiredMixin, DetailView):
    """Muestra el resumen de una operación ya registrada por el cliente activo."""
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
        ).select_related("moneda", "tasa_cambio", "destino_acreditacion", "metodo_pago")

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


class TransaccionComprobanteView(TransaccionWebDetailView):
    """Presenta el comprobante imprimible de una operación del cliente activo.

    Reutiliza el filtrado por cliente activo de la vista de detalle y solo
    cambia la plantilla, pensada para imprimirse o guardarse como PDF desde
    el navegador.
    """
    template_name = "transacciones/comprobante.html"
