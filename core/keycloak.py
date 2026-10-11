import jwt

from django.conf import settings


def obtener_claims_verificados(request):
    """Valida el access token OIDC y comparte el resultado durante la solicitud.

    La audiencia de Keycloak puede ser ``account``; se exige en cambio el
    cliente autorizado (azp), además de firma, vencimiento, sub y emisor.
    Nunca se decodifica un token sin verificar su firma.
    """
    if not request.user or not request.user.is_authenticated:
        return {}
    if hasattr(request, "_keycloak_claims_verificados"):
        return request._keycloak_claims_verificados
    payload = {}
    token = request.session.get("oidc_access_token")
    endpoint = settings.OIDC_OP_AUTHORIZATION_ENDPOINT or ""
    issuer = endpoint.partition("/protocol/openid-connect/")[0]
    if token and issuer and settings.OIDC_RP_CLIENT_ID:
        try:
            client = jwt.PyJWKClient(settings.OIDC_OP_JWKS_ENDPOINT)
            key = client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token, key.key, algorithms=["RS256"], issuer=issuer,
                options={"verify_aud": False, "require": ["exp", "sub", "iss"]},
            )
            if payload.get("azp") != settings.OIDC_RP_CLIENT_ID:
                payload = {}
        except jwt.PyJWTError:
            payload = {}
    request._keycloak_claims_verificados = payload
    return payload


def obtener_roles(request):
    """Obtiene los roles de Keycloak desde el token de acceso de la sesión.

    Reutiliza los claims verificados (firma RS256, emisor, cliente y expiración).

    Args:
        request (django.http.HttpRequest): Solicitud con el usuario y la sesión.

    Returns:
        list[str]: Roles del reino incluidos en el token, o una lista vacía
        si no hay usuario autenticado, token o roles, o si falla su validación.
    """
    payload = obtener_claims_verificados(request)
    realm_access = payload.get("realm_access")
    roles = realm_access.get("roles") if isinstance(realm_access, dict) else None
    return roles if isinstance(roles, list) else []


def tiene_rol(request, rol):
    """Comprueba si el usuario de la solicitud tiene un rol del reino.

    Args:
        request (django.http.HttpRequest): Solicitud con el usuario y la sesión.
        rol (str): Nombre del rol que se desea comprobar.

    Returns:
        bool: True si el rol está entre los obtenidos del token de acceso.
    """
    return rol in obtener_roles(request)
