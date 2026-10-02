from django.urls import path

from .views import (
    CompraDivisaWebCreateView,
    TransaccionComprobanteView,
    TransaccionHistorialView,
    TransaccionWebDetailView,
    VentaDivisaWebCreateView,
)


urlpatterns = [
    path("compra/", CompraDivisaWebCreateView.as_view(), name="compra-web-create"),
    path("venta/", VentaDivisaWebCreateView.as_view(), name="venta-web-create"),
    path(
        "historial/",
        TransaccionHistorialView.as_view(),
        name="transaccion-web-historial",
    ),
    path(
        "<int:id_transaccion>/",
        TransaccionWebDetailView.as_view(),
        name="transaccion-web-detail",
    ),
    path(
        "<int:id_transaccion>/comprobante/",
        TransaccionComprobanteView.as_view(),
        name="transaccion-web-comprobante",
    ),
]
