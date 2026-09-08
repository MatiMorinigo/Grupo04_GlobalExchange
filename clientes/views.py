from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from core.mixins import AdminRequiredMixin
from .forms import ClienteForm, ConfiguracionBeneficioCategoriaForm
from .models import Cliente, ConfiguracionBeneficioCategoria
from .permissions import EsAdministrador
from .serializers import ClienteSerializer

class ClienteCreateView(generics.CreateAPIView):
    """Expone la creación de clientes por API para administradores.

    Valida los datos mediante ClienteSerializer y guarda el nuevo cliente.
    """
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]



class ClienteListView(generics.ListAPIView):
    """Lista clientes por API para administradores con filtros opcionales."""
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]

    def get_queryset(self):
        """Obtiene los clientes según los parámetros de consulta de la API.

        Lee categoria, tipo y activo de la solicitud. Si activo está presente,
        solo el valor 'true', sin distinguir mayúsculas, selecciona clientes
        activos; cualquier otro valor selecciona clientes inactivos.

        Returns:
            django.db.models.QuerySet: Clientes que cumplen los filtros indicados.
        """
        queryset = Cliente.objects.all()

        categoria = self.request.query_params.get("categoria")
        tipo = self.request.query_params.get("tipo")
        activo = self.request.query_params.get("activo")

        if categoria:
            queryset = queryset.filter(categoria=categoria)

        if tipo:
            queryset = queryset.filter(tipo=tipo)

        if activo is not None:
            queryset = queryset.filter(
                activo=activo.lower() == "true"
            )

        return queryset


class ClienteDetailView(generics.RetrieveUpdateAPIView):
    """Permite consultar y actualizar un cliente por API a administradores.

    Identifica al cliente mediante el parámetro de URL id_cliente.
    """
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]
    lookup_field = "id_cliente"

    def get_object(self):
        """Busca el cliente identificado por id_cliente en la URL.

        Returns:
            Cliente: Cliente correspondiente al identificador solicitado.

        Raises:
            rest_framework.exceptions.NotFound: Si el cliente no existe.
        """
        try:
            return Cliente.objects.get(
                id_cliente=self.kwargs["id_cliente"]
            )
        except Cliente.DoesNotExist:
            raise NotFound("Cliente no encontrado.")


class ClienteDeactivateView(APIView):
    """Expone la desactivación de clientes por API para administradores."""
    permission_classes = [EsAdministrador]
    def patch(self, request, id_cliente):
        """Desactiva un cliente sin eliminar su registro.

        Args:
            request (rest_framework.request.Request): Solicitud HTTP recibida.
            id_cliente (int): Identificador del cliente que se desea desactivar.

        Returns:
            rest_framework.response.Response: Mensaje con estado HTTP 200 al
            desactivar el cliente, o HTTP 400 si ya estaba inactivo.

        Raises:
            rest_framework.exceptions.NotFound: Si el cliente no existe.
        """
        try:
            cliente = Cliente.objects.get(id_cliente=id_cliente)
        except Cliente.DoesNotExist:
            raise NotFound("Cliente no encontrado.")

        if not cliente.activo:
            return Response(
                {"detail": "El cliente ya se encuentra inactivo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        cliente.activo = False
        cliente.save(update_fields=["activo"])

        return Response(
            {"detail": "Cliente desactivado correctamente."},
            status=status.HTTP_200_OK
        )


class ClienteWebListView(AdminRequiredMixin, ListView):
    """Muestra a administradores un listado paginado de clientes.

    Presenta diez clientes por página y permite filtrar por texto, estado,
    categoría y tipo de persona.
    """
    model = Cliente
    template_name = "clientes/cliente_list.html"
    context_object_name = "clientes"
    paginate_by = 10

    def get_queryset(self):
        """Filtra los clientes de la interfaz web y los ordena por nombre.

        Lee los parámetros GET q, estado, categoria y tipo. Busca q en nombre
        o RUC sin distinguir mayúsculas. Los estados 'activos' e 'inactivos'
        restringen el listado según el campo activo.

        Returns:
            django.db.models.QuerySet: Clientes filtrados y ordenados por nombre.
        """
        queryset = Cliente.objects.order_by("nombre")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "").strip()
        categoria = self.request.GET.get("categoria", "").strip()
        tipo = self.request.GET.get("tipo", "").strip()

        if query:
            queryset = queryset.filter(
                Q(nombre__icontains=query) | Q(ruc__icontains=query)
            )

        if estado == "activos":
            queryset = queryset.filter(activo=True)
        elif estado == "inactivos":
            queryset = queryset.filter(activo=False)

        if categoria:
            queryset = queryset.filter(categoria=categoria)

        if tipo:
            queryset = queryset.filter(tipo=tipo)

        return queryset

    def get_context_data(self, **kwargs):
        """Añade filtros y estadísticas generales al contexto del listado.

        Los conteos abarcan todos los clientes, independientemente de los
        filtros aplicados al listado.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo, los filtros actuales y los conteos
            de clientes totales, activos, inactivos y categorías distintas.
        """
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_menu": "clientes",
                "query": self.request.GET.get("q", "").strip(),
                "estado": self.request.GET.get("estado", "").strip(),
                "total_clientes": Cliente.objects.count(),
                "clientes_activos": Cliente.objects.filter(activo=True).count(),
                "clientes_inactivos": Cliente.objects.filter(activo=False).count(),
                "categorias_count": Cliente.objects.values("categoria").distinct().count(),
                "categoria": self.request.GET.get("categoria", "").strip(),
                "tipo": self.request.GET.get("tipo", "").strip(),
            }
        )
        return context


class ClienteWebCreateView(AdminRequiredMixin, CreateView):
    """Permite a administradores crear clientes mediante un formulario web."""
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cliente_form.html"
    success_url = reverse_lazy("cliente-web-list")

    def form_valid(self, form):
        """Anuncia la creación y delega el guardado del formulario válido.

        Args:
            form (ClienteForm): Formulario validado con los datos del cliente.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de clientes
            después de guardar el registro.
        """
        messages.success(self.request, "Cliente creado correctamente.")
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
                "active_menu": "clientes",
                "page_title": "Nuevo cliente",
                "submit_label": "Guardar cliente",
            }
        )
        return context


class ClienteWebDetailView(AdminRequiredMixin,DetailView):
    """Muestra a administradores el detalle de un cliente.

    Obtiene el cliente mediante el parámetro de URL id_cliente.
    """
    model = Cliente
    template_name = "clientes/cliente_detail.html"
    context_object_name = "cliente"
    pk_url_kwarg = "id_cliente"

    def get_context_data(self, **kwargs):
        """Marca el menú de clientes como activo en la página de detalle.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto del detalle con la selección del menú de clientes.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "clientes"
        return context


class ClienteWebUpdateView(AdminRequiredMixin,UpdateView):
    """Permite a administradores editar clientes mediante un formulario web."""
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cliente_form.html"
    pk_url_kwarg = "id_cliente"

    def get_success_url(self):
        """Resuelve la URL de detalle del cliente actualizado.

        Returns:
            django.utils.functional.Promise: URL evaluada de forma diferida
            para mostrar el detalle del cliente guardado.
        """
        return reverse_lazy("cliente-web-detail", kwargs={"id_cliente": self.object.id_cliente})

    def form_valid(self, form):
        """Anuncia la actualización y delega el guardado del formulario válido.

        Args:
            form (ClienteForm): Formulario validado con los cambios del cliente.

        Returns:
            django.http.HttpResponseRedirect: Redirección al detalle del cliente
            después de guardar los cambios.
        """
        messages.success(self.request, "Cliente actualizado correctamente.")
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
                "active_menu": "clientes",
                "page_title": "Editar cliente",
                "submit_label": "Guardar cambios",
            }
        )
        return context


class ClienteWebDeactivateView(AdminRequiredMixin, View):
    """Permite a administradores desactivar clientes desde la interfaz web."""
    def post(self, request, id_cliente):
        """Desactiva el cliente y redirige a su página de detalle.

        Añade un mensaje de éxito si cambia el estado o un mensaje informativo
        si el cliente ya estaba inactivo.

        Args:
            request (django.http.HttpRequest): Solicitud utilizada para registrar
                los mensajes de la operación.
            id_cliente (int): Identificador del cliente que se desea desactivar.

        Returns:
            django.http.HttpResponseRedirect: Redirección al detalle del cliente.

        Raises:
            django.http.Http404: Si el cliente no existe.
        """
        cliente = get_object_or_404(Cliente, id_cliente=id_cliente)

        if cliente.activo:
            cliente.activo = False
            cliente.save(update_fields=["activo"])
            messages.success(request, "Cliente desactivado correctamente.")
        else:
            messages.info(request, "El cliente ya se encontraba inactivo.")

        return redirect("cliente-web-detail", id_cliente=cliente.id_cliente)

class ConfiguracionBeneficioCategoriaListView(AdminRequiredMixin, ListView):
    """
    Muestra al administrador la configuración de beneficios
    correspondiente a cada categoría de cliente.
    """

    model = ConfiguracionBeneficioCategoria
    template_name = "clientes/configuracion_beneficios_list.html"
    context_object_name = "configuraciones"

    def get_queryset(self):
        """
        Obtiene las configuraciones ordenadas por categoría.

        Returns:
            QuerySet: Configuraciones de beneficios por categoría.
        """
        return ConfiguracionBeneficioCategoria.objects.order_by("categoria")

class ConfiguracionBeneficioCategoriaUpdateView(AdminRequiredMixin, UpdateView):
    """
    Permite al administrador modificar el beneficio porcentual
    y el límite mensual de una categoría de cliente.
    """

    model = ConfiguracionBeneficioCategoria
    form_class = ConfiguracionBeneficioCategoriaForm
    template_name = "clientes/configuracion_beneficios_form.html"
    success_url = reverse_lazy("configuracion_beneficios")

    def form_valid(self, form):
        """
        Guarda la configuración modificada y muestra un mensaje de éxito.
        """
        messages.success(
            self.request,
            "La configuración de beneficios fue actualizada correctamente.",
        )
        return super().form_valid(form)