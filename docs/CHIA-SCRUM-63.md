# CHIA - SCRUM-63: Consulta de clientes

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó IA para guiar la implementación de la consulta de clientes mediante Django REST Framework, incluyendo:
- Implementación del listado general de clientes
- Implementación de la consulta individual por id_cliente
- Configuración de endpoints para ambas consultas
- Reutilización del ClienteSerializer existente
- Configuración de Django REST Framework en INSTALLED_APPS
- Pruebas del listado de clientes registrados
- Pruebas de consulta de un cliente específico
- Manejo de clientes inexistentes mediante HTTP 404
- Personalización del mensaje de cliente no encontrado

## Decisiones tomadas con asistencia de IA
- Utilizar ListAPIView para obtener el listado de clientes
- Utilizar RetrieveAPIView para consultar un cliente específico
- Utilizar `id_cliente` como campo de búsqueda del recurso
- Mantener la consulta de clientes activos e inactivos para conservar acceso al historial
- Devolver HTTP 404 cuando el cliente solicitado no exista
- Utilizar mensajes de error claros y en español