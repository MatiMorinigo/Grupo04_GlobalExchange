from django.urls import path

from .views import (
    CompraDivisaWebCreateView,
    TransaccionAceptarNuevaTasaView,
    TransaccionCancelarView,
    TransaccionRevalidarCotizacionView,
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
        "<int:id_transaccion>/revalidar/",
        TransaccionRevalidarCotizacionView.as_view(),
        name="transaccion-web-revalidar",
    ),
    path(
        "<int:id_transaccion>/aceptar-tasa/",
        TransaccionAceptarNuevaTasaView.as_view(),
        name="transaccion-web-aceptar-tasa",
    ),
    path(
        "<int:id_transaccion>/cancelar/",
        TransaccionCancelarView.as_view(),
        name="transaccion-web-cancelar",
    ),
]
