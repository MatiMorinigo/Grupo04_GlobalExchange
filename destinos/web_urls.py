from django.urls import path

from .views import (
    DestinoWebActivateView,
    DestinoWebCreateView,
    DestinoWebDeactivateView,
    DestinoWebDeleteView,
    DestinoWebListView,
    DestinoWebUpdateView,
)


urlpatterns = [
    path("", DestinoWebListView.as_view(), name="destino-web-list"),
    path("nuevo/", DestinoWebCreateView.as_view(), name="destino-web-create"),
    path("<int:id_destino>/editar/", DestinoWebUpdateView.as_view(), name="destino-web-update"),
    path(
        "<int:id_destino>/desactivar/",
        DestinoWebDeactivateView.as_view(),
        name="destino-web-deactivate",
    ),
    path(
        "<int:id_destino>/activar/",
        DestinoWebActivateView.as_view(),
        name="destino-web-activate",
    ),
    path(
        "<int:id_destino>/eliminar/",
        DestinoWebDeleteView.as_view(),
        name="destino-web-delete",
    ),
]
