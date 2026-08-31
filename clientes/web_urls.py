from django.urls import path

from .views import (
    ClienteWebCreateView,
    ClienteWebDeactivateView,
    ClienteWebDetailView,
    ClienteWebListView,
    ClienteWebUpdateView,
)


urlpatterns = [
    path("", ClienteWebListView.as_view(), name="cliente-web-list"),
    path("nuevo/", ClienteWebCreateView.as_view(), name="cliente-web-create"),
    path("<int:id_cliente>/", ClienteWebDetailView.as_view(), name="cliente-web-detail"),
    path("<int:id_cliente>/editar/", ClienteWebUpdateView.as_view(), name="cliente-web-update"),
    path(
        "<int:id_cliente>/desactivar/",
        ClienteWebDeactivateView.as_view(),
        name="cliente-web-deactivate",
    ),
]
