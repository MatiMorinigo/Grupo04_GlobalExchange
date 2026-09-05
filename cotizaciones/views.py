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


class MonedaListView(generics.ListAPIView):
    queryset = Moneda.objects.filter(activa=True)
    serializer_class = MonedaSerializer


class TasaCambioListView(generics.ListAPIView):
    serializer_class = TasaCambioSerializer

    def get_queryset(self):
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
    queryset = TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
    serializer_class = TasaCambioSerializer
    lookup_field = "id_tasa"


class TasaCambioParVigenteView(generics.RetrieveAPIView):
    serializer_class = TasaCambioSerializer

    def get_object(self):
        return get_object_or_404(
            TasaCambio.objects.select_related("moneda_origen", "moneda_destino"),
            moneda_origen_id=self.kwargs["moneda_origen"].upper(),
            moneda_destino_id=self.kwargs["moneda_destino"].upper(),
            vigente=True,
        )


class SimulacionConversionApiView(APIView):
    def post(self, request):
        serializer = SimulacionConversionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resultado = serializer.save()
        return Response(resultado, status=status.HTTP_200_OK)


class CotizacionWebListView(ListView):
    model = TasaCambio
    template_name = "cotizaciones/tasa_list.html"
    context_object_name = "tasas"

    def get_queryset(self):
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


class SimulacionConversionWebView(FormView):
    template_name = "cotizaciones/simulador.html"
    form_class = SimulacionConversionForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "cotizaciones"
        return context

    def form_valid(self, form):
        try:
            resultado = simular_conversion(
                form.cleaned_data["moneda_origen"].codigo,
                form.cleaned_data["moneda_destino"].codigo,
                form.cleaned_data["monto"],
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
