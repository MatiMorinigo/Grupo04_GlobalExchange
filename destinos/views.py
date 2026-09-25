from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import ClienteActivoRequiredMixin
from cotizaciones.models import Moneda
from usuarios.models import obtener_cliente_activo

from .forms import DestinoAcreditacionForm
from .models import (
    AccionAuditoriaDestino,
    AuditoriaDestinoAcreditacion,
    DestinoAcreditacion,
)


def _datos_auditables(destino):
    """Extrae los campos de un destino que se conservan en la auditoría.

    Args:
        destino (DestinoAcreditacion): Destino del que se toman los datos.

    Returns:
        dict: Representación serializable del destino.
    """
    return {
        "tipo": destino.tipo,
        "alias": destino.alias,
        "titular": destino.titular,
        "documento_titular": destino.documento_titular,
        "moneda": destino.moneda_id,
        "banco": destino.banco,
        "tipo_cuenta": destino.tipo_cuenta,
        "numero_cuenta": destino.numero_cuenta,
        "proveedor_billetera": destino.proveedor_billetera,
        "numero_billetera": destino.numero_billetera,
    }


class DestinoWebListView(ClienteActivoRequiredMixin, ListView):
    """Muestra los destinos de acreditación registrados para el cliente activo."""
    model = DestinoAcreditacion
    template_name = "destinos/destino_list.html"
    context_object_name = "destinos"

    def get_queryset(self):
        """Filtra los destinos del cliente activo según los parámetros GET.

        Sin el parámetro 'estado', o con cualquier valor distinto de 'todos'
        o 'inactivos', se listan solo los destinos activos. El parámetro
        'moneda' acota el listado a una divisa concreta.

        Returns:
            django.db.models.QuerySet: Destinos del cliente activo,
            filtrados según el estado y la moneda solicitados.
        """
        queryset = DestinoAcreditacion.objects.filter(
            cliente=obtener_cliente_activo(self.request.user)
        ).select_related("moneda")

        moneda = self.request.GET.get("moneda", "").strip()
        if moneda:
            queryset = queryset.filter(moneda_id=moneda)

        estado = self.request.GET.get("estado", "").strip()
        if estado == "todos":
            return queryset
        if estado == "inactivos":
            return queryset.filter(activo=False)
        return queryset.filter(activo=True)

    def get_context_data(self, **kwargs):
        """Marca el menú de destinos y expone los filtros aplicados.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto del listado con la selección del menú, los
            filtros activos y las monedas disponibles para filtrar.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "destinos"
        context["estado"] = self.request.GET.get("estado", "").strip()
        context["moneda"] = self.request.GET.get("moneda", "").strip()
        context["monedas"] = Moneda.objects.filter(activa=True).order_by("codigo")
        return context


class DestinoWebCreateView(ClienteActivoRequiredMixin, CreateView):
    """Permite registrar un destino de acreditación para el cliente activo."""
    model = DestinoAcreditacion
    form_class = DestinoAcreditacionForm
    template_name = "destinos/destino_form.html"
    success_url = reverse_lazy("destino-web-list")

    def form_valid(self, form):
        """Asocia el destino al cliente activo y registra la auditoría de creación.

        Args:
            form (DestinoAcreditacionForm): Formulario validado con los
                datos del destino.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            destinos después de guardar el registro.
        """
        form.instance.cliente = obtener_cliente_activo(self.request.user)
        response = super().form_valid(form)
        AuditoriaDestinoAcreditacion.objects.registrar(
            destino=self.object,
            accion=AccionAuditoriaDestino.CREACION,
            realizado_por=self.request.user,
            datos_nuevos=_datos_auditables(self.object),
        )
        messages.success(self.request, "Destino de acreditación registrado correctamente.")
        return response

    def get_context_data(self, **kwargs):
        """Prepara los textos y el menú del formulario de creación.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo, el título y la etiqueta del botón.
        """
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_menu": "destinos",
                "page_title": "Nuevo destino de acreditación",
                "submit_label": "Guardar",
            }
        )
        return context


class DestinoWebUpdateView(ClienteActivoRequiredMixin, UpdateView):
    """Permite editar los datos de un destino de acreditación del cliente activo."""
    model = DestinoAcreditacion
    form_class = DestinoAcreditacionForm
    template_name = "destinos/destino_form.html"
    pk_url_kwarg = "id_destino"
    success_url = reverse_lazy("destino-web-list")

    def get_queryset(self):
        """Restringe la edición a los destinos del cliente activo.

        Returns:
            django.db.models.QuerySet: Destinos pertenecientes al cliente
            activo del usuario.
        """
        return DestinoAcreditacion.objects.filter(
            cliente=obtener_cliente_activo(self.request.user)
        )

    def get_object(self, queryset=None):
        """Obtiene el destino a editar y guarda una copia de sus datos actuales.

        Args:
            queryset (django.db.models.QuerySet or None): Conjunto de
                consulta propuesto por la vista base.

        Returns:
            DestinoAcreditacion: Destino identificado por la URL.
        """
        destino = super().get_object(queryset)
        self._datos_anteriores = _datos_auditables(destino)
        return destino

    def form_valid(self, form):
        """Guarda los cambios del destino y registra la auditoría de modificación.

        Args:
            form (DestinoAcreditacionForm): Formulario validado con los
                nuevos datos.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            destinos después de guardar los cambios.
        """
        response = super().form_valid(form)
        AuditoriaDestinoAcreditacion.objects.registrar(
            destino=self.object,
            accion=AccionAuditoriaDestino.MODIFICACION,
            realizado_por=self.request.user,
            datos_anteriores=self._datos_anteriores,
            datos_nuevos=_datos_auditables(self.object),
        )
        messages.success(self.request, "Destino de acreditación actualizado correctamente.")
        return response

    def get_context_data(self, **kwargs):
        """Prepara los textos y el menú del formulario de edición.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo, el título y la etiqueta del botón.
        """
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_menu": "destinos",
                "page_title": "Editar destino de acreditación",
                "submit_label": "Guardar cambios",
            }
        )
        return context


class DestinoWebDeactivateView(ClienteActivoRequiredMixin, View):
    """Permite desactivar un destino de acreditación del cliente activo."""

    def post(self, request, id_destino):
        """Desactiva el destino y redirige al listado.

        Args:
            request (django.http.HttpRequest): Solicitud utilizada para
                registrar los mensajes y el usuario de la operación.
            id_destino (int): Identificador del destino a desactivar.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de destinos.

        Raises:
            django.http.Http404: Si el destino no existe o no pertenece al
                cliente activo.
        """
        destino = get_object_or_404(
            DestinoAcreditacion,
            id_destino=id_destino,
            cliente=obtener_cliente_activo(request.user),
        )

        if destino.activo:
            destino.activo = False
            destino.save(update_fields=["activo"])
            AuditoriaDestinoAcreditacion.objects.registrar(
                destino=destino,
                accion=AccionAuditoriaDestino.DESACTIVACION,
                realizado_por=request.user,
                datos_anteriores={"activo": True},
                datos_nuevos={"activo": False},
            )
            messages.success(request, "Destino de acreditación desactivado correctamente.")
        else:
            messages.info(request, "El destino de acreditación ya se encontraba desactivado.")

        return redirect("destino-web-list")


class DestinoWebActivateView(ClienteActivoRequiredMixin, View):
    """Permite reactivar un destino de acreditación del cliente activo."""

    def post(self, request, id_destino):
        """Reactiva el destino y redirige al listado.

        Args:
            request (django.http.HttpRequest): Solicitud utilizada para
                registrar los mensajes y el usuario de la operación.
            id_destino (int): Identificador del destino a reactivar.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de destinos.

        Raises:
            django.http.Http404: Si el destino no existe o no pertenece al
                cliente activo.
        """
        destino = get_object_or_404(
            DestinoAcreditacion,
            id_destino=id_destino,
            cliente=obtener_cliente_activo(request.user),
        )

        if not destino.activo:
            destino.activo = True
            destino.save(update_fields=["activo"])
            AuditoriaDestinoAcreditacion.objects.registrar(
                destino=destino,
                accion=AccionAuditoriaDestino.ACTIVACION,
                realizado_por=request.user,
                datos_anteriores={"activo": False},
                datos_nuevos={"activo": True},
            )
            messages.success(request, "Destino de acreditación activado correctamente.")
        else:
            messages.info(request, "El destino de acreditación ya se encontraba activo.")

        return redirect("destino-web-list")


class DestinoWebDeleteView(ClienteActivoRequiredMixin, DeleteView):
    """Permite eliminar definitivamente un destino de acreditación del cliente activo."""
    model = DestinoAcreditacion
    template_name = "destinos/destino_confirm_delete.html"
    pk_url_kwarg = "id_destino"
    context_object_name = "destino"
    success_url = reverse_lazy("destino-web-list")

    def get_queryset(self):
        """Restringe la eliminación a los destinos del cliente activo.

        Returns:
            django.db.models.QuerySet: Destinos pertenecientes al cliente
            activo del usuario.
        """
        return DestinoAcreditacion.objects.filter(
            cliente=obtener_cliente_activo(self.request.user)
        )

    def form_valid(self, form):
        """Registra la auditoría de eliminación antes de borrar el destino.

        El registro se crea antes de eliminar el objeto: la relación usa
        SET_NULL, así que la fila de auditoría sobrevive al borrado y deja
        constancia de qué destino existía.

        Args:
            form (django.forms.Form): Formulario vacío de confirmación.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            destinos después de eliminar el registro.
        """
        datos = _datos_auditables(self.object)
        datos["activo"] = self.object.activo
        AuditoriaDestinoAcreditacion.objects.registrar(
            destino=self.object,
            accion=AccionAuditoriaDestino.ELIMINACION,
            realizado_por=self.request.user,
            datos_anteriores=datos,
        )
        messages.success(self.request, "Destino de acreditación eliminado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """Marca el menú de destinos como activo.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo seleccionado.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "destinos"
        return context
