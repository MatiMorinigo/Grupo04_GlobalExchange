
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

from .models import AsignacionCaja
from .forms import AsignacionCajaForm

from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery
from django.core.exceptions import ValidationError
from django.views.generic import TemplateView, DetailView
from .mixins import CajeroRequiredMixin
from .forms import InventarioInicialFormSet, DenominacionBilleteForm
from .models import AperturaCaja, DenominacionBillete
from .services import abrir_caja, asignaciones_vigentes


class SucursalListView(AdminRequiredMixin, ListView):
    """Muestra las sucursales registradas."""

    model = Sucursal
    template_name = "cajas/sucursal_list.html"
    context_object_name = "sucursales"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        context["active_submenu"] = "sucursales"
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
        context["active_submenu"] = "sucursales"
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
        context["active_submenu"] = "sucursales"
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
        context["active_submenu"] = "cajas"
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
        context["active_submenu"] = "cajas"
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
        context["active_submenu"] = "cajas"
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


class AsignacionCajaListView(AdminOTesoreroRequiredMixin, ListView):
    model = AsignacionCaja
    template_name = "cajas/asignacion_list.html"
    context_object_name = "asignaciones"

    def get_queryset(self):
        return AsignacionCaja.objects.select_related(
            "caja__sucursal",
            "asignado_por"
        ).order_by("-fecha_inicio")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        context["active_submenu"] = "asignaciones"
        return context


class AsignacionCajaCreateView(AdminOTesoreroRequiredMixin, CreateView):
    model = AsignacionCaja
    form_class = AsignacionCajaForm
    template_name = "cajas/asignacion_form.html"
    success_url = reverse_lazy("asignacion-list")


    def form_valid(self, form):
        form.instance.asignado_por = self.request.user

        form.instance.cajero_username = (
            form.cajero_verificado["username"]
        )

        try:
            with transaction.atomic():
                respuesta = super().form_valid(form)

        except IntegrityError as error:
            restriccion = getattr(
                getattr(error.__cause__, "diag", None),
                "constraint_name",
                None
            )

            if restriccion not in {
                "no_superposicion_por_caja",
                "no_superposicion_por_cajero",
            }:
                raise

            form.add_error(
                None,
                "No se pudo registrar la asignación porque "
                "el cajero o la caja ya tienen un turno "
                "superpuesto."
            )

            return self.form_invalid(form)

        messages.success(
            self.request,
            "Cajero asignado correctamente."
        )

        return respuesta


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cajas"
        context["active_submenu"] = "asignaciones"
        context["page_title"] = "Nueva asignación de cajero"
        return context


class DenominacionContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(active_menu="cajas", active_submenu="denominaciones")
        return context


class DenominacionBilleteListView(
    AdminOTesoreroRequiredMixin, DenominacionContextMixin, ListView
):
    model = DenominacionBillete
    template_name = "cajas/denominacion_list.html"
    context_object_name = "denominaciones"

    def get_queryset(self):
        return DenominacionBillete.objects.select_related("moneda").order_by("moneda_id", "valor")


class DenominacionFormMixin(DenominacionContextMixin):
    model = DenominacionBillete
    form_class = DenominacionBilleteForm
    template_name = "cajas/denominacion_form.html"
    success_url = reverse_lazy("denominacion-list")

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = form.save(commit=False)
                # Editar moneda/valor no debe sobrescribir un cambio de estado concurrente.
                campos = ["moneda", "valor"] if self.object.pk else None
                self.object.save(update_fields=campos)
        except IntegrityError as error:
            restriccion = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
            if restriccion != "billete_moneda_valor_unico":
                raise
            form.add_error(None, "Ya existe una denominación con esa moneda y valor.")
            return self.form_invalid(form)
        messages.success(self.request, "Denominación guardada correctamente.")
        return redirect(self.success_url)


class DenominacionBilleteCreateView(
    AdminOTesoreroRequiredMixin, DenominacionFormMixin, CreateView
):
    extra_context = {"page_title": "Nueva denominación de billete", "submit_label": "Guardar denominación"}


class DenominacionBilleteUpdateView(
    AdminOTesoreroRequiredMixin, DenominacionFormMixin, UpdateView
):
    pk_url_kwarg = "id_denominacion"
    extra_context = {"page_title": "Editar denominación de billete", "submit_label": "Guardar cambios"}


class DenominacionBilleteEstadoView(AdminOTesoreroRequiredMixin, View):
    """Cambia el estado mediante POST sin eliminar registros históricos."""

    def post(self, request, id_denominacion, activar):
        denominacion = get_object_or_404(DenominacionBillete, pk=id_denominacion)
        denominacion.activa = activar
        denominacion.save(update_fields=["activa"])
        messages.success(
            request,
            "Denominación habilitada correctamente." if activar
            else "Denominación deshabilitada correctamente.",
        )
        return redirect("denominacion-list")


class AperturaContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(active_menu="cajas", active_submenu="aperturas")
        return context


class AperturaCajaListView(CajeroRequiredMixin, AperturaContextMixin, TemplateView):
    template_name = "cajas/apertura_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activas = AperturaCaja.objects.filter(caja_id=OuterRef("caja_id"), estado="ABIERTA")
        context["asignaciones"] = asignaciones_vigentes(self.cajero_id).annotate(
            apertura_activa_id=Subquery(activas.values("pk")[:1])
        )
        # Se mantienen accesibles aunque haya vencido el turno o se deshabilite la caja.
        context["aperturas"] = AperturaCaja.objects.filter(
            cajero_keycloak_id=self.cajero_id
        ).select_related("caja__sucursal")[:50]
        return context


class AperturaCajaCreateView(CajeroRequiredMixin, AperturaContextMixin, TemplateView):
    template_name = "cajas/apertura_form.html"

    def get_asignacion(self):
        return get_object_or_404(
            AsignacionCaja.objects.select_related("caja__sucursal"),
            pk=self.kwargs["id_asignacion"], cajero_keycloak_id=self.cajero_id,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["asignacion"] = self.get_asignacion()
        context.setdefault("formset", InventarioInicialFormSet(prefix="inventario"))
        context["denominaciones"] = list(DenominacionBillete.objects.filter(
            activa=True, moneda__activa=True
        ).values("id", "moneda_id"))
        return context

    def post(self, request, *args, **kwargs):
        asignacion = self.get_asignacion()
        formset = InventarioInicialFormSet(request.POST, prefix="inventario")
        errores = []
        if formset.is_valid():
            try:
                apertura = abrir_caja(
                    request=request, asignacion_id=asignacion.pk, inventario=formset.inventario()
                )
            except ValidationError as error:
                errores = error.messages
            else:
                messages.success(request, "Apertura de caja registrada correctamente.")
                return redirect("apertura-detail", id_apertura=apertura.pk)
        return self.render_to_response(self.get_context_data(formset=formset, errores=errores))


class AperturaCajaDetailView(CajeroRequiredMixin, AperturaContextMixin, DetailView):
    template_name = "cajas/apertura_detail.html"
    context_object_name = "apertura"
    pk_url_kwarg = "id_apertura"

    def get_queryset(self):
        return AperturaCaja.objects.filter(cajero_keycloak_id=self.cajero_id).select_related(
            "caja__sucursal", "asignacion"
        ).prefetch_related("detalles_inventario")

