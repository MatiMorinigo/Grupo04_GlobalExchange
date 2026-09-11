from django.urls import path

from .views import (
    MetodoPagoActivarView,
    MetodoPagoDesactivarView,
    MetodoPagoDetailView,
    MetodoPagoListCreateView,
)

urlpatterns = [
    path("metodos-pago/", MetodoPagoListCreateView.as_view(), name="metodopago-list-create"),
    path("metodos-pago/<int:id_metodo_pago>/", MetodoPagoDetailView.as_view(), name="metodopago-detail"),
    path(
        "metodos-pago/<int:id_metodo_pago>/desactivar/",
        MetodoPagoDesactivarView.as_view(),
        name="metodopago-desactivar",
    ),
    path(
        "metodos-pago/<int:id_metodo_pago>/activar/",
        MetodoPagoActivarView.as_view(),
        name="metodopago-activar",
    ),
]
