from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from core.keycloak import tiene_rol
from .services import obtener_cajero_autenticado


class CajeroRequiredMixin(LoginRequiredMixin):
    """Identidad y rol obtenidos del mismo token OIDC verificado."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.cajero_id = obtener_cajero_autenticado(request)
        return super().dispatch(request, *args, **kwargs)


class AdminOTesoreroRequiredMixin(UserPassesTestMixin):
    """Restringe el acceso a administradores y tesoreros."""

    def test_func(self):
        return (
            tiene_rol(self.request, "administrador")
            or tiene_rol(self.request, "tesorero")
        )
