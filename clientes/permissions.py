from rest_framework.permissions import BasePermission

from core.keycloak import tiene_rol


class EsAdministrador(BasePermission):
    message = "No tiene permisos de administrador."

    def has_permission(self, request, view):
        return tiene_rol(request, "administrador")