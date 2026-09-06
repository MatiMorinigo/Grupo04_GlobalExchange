from django.urls import path

from .views import (
    MetodoPagoDetailView,
    MetodoPagoHabilitadosView,
    MetodoPagoListCreateView,
)

urlpatterns = [
    # Listado y creación
    path(
        "metodos-pago/",
        MetodoPagoListCreateView.as_view(),
        name="metodopago-list-create",
    ),
    # Detalle y actualización
    path(
        "metodos-pago/<int:id_metodo_pago>/",
        MetodoPagoDetailView.as_view(),
        name="metodopago-detail",
    ),
    # Solo habilitados — consumido por operaciones cambiarias (CA-4 / HU27)
    path(
        "metodos-pago/habilitados/",
        MetodoPagoHabilitadosView.as_view(),
        name="metodopago-habilitados",
    ),
]
