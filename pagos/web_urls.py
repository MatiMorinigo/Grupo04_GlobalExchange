from django.urls import path

from .views import (
    MetodoPagoWebActivateView,
    MetodoPagoWebCreateView,
    MetodoPagoWebDeactivateView,
    MetodoPagoWebDeleteView,
    MetodoPagoWebListView,
    MetodoPagoWebUpdateView,
)

urlpatterns = [
    path("", MetodoPagoWebListView.as_view(), name="metodopago-web-list"),
    path("nuevo/", MetodoPagoWebCreateView.as_view(), name="metodopago-web-create"),
    path("<int:id_metodo_pago>/editar/", MetodoPagoWebUpdateView.as_view(), name="metodopago-web-update"),
    path(
        "<int:id_metodo_pago>/desactivar/",
        MetodoPagoWebDeactivateView.as_view(),
        name="metodopago-web-deactivate",
    ),
    path(
        "<int:id_metodo_pago>/activar/",
        MetodoPagoWebActivateView.as_view(),
        name="metodopago-web-activate",
    ),
    path(
        "<int:id_metodo_pago>/eliminar/",
        MetodoPagoWebDeleteView.as_view(),
        name="metodopago-web-delete",
    ),
]
