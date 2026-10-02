from django.urls import path

from .views import (
    ConfiguracionComisionUpdateView,
    CotizacionWebListView,
    MonedaWebActivateView,
    MonedaWebCreateView,
    MonedaWebDeactivateView,
    MonedaWebListView,
    MonedaWebUpdateView,
    SimulacionConversionWebView,
    TasaCambioCrearView,
    TasaCambioEditarView,
)


urlpatterns = [
    path("", CotizacionWebListView.as_view(), name="cotizacion-web-list"),
    path("simulador/", SimulacionConversionWebView.as_view(), name="cotizacion-simulador"),
    path("tasas/nueva/", TasaCambioCrearView.as_view(), name="tasa-web-crear"),
    path("tasas/<int:id_tasa>/editar/", TasaCambioEditarView.as_view(), name="tasa-web-editar"),
    path("monedas/", MonedaWebListView.as_view(), name="moneda-web-list"),
    path("monedas/nueva/", MonedaWebCreateView.as_view(), name="moneda-web-create"),
    path("monedas/<str:codigo>/editar/", MonedaWebUpdateView.as_view(), name="moneda-web-update"),
    path(
        "monedas/<str:codigo>/deshabilitar/",
        MonedaWebDeactivateView.as_view(),
        name="moneda-web-deactivate",
    ),
    path(
        "monedas/<str:codigo>/habilitar/",
        MonedaWebActivateView.as_view(),
        name="moneda-web-activate",
    ),
    path(
        "configuracion-comisiones/editar/",
        ConfiguracionComisionUpdateView.as_view(),
        name="configuracion-comisiones-editar",
    ),
]
