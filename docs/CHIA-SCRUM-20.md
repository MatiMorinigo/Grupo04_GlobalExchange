# CHIA - SCRUM-20: Acceso a funcionalidades según roles y permisos

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó ChatGPT como apoyo durante la implementación del control de acceso a funcionalidades según roles y permisos utilizando Keycloak y Django REST Framework.

La asistencia incluyó:
- Verificación de los roles configurados en Keycloak.
- Asignación y prueba del rol `administrador`.
- Comprobación de que los roles fueran incluidos en el token emitido por Keycloak.
- Configuración para almacenar el access token OIDC en la sesión de Django.
- Implementación de una clase de permiso personalizada para validar el rol `administrador`.
- Validación de la firma del token JWT mediante el endpoint JWKS de Keycloak.
- Protección de los endpoints CRUD de clientes utilizando permisos de Django REST Framework.
- Diagnóstico de un problema causado por la expiración del access token.
- Configuración de la renovación de la sesión OIDC para evitar el uso de tokens expirados.
- Pruebas de acceso con un usuario administrador y con un usuario sin permisos de administrador.

## Decisiones tomadas con asistencia de IA
- Se decidió que la autorización debía realizarse en el backend y no depender únicamente del frontend.
- Se creó una clase personalizada `EsAdministrador` basada en `BasePermission` de Django REST Framework.
- Se decidió restringir el CRUD de clientes al rol `administrador`.
- Se utilizó el claim `realm_access.roles` del token de Keycloak para obtener los roles del usuario.
- Se configuró `OIDC_STORE_ACCESS_TOKEN = True` para almacenar el access token en la sesión de Django.
- Se mantuvo la validación criptográfica del JWT utilizando las claves públicas obtenidas desde el endpoint JWKS de Keycloak.
- Se configuró `OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = 240` para renovar la sesión antes de que el token utilizado para la autorización expire.
- Los usuarios autenticados sin el rol `administrador` reciben una respuesta `403 Forbidden`.
- Los usuarios con el rol `administrador` pueden acceder normalmente a los endpoints protegidos.