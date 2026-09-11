from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import ClienteActivoRequiredMixin
from usuarios.models import obtener_cliente_activo

from .forms import MetodoPagoForm
from .models import AccionAuditoriaMetodoPago, AuditoriaMetodoPago, MetodoPago
from .serializers import MetodoPagoSerializer


class MetodoPagoWebListView(ClienteActivoRequiredMixin, ListView):
    """Muestra los métodos de pago registrados para el cliente activo del usuario."""
    model = MetodoPago
    template_name = "pagos/metodopago_list.html"
    context_object_name = "metodos_pago"

    def get_queryset(self):
        """Filtra los métodos de pago del cliente activo según el parámetro GET 'estado'.

        Sin parámetro (o con cualquier valor distinto de 'todos' o
        'inactivos') se listan solo los métodos de pago activos.

        Returns:
            django.db.models.QuerySet: Métodos de pago del cliente activo,
            filtrados según el estado solicitado.
        """
        queryset = MetodoPago.objects.filter(cliente=obtener_cliente_activo(self.request.user))
        estado = self.request.GET.get("estado", "").strip()

        if estado == "todos":
            return queryset
        if estado == "inactivos":
            return queryset.filter(activo=False)
        return queryset.filter(activo=True)

    def get_context_data(self, **kwargs):
        """Marca el menú de métodos de pago como activo y expone el filtro de estado.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto del listado con la selección del menú y el
            filtro de estado actualmente aplicado.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "metodos_pago"
        context["estado"] = self.request.GET.get("estado", "").strip()
        return context


class MetodoPagoWebCreateView(ClienteActivoRequiredMixin, CreateView):
    """Permite registrar un método de pago para el cliente activo del usuario."""
    model = MetodoPago
    form_class = MetodoPagoForm
    template_name = "pagos/metodopago_form.html"
    success_url = reverse_lazy("metodopago-web-list")

    def form_valid(self, form):
        """Asocia el método de pago al cliente activo y registra la auditoría de creación.

        Args:
            form (MetodoPagoForm): Formulario validado con los datos de la tarjeta.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            métodos de pago después de guardar el registro.
        """
        form.instance.cliente = obtener_cliente_activo(self.request.user)
        response = super().form_valid(form)
        AuditoriaMetodoPago.objects.registrar(
            metodo_pago=self.object,
            accion=AccionAuditoriaMetodoPago.CREACION,
            realizado_por=self.request.user,
            datos_nuevos={
                "tipo": self.object.tipo,
                "titular": self.object.titular,
                "ultimos_cuatro_digitos": self.object.ultimos_cuatro_digitos,
                "fecha_vencimiento": self.object.fecha_vencimiento,
            },
        )
        messages.success(self.request, "Método de pago registrado correctamente.")
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
                "active_menu": "metodos_pago",
                "page_title": "Nuevo método de pago",
                "submit_label": "Guardar",
            }
        )
        return context


class MetodoPagoWebUpdateView(ClienteActivoRequiredMixin, UpdateView):
    """Permite editar los datos de un método de pago del cliente activo."""
    model = MetodoPago
    form_class = MetodoPagoForm
    template_name = "pagos/metodopago_form.html"
    pk_url_kwarg = "id_metodo_pago"
    success_url = reverse_lazy("metodopago-web-list")

    def get_queryset(self):
        """Restringe la edición a los métodos de pago del cliente activo.

        Returns:
            django.db.models.QuerySet: Métodos de pago pertenecientes al
            cliente activo del usuario.
        """
        return MetodoPago.objects.filter(cliente=obtener_cliente_activo(self.request.user))

    def get_object(self, queryset=None):
        """Obtiene el método de pago a editar y guarda una copia de sus datos actuales.

        Returns:
            MetodoPago: Método de pago identificado por la URL.
        """
        metodo_pago = super().get_object(queryset)
        self._datos_anteriores = {
            "titular": metodo_pago.titular,
            "ultimos_cuatro_digitos": metodo_pago.ultimos_cuatro_digitos,
            "fecha_vencimiento": metodo_pago.fecha_vencimiento,
        }
        return metodo_pago

    def form_valid(self, form):
        """Guarda los cambios del método de pago y registra la auditoría de modificación.

        Args:
            form (MetodoPagoForm): Formulario validado con los nuevos datos.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            métodos de pago después de guardar los cambios.
        """
        response = super().form_valid(form)
        AuditoriaMetodoPago.objects.registrar(
            metodo_pago=self.object,
            accion=AccionAuditoriaMetodoPago.MODIFICACION,
            realizado_por=self.request.user,
            datos_anteriores=self._datos_anteriores,
            datos_nuevos={
                "titular": self.object.titular,
                "ultimos_cuatro_digitos": self.object.ultimos_cuatro_digitos,
                "fecha_vencimiento": self.object.fecha_vencimiento,
            },
        )
        messages.success(self.request, "Método de pago actualizado correctamente.")
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
                "active_menu": "metodos_pago",
                "page_title": "Editar método de pago",
                "submit_label": "Guardar cambios",
            }
        )
        return context


class MetodoPagoWebDeactivateView(ClienteActivoRequiredMixin, View):
    """Permite desactivar un método de pago del cliente activo desde la interfaz web."""
    def post(self, request, id_metodo_pago):
        """Desactiva el método de pago y redirige al listado.

        Añade un mensaje de éxito si cambia el estado o un mensaje
        informativo si ya estaba desactivado. Registra la acción en la
        auditoría solo cuando efectivamente se desactiva.

        Args:
            request (django.http.HttpRequest): Solicitud utilizada para
                registrar los mensajes y el usuario de la operación.
            id_metodo_pago (int): Identificador del método de pago a desactivar.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            métodos de pago.

        Raises:
            django.http.Http404: Si el método de pago no existe o no
                pertenece al cliente activo.
        """
        metodo_pago = get_object_or_404(
            MetodoPago, id_metodo_pago=id_metodo_pago, cliente=obtener_cliente_activo(request.user)
        )

        if metodo_pago.activo:
            metodo_pago.activo = False
            metodo_pago.save(update_fields=["activo"])
            AuditoriaMetodoPago.objects.registrar(
                metodo_pago=metodo_pago,
                accion=AccionAuditoriaMetodoPago.DESACTIVACION,
                realizado_por=request.user,
                datos_anteriores={"activo": True},
                datos_nuevos={"activo": False},
            )
            messages.success(request, "Método de pago desactivado correctamente.")
        else:
            messages.info(request, "El método de pago ya se encontraba desactivado.")

        return redirect("metodopago-web-list")


class MetodoPagoWebActivateView(ClienteActivoRequiredMixin, View):
    """Permite reactivar un método de pago del cliente activo desde la interfaz web."""
    def post(self, request, id_metodo_pago):
        """Reactiva el método de pago y redirige al listado.

        Añade un mensaje de éxito si cambia el estado o un mensaje
        informativo si ya estaba activo. Registra la acción en la
        auditoría solo cuando efectivamente se reactiva.

        Args:
            request (django.http.HttpRequest): Solicitud utilizada para
                registrar los mensajes y el usuario de la operación.
            id_metodo_pago (int): Identificador del método de pago a reactivar.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            métodos de pago.

        Raises:
            django.http.Http404: Si el método de pago no existe o no
                pertenece al cliente activo.
        """
        metodo_pago = get_object_or_404(
            MetodoPago, id_metodo_pago=id_metodo_pago, cliente=obtener_cliente_activo(request.user)
        )

        if not metodo_pago.activo:
            metodo_pago.activo = True
            metodo_pago.save(update_fields=["activo"])
            AuditoriaMetodoPago.objects.registrar(
                metodo_pago=metodo_pago,
                accion=AccionAuditoriaMetodoPago.ACTIVACION,
                realizado_por=request.user,
                datos_anteriores={"activo": False},
                datos_nuevos={"activo": True},
            )
            messages.success(request, "Método de pago activado correctamente.")
        else:
            messages.info(request, "El método de pago ya se encontraba activo.")

        return redirect("metodopago-web-list")


class MetodoPagoWebDeleteView(ClienteActivoRequiredMixin, DeleteView):
    """Permite eliminar definitivamente un método de pago del cliente activo."""
    model = MetodoPago
    template_name = "pagos/metodopago_confirm_delete.html"
    pk_url_kwarg = "id_metodo_pago"
    context_object_name = "metodo_pago"
    success_url = reverse_lazy("metodopago-web-list")

    def get_queryset(self):
        """Restringe la eliminación a los métodos de pago del cliente activo.

        Returns:
            django.db.models.QuerySet: Métodos de pago pertenecientes al
            cliente activo del usuario.
        """
        return MetodoPago.objects.filter(cliente=obtener_cliente_activo(self.request.user))

    def form_valid(self, form):
        """Registra la auditoría de eliminación antes de borrar el método de pago.

        El registro de auditoría se crea antes de eliminar el objeto: la
        relación usa SET_NULL, así que la fila de auditoría sobrevive al
        borrado y deja constancia de qué tarjeta existía.

        Args:
            form (django.forms.Form): Formulario vacío de confirmación.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            métodos de pago después de eliminar el registro.
        """
        AuditoriaMetodoPago.objects.registrar(
            metodo_pago=self.object,
            accion=AccionAuditoriaMetodoPago.ELIMINACION,
            realizado_por=self.request.user,
            datos_anteriores={
                "tipo": self.object.tipo,
                "titular": self.object.titular,
                "ultimos_cuatro_digitos": self.object.ultimos_cuatro_digitos,
                "fecha_vencimiento": self.object.fecha_vencimiento,
                "activo": self.object.activo,
            },
        )
        messages.success(self.request, "Método de pago eliminado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """Marca el menú de métodos de pago como activo.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo seleccionado.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "metodos_pago"
        return context


class MetodoPagoListCreateView(generics.ListCreateAPIView):
    """Expone por API el listado y alta de métodos de pago del cliente activo."""
    serializer_class = MetodoPagoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Limita la lista a los métodos de pago del cliente activo del usuario.

        Returns:
            django.db.models.QuerySet: Métodos de pago del cliente activo,
            o un queryset vacío si no hay cliente activo.
        """
        cliente = obtener_cliente_activo(self.request.user)
        if cliente is None:
            return MetodoPago.objects.none()

        queryset = MetodoPago.objects.filter(cliente=cliente)
        activo = self.request.query_params.get("activo")
        if activo is not None:
            queryset = queryset.filter(activo=activo.lower() == "true")
        return queryset

    def perform_create(self, serializer):
        """Asocia el método de pago creado al cliente activo y registra la auditoría.

        Args:
            serializer (MetodoPagoSerializer): Serializer validado con los
                datos de la tarjeta.

        Raises:
            rest_framework.exceptions.PermissionDenied: Si el usuario no
                tiene un cliente activo asociado.
        """
        cliente = obtener_cliente_activo(self.request.user)
        if cliente is None:
            raise PermissionDenied("Necesitás un cliente activo para registrar un método de pago.")

        metodo_pago = serializer.save(cliente=cliente)
        AuditoriaMetodoPago.objects.registrar(
            metodo_pago=metodo_pago,
            accion=AccionAuditoriaMetodoPago.CREACION,
            realizado_por=self.request.user,
            datos_nuevos={
                "tipo": metodo_pago.tipo,
                "titular": metodo_pago.titular,
                "ultimos_cuatro_digitos": metodo_pago.ultimos_cuatro_digitos,
                "fecha_vencimiento": metodo_pago.fecha_vencimiento,
            },
        )


class MetodoPagoDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Expone por API el detalle, edición y baja de un método de pago del cliente activo."""
    serializer_class = MetodoPagoSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "id_metodo_pago"
    lookup_field = "id_metodo_pago"

    def get_queryset(self):
        """Limita el acceso a los métodos de pago del cliente activo del usuario.

        Returns:
            django.db.models.QuerySet: Métodos de pago del cliente activo,
            o un queryset vacío si no hay cliente activo (evita que un
            usuario acceda a métodos de pago de otro cliente).
        """
        cliente = obtener_cliente_activo(self.request.user)
        if cliente is None:
            return MetodoPago.objects.none()
        return MetodoPago.objects.filter(cliente=cliente)

    def perform_update(self, serializer):
        """Guarda los cambios del método de pago y registra la auditoría de modificación.

        Args:
            serializer (MetodoPagoSerializer): Serializer validado con los
                nuevos datos.
        """
        instancia = self.get_object()
        datos_anteriores = {
            "titular": instancia.titular,
            "ultimos_cuatro_digitos": instancia.ultimos_cuatro_digitos,
            "fecha_vencimiento": instancia.fecha_vencimiento,
        }
        metodo_pago = serializer.save()
        AuditoriaMetodoPago.objects.registrar(
            metodo_pago=metodo_pago,
            accion=AccionAuditoriaMetodoPago.MODIFICACION,
            realizado_por=self.request.user,
            datos_anteriores=datos_anteriores,
            datos_nuevos={
                "titular": metodo_pago.titular,
                "ultimos_cuatro_digitos": metodo_pago.ultimos_cuatro_digitos,
                "fecha_vencimiento": metodo_pago.fecha_vencimiento,
            },
        )

    def perform_destroy(self, instance):
        """Registra la auditoría de eliminación antes de borrar el método de pago.

        Args:
            instance (MetodoPago): Método de pago a eliminar.
        """
        AuditoriaMetodoPago.objects.registrar(
            metodo_pago=instance,
            accion=AccionAuditoriaMetodoPago.ELIMINACION,
            realizado_por=self.request.user,
            datos_anteriores={
                "tipo": instance.tipo,
                "titular": instance.titular,
                "ultimos_cuatro_digitos": instance.ultimos_cuatro_digitos,
                "fecha_vencimiento": instance.fecha_vencimiento,
                "activo": instance.activo,
            },
        )
        instance.delete()


class MetodoPagoDesactivarView(APIView):
    """Permite desactivar por API un método de pago del cliente activo."""
    permission_classes = [IsAuthenticated]

    def post(self, request, id_metodo_pago):
        """Desactiva el método de pago indicado si pertenece al cliente activo.

        Args:
            request (rest_framework.request.Request): Solicitud autenticada.
            id_metodo_pago (int): Identificador del método de pago.

        Returns:
            rest_framework.response.Response: Estado resultante de la operación.

        Raises:
            django.http.Http404: Si el método de pago no existe o no
                pertenece al cliente activo.
        """
        cliente = obtener_cliente_activo(request.user)
        metodo_pago = get_object_or_404(MetodoPago, id_metodo_pago=id_metodo_pago, cliente=cliente)

        if metodo_pago.activo:
            metodo_pago.activo = False
            metodo_pago.save(update_fields=["activo"])
            AuditoriaMetodoPago.objects.registrar(
                metodo_pago=metodo_pago,
                accion=AccionAuditoriaMetodoPago.DESACTIVACION,
                realizado_por=request.user,
                datos_anteriores={"activo": True},
                datos_nuevos={"activo": False},
            )
        return Response({"activo": metodo_pago.activo}, status=status.HTTP_200_OK)


class MetodoPagoActivarView(APIView):
    """Permite reactivar por API un método de pago del cliente activo."""
    permission_classes = [IsAuthenticated]

    def post(self, request, id_metodo_pago):
        """Reactiva el método de pago indicado si pertenece al cliente activo.

        Args:
            request (rest_framework.request.Request): Solicitud autenticada.
            id_metodo_pago (int): Identificador del método de pago.

        Returns:
            rest_framework.response.Response: Estado resultante de la operación.

        Raises:
            django.http.Http404: Si el método de pago no existe o no
                pertenece al cliente activo.
        """
        cliente = obtener_cliente_activo(request.user)
        metodo_pago = get_object_or_404(MetodoPago, id_metodo_pago=id_metodo_pago, cliente=cliente)

        if not metodo_pago.activo:
            metodo_pago.activo = True
            metodo_pago.save(update_fields=["activo"])
            AuditoriaMetodoPago.objects.registrar(
                metodo_pago=metodo_pago,
                accion=AccionAuditoriaMetodoPago.ACTIVACION,
                realizado_por=request.user,
                datos_anteriores={"activo": False},
                datos_nuevos={"activo": True},
            )
        return Response({"activo": metodo_pago.activo}, status=status.HTTP_200_OK)
