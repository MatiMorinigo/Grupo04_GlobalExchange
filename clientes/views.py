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

from .forms import ClienteForm
from .models import Cliente
from .permissions import EsAdministrador
from .serializers import ClienteSerializer

class ClienteCreateView(generics.CreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]



class ClienteListView(generics.ListAPIView):
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]

    def get_queryset(self):
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
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]
    lookup_field = "id_cliente"

    def get_object(self):
        try:
            return Cliente.objects.get(
                id_cliente=self.kwargs["id_cliente"]
            )
        except Cliente.DoesNotExist:
            raise NotFound("Cliente no encontrado.")


class ClienteDeactivateView(APIView):
    permission_classes = [EsAdministrador]
    def patch(self, request, id_cliente):
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


class ClienteWebListView(ListView):
    model = Cliente
    template_name = "clientes/cliente_list.html"
    context_object_name = "clientes"
    paginate_by = 10

    def get_queryset(self):
        queryset = Cliente.objects.order_by("nombre")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "").strip()

        if query:
            queryset = queryset.filter(
                Q(nombre__icontains=query) | Q(ruc__icontains=query)
            )
        if estado == "activos":
            queryset = queryset.filter(activo=True)
        elif estado == "inactivos":
            queryset = queryset.filter(activo=False)

        return queryset

    def get_context_data(self, **kwargs):
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
            }
        )
        return context


class ClienteWebCreateView(CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cliente_form.html"
    success_url = reverse_lazy("cliente-web-list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente creado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_menu": "clientes",
                "page_title": "Nuevo cliente",
                "submit_label": "Guardar cliente",
            }
        )
        return context


class ClienteWebDetailView(DetailView):
    model = Cliente
    template_name = "clientes/cliente_detail.html"
    context_object_name = "cliente"
    pk_url_kwarg = "id_cliente"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "clientes"
        return context


class ClienteWebUpdateView(UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cliente_form.html"
    pk_url_kwarg = "id_cliente"

    def get_success_url(self):
        return reverse_lazy("cliente-web-detail", kwargs={"id_cliente": self.object.id_cliente})

    def form_valid(self, form):
        messages.success(self.request, "Cliente actualizado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_menu": "clientes",
                "page_title": "Editar cliente",
                "submit_label": "Guardar cambios",
            }
        )
        return context


class ClienteWebDeactivateView(View):
    def post(self, request, id_cliente):
        cliente = get_object_or_404(Cliente, id_cliente=id_cliente)

        if cliente.activo:
            cliente.activo = False
            cliente.save(update_fields=["activo"])
            messages.success(request, "Cliente desactivado correctamente.")
        else:
            messages.info(request, "El cliente ya se encontraba inactivo.")

        return redirect("cliente-web-detail", id_cliente=cliente.id_cliente)
