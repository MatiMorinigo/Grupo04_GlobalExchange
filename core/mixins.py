from django.contrib.auth.mixins import UserPassesTestMixin

from core.keycloak import tiene_rol


class AdminRequiredMixin(UserPassesTestMixin):
    """Restringe las vistas a usuarios con el rol administrador de Keycloak."""
    def test_func(self):
        """Evalúa el permiso administrativo de la solicitud actual.

        Returns:
            bool: True si el usuario tiene el rol administrador.
        """
        return tiene_rol(self.request, "administrador")