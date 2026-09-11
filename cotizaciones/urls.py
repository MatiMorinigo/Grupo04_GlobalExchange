from django.urls import path

from .views import (
    MonedaListView,
    SimulacionConversionApiView,
    TasaCambioDetailView,
    TasaCambioListView,
    TasaCambioParVigenteView,
)


urlpatterns = [
    path("monedas/", MonedaListView.as_view(), name="cotizacion-moneda-list"),
    path("simulaciones/", SimulacionConversionApiView.as_view(), name="cotizacion-simulacion-create"),
    path("tasas/", TasaCambioListView.as_view(), name="cotizacion-tasa-list"),
    path("tasas/<int:id_tasa>/", TasaCambioDetailView.as_view(), name="cotizacion-tasa-detail"),
    path(
        "tasas/<str:moneda_origen>/<str:moneda_destino>/",
        TasaCambioParVigenteView.as_view(),
        name="cotizacion-tasa-par-vigente",
    ),
]
