
from django.urls import path

from .views import (
    SucursalListView,
    SucursalCreateView,
    SucursalUpdateView,
    SucursalDeactivateView,
    CajaListView,
    CajaCreateView,
    CajaUpdateView,
    CajaEstadoView,
    AsignacionCajaListView,
    AsignacionCajaCreateView,
)

urlpatterns = [
    # Gestión de cajas
    path("", CajaListView.as_view(), name="caja-list"),
    path("nueva/", CajaCreateView.as_view(), name="caja-create"),
    path(
        "<int:id_caja>/editar/",
        CajaUpdateView.as_view(),
        name="caja-update",
    ),
    path(
        "<int:id_caja>/activar/",
        CajaEstadoView.as_view(),
        {"activar": True},
        name="caja-activate",
    ),
    path(
        "<int:id_caja>/desactivar/",
        CajaEstadoView.as_view(),
        {"activar": False},
        name="caja-deactivate",
    ),

    # Gestión de sucursales
    path("sucursales/", SucursalListView.as_view(), name="sucursal-list"),
    path(
        "sucursales/nueva/",
        SucursalCreateView.as_view(),
        name="sucursal-create",
    ),
    path(
        "sucursales/<int:id_sucursal>/editar/",
        SucursalUpdateView.as_view(),
        name="sucursal-update",
    ),
    path(
        "sucursales/<int:id_sucursal>/desactivar/",
        SucursalDeactivateView.as_view(),
        name="sucursal-deactivate",
    ),
    path(
        "asignaciones/",
        AsignacionCajaListView.as_view(),
        name="asignacion-list"
    ),
    path(
        "asignaciones/nueva/",
        AsignacionCajaCreateView.as_view(),
        name="asignacion-create"
    ),
]
