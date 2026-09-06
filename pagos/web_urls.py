from django.urls import path

from .views import (
    MetodoPagoWebCreateView,
    MetodoPagoWebDetailView,
    MetodoPagoWebListView,
    MetodoPagoWebToggleView,
    MetodoPagoWebUpdateView,
)

urlpatterns = [
    path("", MetodoPagoWebListView.as_view(), name="metodopago-web-list"),
    path("nuevo/", MetodoPagoWebCreateView.as_view(), name="metodopago-web-create"),
    path(
        "<int:id_metodo_pago>/",
        MetodoPagoWebDetailView.as_view(),
        name="metodopago-web-detail",
    ),
    path(
        "<int:id_metodo_pago>/editar/",
        MetodoPagoWebUpdateView.as_view(),
        name="metodopago-web-update",
    ),
    path(
        "<int:id_metodo_pago>/toggle/",
        MetodoPagoWebToggleView.as_view(),
        name="metodopago-web-toggle",
    ),
]
