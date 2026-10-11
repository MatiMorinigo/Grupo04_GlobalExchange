from django.urls import path

from .views import (
    CompraDivisaWebCreateView,
    PagoSimuladoListView,
    PagoSimuladoResolverView,
    TransaccionComprobanteView,
    TransaccionHistorialView,
    TransaccionIniciarPagoView,
    TransaccionWebDetailView,
    VentaDivisaWebCreateView,
    webhook_stripe,
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
    path(
        "<int:id_transaccion>/pagar/",
        TransaccionIniciarPagoView.as_view(),
        name="transaccion-web-iniciar-pago",
    ),
    path("webhooks/stripe/", webhook_stripe, name="webhook-stripe"),
    path("pagos-simulados/", PagoSimuladoListView.as_view(), name="pago-simulado-list"),
    path(
        "pagos-simulados/<int:id_pago>/resolver/",
        PagoSimuladoResolverView.as_view(),
        name="pago-simulado-resolver",
    ),
]
