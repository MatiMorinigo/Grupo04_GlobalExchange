from django.urls import path

from .views import CotizacionWebListView, SimulacionConversionWebView


urlpatterns = [
    path("", CotizacionWebListView.as_view(), name="cotizacion-web-list"),
    path("simulador/", SimulacionConversionWebView.as_view(), name="cotizacion-simulador"),
]
