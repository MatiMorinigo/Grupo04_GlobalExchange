from django.urls import path

from .views import (
    CompraDivisaWebCreateView,
    TransaccionComprobanteView,
    TransaccionWebDetailView,
)


urlpatterns = [
    path("compra/", CompraDivisaWebCreateView.as_view(), name="compra-web-create"),
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
