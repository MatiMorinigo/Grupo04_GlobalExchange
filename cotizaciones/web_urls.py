from django.urls import path

from .views import (
    CotizacionWebListView,
    MonedaWebCreateView,
    MonedaWebDeactivateView,
    MonedaWebListView,
    MonedaWebUpdateView,
    SimulacionConversionWebView,
)


urlpatterns = [
    path("", CotizacionWebListView.as_view(), name="cotizacion-web-list"),
    path("simulador/", SimulacionConversionWebView.as_view(), name="cotizacion-simulador"),
    path("monedas/", MonedaWebListView.as_view(), name="moneda-web-list"),
    path("monedas/nueva/", MonedaWebCreateView.as_view(), name="moneda-web-create"),
    path("monedas/<str:codigo>/editar/", MonedaWebUpdateView.as_view(), name="moneda-web-update"),
    path(
        "monedas/<str:codigo>/deshabilitar/",
        MonedaWebDeactivateView.as_view(),
        name="moneda-web-deactivate",
    ),
]
