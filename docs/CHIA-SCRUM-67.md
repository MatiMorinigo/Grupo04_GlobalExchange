# CHIA - SCRUM-67: Segmentación de clientes

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó ChatGPT como apoyo durante la implementación de la segmentación de clientes en la API.

La asistencia incluyó:
- Análisis del requerimiento de CRUD con segmentación.
- Definición de filtros aplicables al listado de clientes.
- Implementación del filtrado mediante parámetros de consulta.
- Segmentación de clientes por categoría.
- Segmentación de clientes por tipo.
- Segmentación de clientes por estado activo/inactivo.
- Combinación de múltiples filtros en una misma consulta.
- Pruebas de los filtros utilizando distintos clientes registrados.

## Decisiones tomadas con asistencia de IA
- Se decidió implementar la segmentación sobre el endpoint existente de consulta de clientes.
- Se utilizaron parámetros de consulta (`query params`) para evitar crear endpoints adicionales.
- Se permitió filtrar por `categoria`, `tipo` y `activo`.
- Los filtros pueden utilizarse individualmente o combinarse.
- Se mantuvo el comportamiento original del endpoint cuando no se proporciona ningún filtro.
- Para el filtro `activo`, se utilizó `.lower()` para evitar problemas por diferencias entre mayúsculas y minúsculas en valores como `true`, `TRUE` o `True`.
- La construcción de las consultas con filtros quedará a cargo del frontend.