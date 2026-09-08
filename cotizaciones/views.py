from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.views.generic import FormView, ListView
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import SimulacionConversionForm
from .models import Moneda, TasaCambio
from .serializers import MonedaSerializer, SimulacionConversionSerializer, TasaCambioSerializer
from .services import SimulacionConversionError, simular_conversion
from clientes.models import CategoriaCliente
from usuarios.models import UsuarioCliente

class MonedaListView(generics.ListAPIView):
    """Expone por API el listado de monedas activas."""
    queryset = Moneda.objects.filter(activa=True)
    serializer_class = MonedaSerializer


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
        convierte a mayúsculas antes de aplicar el filtro.

        Returns:
            django.db.models.QuerySet: Tasas con sus monedas relacionadas,
            ordenadas por los códigos de origen y destino.
        """
        queryset = (
            TasaCambio.objects.filter(vigente=True)
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
