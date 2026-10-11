
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView

from core.mixins import AdminRequiredMixin
from .models import Sucursal
from .forms import SucursalForm

from .models import Caja
from .forms import CajaForm
from .mixins import AdminOTesoreroRequiredMixin

class SucursalListView(AdminRequiredMixin, ListView):
    """Muestra las sucursales registradas."""

    model = Sucursal
    template_name = "cajas/sucursal_list.html"
    context_object_name = "sucursales"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        return context


class SucursalCreateView(AdminRequiredMixin, CreateView):
    """Permite al administrador registrar sucursales."""

    model = Sucursal
    form_class = SucursalForm
    template_name = "cajas/sucursal_form.html"
    success_url = reverse_lazy("sucursal-list")

    def form_valid(self, form):
        messages.success(
            self.request,
            "Sucursal registrada correctamente."
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        context["page_title"] = "Nueva sucursal"
        context["submit_label"] = "Guardar sucursal"
        return context


class SucursalUpdateView(AdminRequiredMixin, UpdateView):
    """Permite al administrador modificar sucursales."""

    model = Sucursal
    form_class = SucursalForm
    template_name = "cajas/sucursal_form.html"
    pk_url_kwarg = "id_sucursal"
    success_url = reverse_lazy("sucursal-list")

    def form_valid(self, form):
        messages.success(
            self.request,
            "Sucursal actualizada correctamente."
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        context["page_title"] = "Editar sucursal"
        context["submit_label"] = "Guardar cambios"
        return context


class SucursalDeactivateView(AdminRequiredMixin, View):
    """Deshabilita una sucursal sin eliminarla."""

    def post(self, request, id_sucursal):
        sucursal = get_object_or_404(
            Sucursal,
            id_sucursal=id_sucursal
        )

        if not sucursal.activa:
            messages.info(
                request,
                "La sucursal ya se encontraba deshabilitada."
            )
            return redirect("sucursal-list")

        if sucursal.cajas.filter(activa=True).exists():
            messages.error(
                request,
                "No se puede deshabilitar una sucursal "
                "que tenga cajas activas."
            )
            return redirect("sucursal-list")

        sucursal.activa = False
        sucursal.save(update_fields=["activa"])

        messages.success(
            request,
            "Sucursal deshabilitada correctamente."
        )

        return redirect("sucursal-list")


class CajaListView(AdminOTesoreroRequiredMixin, ListView):
    """Muestra las cajas registradas y sus sucursales."""

    model = Caja
    template_name = "cajas/caja_list.html"
    context_object_name = "cajas"

    def get_queryset(self):
        return Caja.objects.select_related("sucursal").order_by(
            "sucursal__codigo", "codigo"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        return context


class CajaCreateView(AdminOTesoreroRequiredMixin, CreateView):
    """Permite registrar cajas en sucursales activas."""

    model = Caja
    form_class = CajaForm
    template_name = "cajas/caja_form.html"
    success_url = reverse_lazy("caja-list")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["sucursal"].queryset = Sucursal.objects.filter(
            activa=True
        )
        return form

    def form_valid(self, form):
        messages.success(
            self.request,
            "Caja registrada correctamente."
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        context["page_title"] = "Nueva caja"
        context["submit_label"] = "Guardar caja"
        return context

class CajaUpdateView(AdminOTesoreroRequiredMixin, UpdateView):
    """Permite modificar los datos de una caja."""

    model = Caja
    form_class = CajaForm
    template_name = "cajas/caja_form.html"
    pk_url_kwarg = "id_caja"
    success_url = reverse_lazy("caja-list")

    def form_valid(self, form):
        messages.success(
            self.request,
            "Caja actualizada correctamente."
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        context["page_title"] = "Editar caja"
        context["submit_label"] = "Guardar cambios"
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["sucursal"].queryset = Sucursal.objects.filter(
            activa=True
        )
        return form

class CajaEstadoView(AdminOTesoreroRequiredMixin, View):
    """Permite habilitar o deshabilitar una caja."""

    def post(self, request, id_caja, activar):
        caja = get_object_or_404(Caja, id_caja=id_caja)

        if activar and not caja.sucursal.activa:
            messages.error(
                request,
                "No se puede habilitar una caja de una sucursal inactiva."
            )
            return redirect("caja-list")

        caja.activa = activar
        caja.save(update_fields=["activa"])

        mensaje = (
            "Caja habilitada correctamente."
            if activar
            else "Caja deshabilitada correctamente."
        )
        messages.success(request, mensaje)

        return redirect("caja-list")