
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
    AperturaCajaListView,
    AperturaCajaCreateView,
    AperturaCajaDetailView,
    DenominacionBilleteListView,
    DenominacionBilleteCreateView,
    DenominacionBilleteUpdateView,
    DenominacionBilleteEstadoView,
)

urlpatterns = [
    path("denominaciones/", DenominacionBilleteListView.as_view(), name="denominacion-list"),
    path("denominaciones/nueva/", DenominacionBilleteCreateView.as_view(), name="denominacion-create"),
    path("denominaciones/<int:id_denominacion>/editar/", DenominacionBilleteUpdateView.as_view(), name="denominacion-update"),
    path("denominaciones/<int:id_denominacion>/activar/", DenominacionBilleteEstadoView.as_view(),
         {"activar": True}, name="denominacion-activate"),
    path("denominaciones/<int:id_denominacion>/desactivar/", DenominacionBilleteEstadoView.as_view(),
         {"activar": False}, name="denominacion-deactivate"),
    path("aperturas/", AperturaCajaListView.as_view(), name="apertura-list"),
    path("asignaciones/<int:id_asignacion>/abrir/", AperturaCajaCreateView.as_view(), name="apertura-create"),
    path("aperturas/<int:id_apertura>/", AperturaCajaDetailView.as_view(), name="apertura-detail"),
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
