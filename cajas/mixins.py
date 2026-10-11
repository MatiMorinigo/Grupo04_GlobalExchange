from django.contrib.auth.mixins import UserPassesTestMixin

from core.keycloak import tiene_rol


class AdminOTesoreroRequiredMixin(UserPassesTestMixin):
    """Restringe el acceso a administradores y tesoreros."""

    def test_func(self):
        return (
            tiene_rol(self.request, "administrador")
            or tiene_rol(self.request, "tesorero")
        )