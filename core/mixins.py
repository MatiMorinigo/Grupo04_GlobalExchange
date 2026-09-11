from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect

from core.keycloak import tiene_rol
from usuarios.models import obtener_cliente_activo


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


class ClienteActivoRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restringe las vistas a usuarios autenticados con un cliente activo vigente."""

    def test_func(self):
        """Evalúa si el usuario autenticado tiene un cliente activo vigente.

        Returns:
            bool: True si el usuario tiene un cliente activo y este está
            habilitado.
        """
        return obtener_cliente_activo(self.request.user) is not None

    def handle_no_permission(self):
        """Redirige a los usuarios sin cliente activo en lugar de mostrar un error 403.

        Returns:
            django.http.HttpResponseRedirect: Redirección al login si el
            usuario no está autenticado, o al menú principal con un mensaje
            informativo si está autenticado pero no tiene cliente activo.
        """
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.info(
            self.request,
            "Necesitás tener un cliente activo asociado para acceder a esta sección.",
        )
        return redirect("home")