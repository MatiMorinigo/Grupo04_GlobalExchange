from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from core.mixins import AdminRequiredMixin

from .forms import MetodoPagoForm
from .models import MetodoPago
from .permissions import EsAdministrador
from .serializers import MetodoPagoSerializer


# ─────────────────────────────────────────────────────────────────────────────
# Vistas API (DRF)
# ─────────────────────────────────────────────────────────────────────────────


class MetodoPagoListCreateView(generics.ListCreateAPIView):
    """Lista y crea métodos de pago por API para administradores.

    Soporta el filtro opcional ?habilitado=true|false en el listado.
    Al crear, registra automáticamente el usuario como creado_por.
    """

    serializer_class = MetodoPagoSerializer
    permission_classes = [EsAdministrador]

    def get_queryset(self):
        """Filtra los métodos de pago según el parámetro habilitado.

        Returns:
            django.db.models.QuerySet: Métodos de pago filtrados por
            habilitado si el parámetro está presente, o todos en caso
            contrario.
        """
        queryset = MetodoPago.objects.all()
        habilitado = self.request.query_params.get("habilitado")
        if habilitado is not None:
            queryset = queryset.filter(habilitado=habilitado.lower() == "true")
        return queryset

    def perform_create(self, serializer):
        """Guarda el nuevo método de pago asignando el usuario actual como creado_por.

        Args:
            serializer (MetodoPagoSerializer): Serializer validado con los datos
                del nuevo método de pago.
        """
        serializer.save(creado_por=self.request.user)


class MetodoPagoDetailView(generics.RetrieveUpdateAPIView):
    """Consulta y actualiza un método de pago por API para administradores.

    Identifica el registro mediante el parámetro de URL id_metodo_pago.
    Al actualizar, registra automáticamente el usuario como modificado_por.
    """

    serializer_class = MetodoPagoSerializer
    permission_classes = [EsAdministrador]
    lookup_field = "id_metodo_pago"

    def get_object(self):
        """Busca el método de pago identificado por id_metodo_pago en la URL.

        Returns:
            MetodoPago: Método de pago correspondiente al identificador.

        Raises:
            rest_framework.exceptions.NotFound: Si el método no existe.
        """
        try:
            return MetodoPago.objects.get(
                id_metodo_pago=self.kwargs["id_metodo_pago"]
            )
        except MetodoPago.DoesNotExist:
            raise NotFound("Método de pago no encontrado.")

    def perform_update(self, serializer):
        """Guarda los cambios asignando el usuario actual como modificado_por.

        Args:
            serializer (MetodoPagoSerializer): Serializer validado con los nuevos
                datos del método de pago.
        """
        serializer.save(modificado_por=self.request.user)


class MetodoPagoHabilitadosView(generics.ListAPIView):
    """Expone por API únicamente los métodos de pago habilitados.

    Este endpoint es el que deben consumir las operaciones cambiarias
    para restringir la selección a métodos activos (CA-4 / HU27).
    No requiere rol administrador: es de lectura pública autenticada.
    """

    serializer_class = MetodoPagoSerializer
    queryset = MetodoPago.objects.filter(habilitado=True)


# ─────────────────────────────────────────────────────────────────────────────
# Vistas web (CBV + AdminRequiredMixin)
# ─────────────────────────────────────────────────────────────────────────────


class MetodoPagoWebListView(AdminRequiredMixin, ListView):
    """Muestra a administradores un listado de métodos de pago con filtros."""

    model = MetodoPago
    template_name = "pagos/metodopago_list.html"
    context_object_name = "metodos"
    paginate_by = 10

    def get_queryset(self):
        """Filtra los métodos de pago por nombre y estado habilitado.

        Lee los parámetros GET q y estado. Busca q en el nombre sin
        distinguir mayúsculas. Los estados 'habilitados' e 'inhabilitados'
        restringen el listado según el campo habilitado.

        Returns:
            django.db.models.QuerySet: Métodos filtrados y ordenados por nombre.
        """
        queryset = MetodoPago.objects.order_by("nombre")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "").strip()

        if query:
            queryset = queryset.filter(nombre__icontains=query)

        if estado == "habilitados":
            queryset = queryset.filter(habilitado=True)
        elif estado == "inhabilitados":
            queryset = queryset.filter(habilitado=False)

        return queryset

    def get_context_data(self, **kwargs):
        """Añade filtros y estadísticas al contexto del listado.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo, los filtros y los conteos
            de métodos totales, habilitados e inhabilitados.
        """
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_menu": "metodos_pago",
                "query": self.request.GET.get("q", "").strip(),
                "estado": self.request.GET.get("estado", "").strip(),
                "total_metodos": MetodoPago.objects.count(),
                "metodos_habilitados": MetodoPago.objects.filter(habilitado=True).count(),
                "metodos_inhabilitados": MetodoPago.objects.filter(habilitado=False).count(),
            }
        )
        return context


class MetodoPagoWebCreateView(AdminRequiredMixin, CreateView):
    """Permite a administradores crear métodos de pago mediante un formulario web."""

    model = MetodoPago
    form_class = MetodoPagoForm
    template_name = "pagos/metodopago_form.html"
    success_url = reverse_lazy("metodopago-web-list")

    def form_valid(self, form):
        """Asigna el usuario actual como creado_por y anuncia la creación.

        Args:
            form (MetodoPagoForm): Formulario validado con los datos del método.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado tras guardar.
        """
        form.instance.creado_por = self.request.user
        messages.success(self.request, "Método de pago creado correctamente.")
        return super().form_valid(form)

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
                "active_menu": "metodos_pago",
                "page_title": "Nuevo método de pago",
                "submit_label": "Guardar método de pago",
            }
        )
        return context


class MetodoPagoWebDetailView(AdminRequiredMixin, DetailView):
    """Muestra a administradores el detalle de un método de pago.

    Obtiene el registro mediante el parámetro de URL id_metodo_pago.
    """

    model = MetodoPago
    template_name = "pagos/metodopago_detail.html"
    context_object_name = "metodo"
    pk_url_kwarg = "id_metodo_pago"

    def get_context_data(self, **kwargs):
        """Marca el menú de métodos de pago como activo en la página de detalle.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto del detalle con la selección del menú activo.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "metodos_pago"
        return context


class MetodoPagoWebUpdateView(AdminRequiredMixin, UpdateView):
    """Permite a administradores editar métodos de pago mediante un formulario web."""

    model = MetodoPago
    form_class = MetodoPagoForm
    template_name = "pagos/metodopago_form.html"
    pk_url_kwarg = "id_metodo_pago"

    def get_success_url(self):
        """Resuelve la URL de detalle del método de pago actualizado.

        Returns:
            str: URL de detalle del método guardado.
        """
        return reverse_lazy(
            "metodopago-web-detail",
            kwargs={"id_metodo_pago": self.object.id_metodo_pago},
        )

    def form_valid(self, form):
        """Asigna el usuario actual como modificado_por y anuncia la actualización.

        Args:
            form (MetodoPagoForm): Formulario validado con los cambios del método.

        Returns:
            django.http.HttpResponseRedirect: Redirección al detalle tras guardar.
        """
        form.instance.modificado_por = self.request.user
        messages.success(self.request, "Método de pago actualizado correctamente.")
        return super().form_valid(form)

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
                "active_menu": "metodos_pago",
                "page_title": "Editar método de pago",
                "submit_label": "Guardar cambios",
            }
        )
        return context


class MetodoPagoWebToggleView(AdminRequiredMixin, View):
    """Permite a administradores habilitar o deshabilitar un método de pago."""

    def post(self, request, id_metodo_pago):
        """Invierte el estado habilitado del método y redirige a su detalle.

        Registra el usuario actual como modificado_por y muestra un mensaje
        informativo con el nuevo estado resultante.

        Args:
            request (django.http.HttpRequest): Solicitud utilizada para
                registrar los mensajes y el usuario modificador.
            id_metodo_pago (int): Identificador del método de pago a modificar.

        Returns:
            django.http.HttpResponseRedirect: Redirección al detalle del método.

        Raises:
            django.http.Http404: Si el método de pago no existe.
        """
        metodo = get_object_or_404(MetodoPago, id_metodo_pago=id_metodo_pago)
        metodo.habilitado = not metodo.habilitado
        metodo.modificado_por = request.user
        metodo.save(update_fields=["habilitado", "modificado_por", "actualizado_en"])

        if metodo.habilitado:
            messages.success(request, f'Método "{metodo.nombre}" habilitado correctamente.')
        else:
            messages.warning(request, f'Método "{metodo.nombre}" inhabilitado correctamente.')

        return redirect("metodopago-web-detail", id_metodo_pago=metodo.id_metodo_pago)
