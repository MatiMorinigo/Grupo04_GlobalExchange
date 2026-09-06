from rest_framework.permissions import BasePermission

from core.keycloak import tiene_rol


class EsAdministrador(BasePermission):
    """Restringe el acceso a usuarios con el rol administrador."""

    message = "No tiene permisos de administrador."

    def has_permission(self, request, view):
        """Comprueba si la solicitud pertenece a un administrador.

        Args:
            request (rest_framework.request.Request): Solicitud cuyo usuario y
                sesión se consultan para comprobar el rol.
            view (rest_framework.views.APIView): Vista que solicita el permiso;
                no se utiliza en esta comprobación.

        Returns:
            bool: True si el usuario tiene el rol administrador; False en caso
            contrario.
        """
        return tiene_rol(request, "administrador")
