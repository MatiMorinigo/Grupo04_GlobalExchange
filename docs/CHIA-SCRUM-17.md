# CHIA - SCRUM-17: Integración base con Keycloak

## Herramienta utilizada
Claude (Anthropic) - claude.ai

## Enlace a la conversación
[Conversación con Claude](https://claude.ai)

## Resumen de la asistencia
Se utilizó IA para guiar la configuración e integración de Keycloak con Django, incluyendo:
- Instalación y configuración de Docker y Keycloak
- Creación del Realm, Client y Roles en Keycloak
- Configuración de autoregistro y verificación de correo con Mailtrap
- Integración OIDC con Django usando mozilla-django-oidc
- Configuración de settings.py, urls.py y variables de entorno
- Configuración de Docker Compose para el equipo

## Decisiones tomadas con asistencia de IA
- Usar `mozilla-django-oidc` como librería de integración OIDC
- Usar Mailtrap para pruebas de correo en desarrollo
- Usar Docker Compose con volumen persistente para Keycloak
- Exportar el realm de Keycloak para compartir configuración con el equipo