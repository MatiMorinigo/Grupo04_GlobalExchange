from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, FormView, ListView, UpdateView
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.keycloak import tiene_rol
from core.mixins import AdminRequiredMixin, AnalistaCambiarioRequiredMixin
from .forms import (
    ConfiguracionComisionForm,
    MonedaForm,
    SimulacionConversionForm,
    TasaCambioCrearForm,
    TasaCambioEditarForm,
)
from .models import (
    AccionAuditoriaMoneda,
    AuditoriaMoneda,
    AuditoriaTasaCambio,
    ConfiguracionComision,
    Moneda,
    TasaCambio,
)
from .serializers import MonedaSerializer, SimulacionConversionSerializer, TasaCambioSerializer
from .services import SimulacionConversionError, simular_conversion
from clientes.models import CategoriaCliente
from usuarios.models import UsuarioCliente

class MonedaListView(generics.ListAPIView):
    """Expone por API el listado de monedas activas."""
    queryset = Moneda.objects.filter(activa=True)
    serializer_class = MonedaSerializer


class MonedaWebListView(AdminRequiredMixin, ListView):
    """Muestra a administradores el listado de monedas admitidas por el sistema."""
    model = Moneda
    template_name = "cotizaciones/moneda_list.html"
    context_object_name = "monedas"

    def get_queryset(self):
        """Filtra las monedas según el parámetro GET 'estado' y las ordena por código.

        Sin parámetro (o con cualquier valor distinto de 'todas' o
        'deshabilitadas') se listan solo las monedas habilitadas.

        Returns:
            django.db.models.QuerySet: Monedas filtradas y ordenadas por código.
        """
        queryset = Moneda.objects.order_by("codigo")
        estado = self.request.GET.get("estado", "").strip()

        if estado == "todas":
            return queryset
        if estado == "deshabilitadas":
            return queryset.filter(activa=False)
        return queryset.filter(activa=True)

    def get_context_data(self, **kwargs):
        """Marca el menú de monedas como activo y expone el filtro de estado.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto del listado con la selección del menú de monedas
            y el filtro de estado actualmente aplicado.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "monedas"
        context["estado"] = self.request.GET.get("estado", "").strip()
        return context


class MonedaWebCreateView(AdminRequiredMixin, CreateView):
    """Permite a administradores agregar monedas admitidas mediante un formulario web."""
    model = Moneda
    form_class = MonedaForm
    template_name = "cotizaciones/moneda_form.html"
    success_url = reverse_lazy("moneda-web-list")

    def form_valid(self, form):
        """Guarda la moneda creada y registra la acción en la auditoría.

        Args:
            form (MonedaForm): Formulario validado con los datos de la moneda.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de monedas
            después de guardar el registro.
        """
        response = super().form_valid(form)
        AuditoriaMoneda.objects.registrar(
            moneda=self.object,
            accion=AccionAuditoriaMoneda.CREACION,
            realizado_por=self.request.user if self.request.user.is_authenticated else None,
            datos_nuevos={
                "codigo": self.object.codigo,
                "nombre": self.object.nombre,
                "simbolo": self.object.simbolo,
                "activa": self.object.activa,
            },
        )
        messages.success(self.request, "Moneda creada correctamente.")
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
                "active_menu": "monedas",
                "page_title": "Nueva moneda",
                "submit_label": "Guardar moneda",
            }
        )
        return context


class MonedaWebUpdateView(AdminRequiredMixin, UpdateView):
    """Permite a administradores editar el nombre y símbolo de una moneda."""
    model = Moneda
    form_class = MonedaForm
    template_name = "cotizaciones/moneda_form.html"
    pk_url_kwarg = "codigo"
    success_url = reverse_lazy("moneda-web-list")

    def get_object(self, queryset=None):
        """Obtiene la moneda a editar y guarda una copia de sus datos actuales.

        Returns:
            Moneda: Moneda identificada por el código de la URL.
        """
        moneda = super().get_object(queryset)
        self._datos_anteriores = {
            "nombre": moneda.nombre,
            "simbolo": moneda.simbolo,
        }
        return moneda

    def form_valid(self, form):
        """Guarda los cambios de la moneda y registra la acción en la auditoría.

        Args:
            form (MonedaForm): Formulario validado con los nuevos datos.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de monedas
            después de guardar los cambios.
        """
        response = super().form_valid(form)
        AuditoriaMoneda.objects.registrar(
            moneda=self.object,
            accion=AccionAuditoriaMoneda.MODIFICACION,
            realizado_por=self.request.user if self.request.user.is_authenticated else None,
            datos_anteriores=self._datos_anteriores,
            datos_nuevos={
                "nombre": self.object.nombre,
                "simbolo": self.object.simbolo,
            },
        )
        messages.success(self.request, "Moneda actualizada correctamente.")
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
                "active_menu": "monedas",
                "page_title": f"Editar moneda {self.object.codigo}",
                "submit_label": "Guardar cambios",
            }
        )
        return context


class MonedaWebDeactivateView(AdminRequiredMixin, View):
    """Permite a administradores deshabilitar monedas desde la interfaz web."""
    def post(self, request, codigo):
        """Deshabilita la moneda y redirige al listado de monedas.

        Añade un mensaje de éxito si cambia el estado o un mensaje informativo
        si la moneda ya estaba deshabilitada. Registra la acción en la
        auditoría solo cuando efectivamente se deshabilita la moneda.

        Args:
            request (django.http.HttpRequest): Solicitud utilizada para registrar
                los mensajes y el usuario de la operación.
            codigo (str): Código de la moneda que se desea deshabilitar.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de monedas.

        Raises:
            django.http.Http404: Si la moneda no existe.
        """
        moneda = get_object_or_404(Moneda, codigo=codigo)

        if moneda.activa:
            moneda.activa = False
            moneda.save(update_fields=["activa"])
            AuditoriaMoneda.objects.registrar(
                moneda=moneda,
                accion=AccionAuditoriaMoneda.DESHABILITACION,
                realizado_por=request.user if request.user.is_authenticated else None,
                datos_anteriores={"activa": True},
                datos_nuevos={"activa": False},
            )
            messages.success(request, "Moneda deshabilitada correctamente.")
        else:
            messages.info(request, "La moneda ya se encontraba deshabilitada.")

        return redirect("moneda-web-list")


class MonedaWebActivateView(AdminRequiredMixin, View):
    """Permite a administradores habilitar monedas desde la interfaz web."""
    def post(self, request, codigo):
        """Habilita la moneda y redirige al listado de monedas.

        Añade un mensaje de éxito si cambia el estado o un mensaje informativo
        si la moneda ya estaba habilitada. Registra la acción en la
        auditoría solo cuando efectivamente se habilita la moneda.

        Args:
            request (django.http.HttpRequest): Solicitud utilizada para registrar
                los mensajes y el usuario de la operación.
            codigo (str): Código de la moneda que se desea habilitar.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de monedas.

        Raises:
            django.http.Http404: Si la moneda no existe.
        """
        moneda = get_object_or_404(Moneda, codigo=codigo)

        if not moneda.activa:
            moneda.activa = True
            moneda.save(update_fields=["activa"])
            AuditoriaMoneda.objects.registrar(
                moneda=moneda,
                accion=AccionAuditoriaMoneda.HABILITACION,
                realizado_por=request.user if request.user.is_authenticated else None,
                datos_anteriores={"activa": False},
                datos_nuevos={"activa": True},
            )
            messages.success(request, "Moneda habilitada correctamente.")
        else:
            messages.info(request, "La moneda ya se encontraba habilitada.")

        return redirect("moneda-web-list")


class TasaCambioListView(generics.ListAPIView):
    """Expone por API las tasas de cambio con filtros de vigencia y monedas."""
    serializer_class = TasaCambioSerializer

    def get_queryset(self):
        """Filtra las tasas según los parámetros de consulta de la solicitud.

        Por defecto consulta tasas vigentes. Reconoce true, 1, si y sí como
        verdaderos, y false, 0 y no como falsos, sin distinguir mayúsculas.
        Otros valores de vigente no restringen el estado. Normaliza a mayúsculas
        los filtros moneda_origen y moneda_destino.

        Returns:
            django.db.models.QuerySet: Tasas con sus monedas relacionadas,
            ordenadas por los códigos de origen y destino.
        """
        queryset = TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
        vigente = self.request.query_params.get("vigente", "true")
        moneda_origen = self.request.query_params.get("moneda_origen")
        moneda_destino = self.request.query_params.get("moneda_destino")

        if vigente.lower() in {"true", "1", "si", "sí"}:
            queryset = queryset.filter(vigente=True)
        elif vigente.lower() in {"false", "0", "no"}:
            queryset = queryset.filter(vigente=False)

        if moneda_origen:
            queryset = queryset.filter(moneda_origen_id=moneda_origen.upper())
        if moneda_destino:
            queryset = queryset.filter(moneda_destino_id=moneda_destino.upper())

        return queryset.order_by("moneda_origen_id", "moneda_destino_id")


class TasaCambioDetailView(generics.RetrieveAPIView):
    """Expone por API el detalle de una tasa identificada mediante id_tasa."""
    queryset = TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
    serializer_class = TasaCambioSerializer
    lookup_field = "id_tasa"


class TasaCambioParVigenteView(generics.RetrieveAPIView):
    """Expone por API la tasa vigente de un par de monedas."""
    serializer_class = TasaCambioSerializer

    def get_object(self):
        """Busca la tasa vigente del par indicado en la URL.

        Normaliza a mayúsculas los parámetros moneda_origen y moneda_destino.

        Returns:
            TasaCambio: Tasa vigente con sus monedas relacionadas.

        Raises:
            django.http.Http404: Si no existe una tasa vigente para el par.
        """
        return get_object_or_404(
            TasaCambio.objects.select_related("moneda_origen", "moneda_destino"),
            moneda_origen_id=self.kwargs["moneda_origen"].upper(),
            moneda_destino_id=self.kwargs["moneda_destino"].upper(),
            vigente=True,
        )


class TasaCambioEditarView(AnalistaCambiarioRequiredMixin, View):
    """Permite a analistas cambiarios y administradores modificar manualmente una tasa vigente.

    El flujo se resuelve en dos pasos dentro de la misma vista: un primer
    envío solicita los nuevos precios y muestra una comparación antes/después
    sin guardar nada; un segundo envío, con el campo oculto confirmado,
    aplica el cambio. La confirmación crea una nueva fila TasaCambio vigente
    y retira la anterior, preservando el historial y el cálculo de variación
    ya existentes.
    """
    template_name = "cotizaciones/tasa_editar_form.html"

    def get(self, request, id_tasa):
        """Muestra el formulario de edición con los precios vigentes actuales.

        Args:
            request (django.http.HttpRequest): Solicitud HTTP recibida.
            id_tasa (int): Identificador de la tasa vigente que se desea editar.

        Returns:
            django.http.HttpResponse: Página con el formulario de edición.

        Raises:
            django.http.Http404: Si no existe una tasa vigente con ese id.
        """
        tasa = get_object_or_404(
            TasaCambio.objects.select_related("moneda_origen", "moneda_destino"),
            id_tasa=id_tasa,
            vigente=True,
        )
        form = TasaCambioEditarForm(
            initial={
                "precio_compra": tasa.precio_compra,
                "precio_venta": tasa.precio_venta,
            }
        )
        return render(
            request,
            self.template_name,
            {
                "tasa": tasa,
                "form": form,
                "modo_confirmacion": False,
                "active_menu": "cotizaciones",
            },
        )

    def post(self, request, id_tasa):
        """Solicita confirmación de los nuevos precios o aplica la modificación.

        Sin el campo confirmado, valida los precios ingresados y vuelve a
        mostrar el formulario en modo confirmación, sin guardar cambios. Con
        el campo confirmado, crea la nueva tasa vigente, retira la anterior y
        registra la modificación en el log de auditoría.

        Args:
            request (django.http.HttpRequest): Solicitud HTTP recibida.
            id_tasa (int): Identificador de la tasa vigente que se desea editar.

        Returns:
            django.http.HttpResponse or django.http.HttpResponseRedirect:
            El formulario con errores o en modo confirmación, o una
            redirección al listado de cotizaciones tras guardar los cambios.

        Raises:
            django.http.Http404: Si no existe una tasa vigente con ese id.
        """
        tasa = get_object_or_404(
            TasaCambio.objects.select_related("moneda_origen", "moneda_destino"),
            id_tasa=id_tasa,
            vigente=True,
        )
        form = TasaCambioEditarForm(request.POST)

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "tasa": tasa,
                    "form": form,
                    "modo_confirmacion": False,
                    "active_menu": "cotizaciones",
                },
            )

        if not form.cleaned_data["confirmado"]:
            return render(
                request,
                self.template_name,
                {
                    "tasa": tasa,
                    "form": form,
                    "modo_confirmacion": True,
                    "active_menu": "cotizaciones",
                },
            )

        with transaction.atomic():
            tasa_vigente = get_object_or_404(
                TasaCambio.objects.select_for_update(),
                id_tasa=id_tasa,
                vigente=True,
            )
            precio_compra_anterior = tasa_vigente.precio_compra
            precio_venta_anterior = tasa_vigente.precio_venta

            tasa_vigente.vigente = False
            tasa_vigente.save(update_fields=["vigente"])

            usuario = request.user if request.user.is_authenticated else None
            nueva_tasa = TasaCambio.objects.create(
                moneda_origen=tasa_vigente.moneda_origen,
                moneda_destino=tasa_vigente.moneda_destino,
                precio_compra=form.cleaned_data["precio_compra"],
                precio_venta=form.cleaned_data["precio_venta"],
                vigente=True,
                modificado_por=usuario,
            )

            AuditoriaTasaCambio.objects.create(
                tasa_nueva=nueva_tasa,
                tasa_anterior=tasa_vigente,
                precio_compra_anterior=precio_compra_anterior,
                precio_venta_anterior=precio_venta_anterior,
                precio_compra_nuevo=nueva_tasa.precio_compra,
                precio_venta_nuevo=nueva_tasa.precio_venta,
                realizado_por=usuario,
            )

        messages.success(request, "Tasa de cambio modificada correctamente.")
        return redirect("cotizacion-web-list")


class TasaCambioCrearView(AnalistaCambiarioRequiredMixin, FormView):
    """Permite a analistas cambiarios y administradores crear una tasa de cambio inicial."""
    form_class = TasaCambioCrearForm
    template_name = "cotizaciones/tasa_crear_form.html"
    success_url = reverse_lazy("cotizacion-web-list")

    def get_context_data(self, **kwargs):
        """Marca el menú de cotizaciones como activo en el formulario de creación.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto del formulario con la selección del menú de cotizaciones.
        """
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cotizaciones"
        return context

    def form_valid(self, form):
        """Crea la tasa de cambio inicial del par de monedas y registra la auditoría.

        Args:
            form (TasaCambioCrearForm): Formulario validado con el par de
                monedas y los precios iniciales.

        Returns:
            django.http.HttpResponseRedirect: Redirección al listado de
            cotizaciones después de crear la tasa.
        """
        usuario = self.request.user if self.request.user.is_authenticated else None
        nueva_tasa = TasaCambio.objects.create(
            moneda_origen=form.cleaned_data["moneda_origen"],
            moneda_destino=form.cleaned_data["moneda_destino"],
            precio_compra=form.cleaned_data["precio_compra"],
            precio_venta=form.cleaned_data["precio_venta"],
            vigente=True,
            modificado_por=usuario,
        )

        AuditoriaTasaCambio.objects.create(
            tasa_nueva=nueva_tasa,
            tasa_anterior=None,
            precio_compra_anterior=None,
            precio_venta_anterior=None,
            precio_compra_nuevo=nueva_tasa.precio_compra,
            precio_venta_nuevo=nueva_tasa.precio_venta,
            realizado_por=usuario,
        )

        messages.success(self.request, "Tasa de cambio creada correctamente.")
        return super().form_valid(form)


class SimulacionConversionApiView(APIView):
    """Recibe por API solicitudes de simulación de conversiones monetarias."""
    def post(self, request):
        """Valida la solicitud y devuelve el resultado de la simulación.

        Args:
            request (rest_framework.request.Request): Solicitud con las monedas
                de origen y destino y el monto en su cuerpo.

        Returns:
            rest_framework.response.Response: Resultado de la simulación con
            estado HTTP 200.

        Raises:
            rest_framework.serializers.ValidationError: Si los datos no son
                válidos o el servicio rechaza la simulación.
        """
        serializer = SimulacionConversionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resultado = serializer.save()
        return Response(resultado, status=status.HTTP_200_OK)


class CotizacionWebListView(ListView):
    """Muestra las tasas vigentes y sus estadísticas en la interfaz web."""
    model = TasaCambio
    template_name = "cotizaciones/tasa_list.html"
    context_object_name = "tasas"

    def get_queryset(self):
        """Obtiene las tasas vigentes, filtradas opcionalmente por moneda de origen.

        Lee el parámetro GET moneda, elimina espacios en los extremos y lo
        convierte a mayúsculas antes de aplicar el filtro. Excluye las tasas
        cuya moneda de origen o destino esté deshabilitada.

        Returns:
            django.db.models.QuerySet: Tasas con sus monedas relacionadas,
            ordenadas por los códigos de origen y destino.
        """
        queryset = (
            TasaCambio.objects.filter(
                vigente=True,
                moneda_origen__activa=True,
                moneda_destino__activa=True,
            )
            .select_related("moneda_origen", "moneda_destino")
            .order_by("moneda_origen_id", "moneda_destino_id")
        )
        moneda = self.request.GET.get("moneda", "").strip().upper()

        if moneda:
            queryset = queryset.filter(moneda_origen_id=moneda)

        return queryset

    def get_context_data(self, **kwargs):
        """Añade filtros, monedas activas y estadísticas al contexto del listado.

        Calcula sobre las tasas del listado la fecha máxima de vigencia y el
        número de tasas con variación de compra o venta distinta de cero.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo, monedas disponibles, filtro,
            total de tasas, última actualización y cantidad de variaciones.
        """
        context = super().get_context_data(**kwargs)
        tasas = context["tasas"]
        ultima_actualizacion = tasas.aggregate(fecha=Max("fecha_vigencia"))["fecha"]
        variaciones = [
            tasa
            for tasa in tasas
            if tasa.variacion_compra() not in {None, 0} or tasa.variacion_venta() not in {None, 0}
        ]
        context.update(
            {
                "active_menu": "cotizaciones",
                "monedas": Moneda.objects.filter(activa=True),
                "moneda": self.request.GET.get("moneda", "").strip().upper(),
                "total_tasas": tasas.count(),
                "ultima_actualizacion": ultima_actualizacion,
                "variaciones_count": len(variaciones),
                "puede_editar_tasas": (
                    tiene_rol(self.request, "analista_cambiario")
                    or tiene_rol(self.request, "administrador")
                ),
            }
        )
        return context

def obtener_categoria_para_simulacion(request):
    """
    Obtiene la categoría aplicable a una simulación de conversión.

    Si el usuario posee un cliente activo, utiliza la categoría de dicho
    cliente. Para visitantes, usuarios sin asociación o sin cliente activo,
    utiliza la categoría minorista.

    Args:
        request (django.http.HttpRequest): Solicitud HTTP actual.

    Returns:
        str: Código de la categoría aplicable a la simulación.
    """
    if not request.user.is_authenticated:
        return CategoriaCliente.MINORISTA

    perfil = (
        UsuarioCliente.objects
        .select_related("cliente_activo")
        .filter(usuario=request.user)
        .first()
    )

    if (
        perfil
        and perfil.cliente_activo
        and perfil.cliente_activo.activo
    ):
        return perfil.cliente_activo.categoria

    return CategoriaCliente.MINORISTA

class SimulacionConversionWebView(FormView):
    """Presenta el formulario y los resultados de la simulación de conversiones."""
    template_name = "cotizaciones/simulador.html"
    form_class = SimulacionConversionForm

    def get_context_data(self, **kwargs):
        """Añade información de la simulación al contexto."""
        context = super().get_context_data(**kwargs)

        categoria = obtener_categoria_para_simulacion(self.request)

        context["active_menu"] = "cotizaciones"
        context["categoria_simulacion"] = categoria
        context["categoria_simulacion_label"] = dict(
            CategoriaCliente.choices
        ).get(categoria, categoria)

        return context

    def form_valid(self, form):
        """
        Ejecuta la simulación utilizando automáticamente la categoría
        correspondiente al cliente activo del usuario.
        """
        categoria = obtener_categoria_para_simulacion(self.request)

        try:
            resultado = simular_conversion(
                form.cleaned_data["moneda_origen"].codigo,
                form.cleaned_data["moneda_destino"].codigo,
                form.cleaned_data["monto"],
                categoria=categoria,
            )
        except SimulacionConversionError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        return self.render_to_response(
            self.get_context_data(
                form=form,
                resultado=resultado,
            )
        )


class ConfiguracionComisionUpdateView(AdminRequiredMixin, UpdateView):
    """Permite al administrador modificar las comisiones de compra y venta del sistema."""

    model = ConfiguracionComision
    form_class = ConfiguracionComisionForm
    template_name = "cotizaciones/configuracion_comision_form.html"
    success_url = reverse_lazy("configuracion_beneficios")

    def get_object(self, queryset=None):
        """Devuelve la única configuración de comisiones, creándola si no existe.

        Args:
            queryset (django.db.models.QuerySet or None): Conjunto de
                consulta propuesto por la vista base, que no se utiliza.

        Returns:
            ConfiguracionComision: Configuración vigente del sistema.
        """
        return ConfiguracionComision.obtener()

    def form_valid(self, form):
        """Registra quién modificó la configuración y confirma el guardado.

        Args:
            form (ConfiguracionComisionForm): Formulario validado con los
                nuevos porcentajes de comisión.

        Returns:
            django.http.HttpResponseRedirect: Redirección a la sección de
            configuración del sistema.
        """
        form.instance.modificado_por = self.request.user
        messages.success(
            self.request,
            "La configuración de comisiones fue actualizada correctamente.",
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """Prepara los textos y el menú del formulario de comisiones.

        Args:
            **kwargs: Datos adicionales del contexto de la vista base.

        Returns:
            dict: Contexto con el menú activo, el título y la etiqueta del botón.
        """
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_menu": "configuracion",
                "page_title": "Editar comisiones",
                "submit_label": "Guardar cambios",
            }
        )
        return context
