from django.urls import path

from .views import (
    ClienteCreateView,
    ClienteListView,
    ClienteDetailView,
)

urlpatterns = [
    path("clientes/", ClienteListView.as_view(), name="cliente-list"),
    path(
        "clientes/<int:id_cliente>/",
        ClienteDetailView.as_view(),
        name="cliente-detail",
    ),
    path(
        "clientes/crear/",
        ClienteCreateView.as_view(),
        name="cliente-create",
    ),
]