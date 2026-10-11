
import requests

from django.conf import settings

from uuid import UUID

class KeycloakServiceError(Exception):
    """Error al consultar la API administrativa de Keycloak."""


def obtener_token_servicio():
    """Obtiene un token de acceso para consultar Keycloak."""

    url = (
        f"{settings.KEYCLOAK_BASE_URL}/realms/"
        f"{settings.KEYCLOAK_REALM}/protocol/"
        "openid-connect/token"
    )

    respuesta = requests.post(
        url,
        data={"grant_type": "client_credentials"},
        auth=(
            settings.KEYCLOAK_SERVICE_CLIENT_ID,
            settings.KEYCLOAK_SERVICE_CLIENT_SECRET,
        ),
        timeout=10,
    )

    respuesta.raise_for_status()
    return respuesta.json()["access_token"]


def obtener_cajeros_keycloak():
    """Obtiene usuarios con el rol de realm 'cajero'."""

    try:
        token = obtener_token_servicio()

        url = (
            f"{settings.KEYCLOAK_BASE_URL}/admin/realms/"
            f"{settings.KEYCLOAK_REALM}/roles/cajero/users"
        )

        cajeros = []
        pagina = 0
        tamanio_pagina = 100

        while True:
            respuesta = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "first": pagina,
                    "max": tamanio_pagina,
                },
                timeout=10,
            )

            respuesta.raise_for_status()
            usuarios = respuesta.json()

            for usuario in usuarios:
                if usuario.get("enabled", False):
                    cajeros.append({
                        "id": usuario["id"],
                        "username": usuario["username"],
                        "nombre": usuario.get("firstName", ""),
                        "apellido": usuario.get("lastName", ""),
                        "email": usuario.get("email", ""),
                    })

            if len(usuarios) < tamanio_pagina:
                break

            pagina += tamanio_pagina

        return cajeros

    except (requests.RequestException, ValueError, KeyError) as error:
        raise KeycloakServiceError(
            "No se pudo obtener la lista de cajeros desde Keycloak."
        ) from error


def obtener_cajero_verificado(cajero_id):
    """
    Comprueba que el usuario exista, esté habilitado
    y tenga el rol 'cajero' en Keycloak.

    Devuelve sus datos si es válido; de lo contrario, None.
    """

    try:
        cajero_id = str(UUID(str(cajero_id)))
    except (ValueError, TypeError, AttributeError):
        return None

    try:
        token = obtener_token_servicio()

        url_base = (
            f"{settings.KEYCLOAK_BASE_URL}/admin/realms/"
            f"{settings.KEYCLOAK_REALM}/users/{cajero_id}"
        )

        headers = {
            "Authorization": f"Bearer {token}"
        }

        # Comprobar existencia y estado del usuario.
        respuesta = requests.get(
            url_base,
            headers=headers,
            timeout=10
        )

        if respuesta.status_code == 404:
            return None

        respuesta.raise_for_status()
        usuario = respuesta.json()

        if not usuario.get("enabled", False):
            return None

        # Consultar los roles efectivos del usuario.
        respuesta_roles = requests.get(
            f"{url_base}/role-mappings/realm/composite",
            headers=headers,
            timeout=10
        )

        respuesta_roles.raise_for_status()
        roles = respuesta_roles.json()

        if not any(
            rol.get("name") == "cajero"
            for rol in roles
        ):
            return None

        return {
            "id": usuario["id"],
            "username": usuario["username"],
        }

    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        raise KeycloakServiceError(
            "No se pudo verificar el cajero en Keycloak."
        ) from error
