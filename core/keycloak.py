import jwt

from django.conf import settings


def obtener_roles(request):
    """Obtiene los roles de Keycloak desde el token de acceso de la sesión.

    Verifica el token con las claves del proveedor y el algoritmo RS256,
    sin validar la audiencia. Los errores de PyJWT se manejan devolviendo
    una lista vacía.

    Args:
        request (django.http.HttpRequest): Solicitud con el usuario y la sesión.

    Returns:
        list[str]: Roles del reino incluidos en el token, o una lista vacía
        si no hay usuario autenticado, token o roles, o si falla su validación.
    """
    if not request.user or not request.user.is_authenticated:
        return []

    access_token = request.session.get("oidc_access_token")

    if not access_token:
        return []

    try:
        jwks_client = jwt.PyJWKClient(settings.OIDC_OP_JWKS_ENDPOINT)
        signing_key = jwks_client.get_signing_key_from_jwt(access_token)

        payload = jwt.decode(
            access_token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )

        return payload.get("realm_access", {}).get("roles", [])

    except jwt.PyJWTError:
        return []


def tiene_rol(request, rol):
    """Comprueba si el usuario de la solicitud tiene un rol del reino.

    Args:
        request (django.http.HttpRequest): Solicitud con el usuario y la sesión.
        rol (str): Nombre del rol que se desea comprobar.

    Returns:
        bool: True si el rol está entre los obtenidos del token de acceso.
    """
    return rol in obtener_roles(request)
