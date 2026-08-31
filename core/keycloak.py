import jwt

from django.conf import settings


def obtener_roles(request):
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
    return rol in obtener_roles(request)
