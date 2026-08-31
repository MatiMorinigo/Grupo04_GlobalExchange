# CHIA - SCRUM-50: Registro de clientes

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó IA para guiar la implementación del registro de clientes en Django REST Framework, incluyendo:
- Creación del modelo Cliente
- Definición de los tipos de cliente: FÍSICA y JURÍDICA
- Definición de las categorías: MINORISTA, CORPORATIVO y VIP
- Configuración del campo de estado activo del cliente
- Creación del serializer para validación y transformación de datos
- Implementación del endpoint de registro mediante CreateAPIView
- Configuración de las rutas correspondientes
- Pruebas de creación de clientes mediante la API

## Decisiones tomadas con asistencia de IA
- Utilizar Django REST Framework para la implementación de la API
- Utilizar ModelSerializer para representar y validar clientes
- Mantener `id_cliente` como campo generado automáticamente
- Definir `ruc` como único para evitar clientes duplicados
- Establecer `activo=True` por defecto al registrar un cliente
- Utilizar enums mediante TextChoices para tipo y categoría de cliente