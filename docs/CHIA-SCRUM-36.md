# CHIA - SCRUM-36: HU-05 — Solicitud de asociación a un cliente

## Herramienta utilizada
Gemini (google.com)

## Enlace a la conversación
[Conversación con Gemini](https://share.gemini.google/3GN5rUXn7TcH)

## Resumen de la asistencia
Se utilizó IA para guiar la implementación de las solicitudes de asociación de usuarios a clientes, incluyendo:
- Diseño e implementación del modelo `SolicitudAsociacion` con los estados `PENDIENTE`, `APROBADA` y `RECHAZADA`
- Creación de interfaz de búsqueda dinámica por RUC utilizando AJAX para identificar clientes activos
- Validación de existencia del cliente y control de solicitudes duplicadas pendientes o ya aprobadas
- Desarrollo de la vista `SolicitudBuscarClienteView` y vista de confirmación
- Implementación de la vista y plantilla `mis_solicitudes.html` para que el usuario consulte el historial y estado de sus solicitudes
- Registro e integración de rutas web en `usuarios/web_urls.py` y `config/urls.py`

## Decisiones tomadas con asistencia de IA
- Implementar una restricción única condicional (`UniqueConstraint`) en la base de datos para impedir múltiples solicitudes `PENDIENTES` del mismo usuario al mismo cliente
- Utilizar peticiones AJAX dinámicas para buscar por RUC antes de confirmar la solicitud, mejorando la experiencia de usuario
- Mantener las solicitudes rechazadas en la base de datos con su fecha de resolución para fines de auditoría e historial
- Restringir la visualización del formulario y componente de solicitud exclusivamente a usuarios normales, ocultándolo a los administradores
