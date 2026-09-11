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
