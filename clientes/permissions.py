import jwt

from django.conf import settings
from rest_framework.permissions import BasePermission


class EsAdministrador(BasePermission):
    message = "No tiene permisos de administrador."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        access_token = request.session.get("oidc_access_token")

        if not access_token:
            return False

        try:
            jwks_client = jwt.PyJWKClient(settings.OIDC_OP_JWKS_ENDPOINT)
            signing_key = jwks_client.get_signing_key_from_jwt(access_token)

            payload = jwt.decode(
                access_token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )

            roles = payload.get("realm_access", {}).get("roles", [])

            return "administrador" in roles

        except jwt.PyJWTError:
            return False