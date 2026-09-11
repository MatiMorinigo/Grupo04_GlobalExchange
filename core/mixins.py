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


class AnalistaCambiarioRequiredMixin(UserPassesTestMixin):
    """Restringe las vistas a analistas cambiarios y administradores de Keycloak."""
    def test_func(self):
        """Evalúa si la solicitud actual puede modificar tasas de cambio.

        Returns:
            bool: True si el usuario tiene el rol analista_cambiario o
            administrador.
        """
        return tiene_rol(self.request, "analista_cambiario") or tiene_rol(self.request, "administrador")