from django.urls import path

from .views import CotizacionWebListView, SimulacionConversionWebView, TasaCambioEditarView


urlpatterns = [
    path("", CotizacionWebListView.as_view(), name="cotizacion-web-list"),
    path("simulador/", SimulacionConversionWebView.as_view(), name="cotizacion-simulador"),
    path("tasas/<int:id_tasa>/editar/", TasaCambioEditarView.as_view(), name="tasa-web-editar"),
]
