from urllib.parse import urlencode

from django.conf import settings


def keycloak_logout_url(request):
    """Construye la URL de cierre de sesión del proveedor OIDC.

    Usa el endpoint configurado o lo deriva del endpoint de autorización.
    Incluye el cliente, la redirección absoluta y, si está disponible,
    el token de identidad de la sesión.

    Args:
        request (django.http.HttpRequest): Solicitud utilizada para acceder
            a la sesión y construir la URL absoluta de retorno.

    Returns:
        str: URL del proveedor con sus parámetros, o LOGOUT_REDIRECT_URL
        cuando no se puede determinar un endpoint de cierre de sesión.
    """
    logout_endpoint = getattr(settings, "OIDC_OP_LOGOUT_ENDPOINT", "")
    if not logout_endpoint and settings.OIDC_OP_AUTHORIZATION_ENDPOINT:
        logout_endpoint = settings.OIDC_OP_AUTHORIZATION_ENDPOINT.rsplit("/", 1)[0] + "/logout"

    if not logout_endpoint:
        return settings.LOGOUT_REDIRECT_URL

    params = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL),
    }

    id_token = request.session.get("oidc_id_token")
    if id_token:
        params["id_token_hint"] = id_token

    return f"{logout_endpoint}?{urlencode(params)}"


from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class CustomOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Sincroniza el nombre y apellido del usuario desde los claims de Keycloak."""

    def create_user(self, claims):
        user = super().create_user(claims)
        user.first_name = claims.get("given_name", "") or claims.get("name", "")
        user.last_name = claims.get("family_name", "")
        user.save()
        return user

    def update_user(self, user, claims):
        user = super().update_user(user, claims)
        first_name = claims.get("given_name", "") or claims.get("name", "")
        last_name = claims.get("family_name", "")
        if first_name or last_name:
            user.first_name = first_name
            user.last_name = last_name
            user.save()
        return user

