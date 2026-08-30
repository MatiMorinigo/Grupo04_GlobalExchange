# CHIA - SCRUM-65: Modificación de clientes

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó IA para guiar la implementación de la modificación de clientes en Django REST Framework, incluyendo:
- Extensión de la vista de detalle para permitir modificaciones
- Implementación de actualización completa mediante PUT
- Implementación de actualización parcial mediante PATCH
- Pruebas de modificación de nombre y categoría
- Validación de campos obligatorios
- Validación de categorías y tipos de cliente
- Validación de RUC único
- Manejo de clientes inexistentes mediante HTTP 404
- Personalización de mensajes de validación y error en español

## Decisiones tomadas con asistencia de IA
- Utilizar RetrieveUpdateAPIView para combinar consulta y modificación del cliente
- Mantener disponibles tanto PUT como PATCH
- Utilizar PUT para reemplazar los datos editables completos del cliente
- Utilizar PATCH para modificar únicamente campos específicos
- Mantener `id_cliente` y `activo` como campos de solo lectura en el serializer
- Utilizar UniqueValidator para impedir RUC duplicados y personalizar su mensaje
- Rechazar modificaciones con valores que no correspondan a las opciones definidas
