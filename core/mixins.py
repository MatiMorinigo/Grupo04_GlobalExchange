from django.contrib.auth.mixins import UserPassesTestMixin

from core.keycloak import tiene_rol


class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return tiene_rol(self.request, "administrador")