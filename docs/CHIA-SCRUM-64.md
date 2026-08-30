# CHIA - SCRUM-64: Desactivación de clientes

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó IA para guiar la implementación de la desactivación lógica de clientes, incluyendo:
- Creación de un endpoint específico para desactivar clientes
- Modificación del estado `activo` de True a False
- Validación de que el cliente exista
- Validación de que el cliente se encuentre activo antes de desactivarlo
- Manejo del intento de desactivar nuevamente un cliente inactivo
- Pruebas de desactivación mediante PATCH
- Pruebas de clientes inexistentes
- Conservación del registro del cliente y su información histórica

## Decisiones tomadas con asistencia de IA
- Implementar desactivación lógica en lugar de eliminación física
- Utilizar el campo `activo` para representar el estado operativo del cliente
- Crear un endpoint específico de desactivación en lugar de permitir modificar `activo` desde el CRUD general
- No eliminar registros históricos del cliente
- Mantener disponibles los datos de clientes inactivos para consultas e historial
- Considerar la desactivación como el equivalente funcional de eliminación dentro del CRUD
- No implementar reactivación del cliente por el momento