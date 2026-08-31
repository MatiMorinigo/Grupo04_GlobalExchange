from django.urls import path

from .views import (
    ClienteActivoSeleccionarView,
    MisSolicitudesView,
    SolicitudAdminAprobarView,
    SolicitudAdminListView,
    SolicitudAdminRechazarView,
    SolicitudBuscarClienteView,
)

urlpatterns = [
    # Usuario normal
    path("solicitar/", SolicitudBuscarClienteView.as_view(), name="solicitar-asociacion"),
    path("mis-solicitudes/", MisSolicitudesView.as_view(), name="mis-solicitudes"),
    path("seleccionar-cliente/", ClienteActivoSeleccionarView.as_view(), name="seleccionar-cliente-activo"),

    # Administrador
    path("admin/solicitudes/", SolicitudAdminListView.as_view(), name="admin-solicitudes"),
    path("admin/solicitudes/<int:pk>/aprobar/", SolicitudAdminAprobarView.as_view(), name="admin-solicitud-aprobar"),
    path("admin/solicitudes/<int:pk>/rechazar/", SolicitudAdminRechazarView.as_view(), name="admin-solicitud-rechazar"),
]
