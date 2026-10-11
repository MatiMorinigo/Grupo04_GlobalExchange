# CHIA - SCRUM-22: Gestión de sucursales y cajas

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó ChatGPT como apoyo durante la implementación del módulo de gestión de sucursales y cajas físicas de Global Exchange.

La asistencia incluyó:
- Análisis de la historia de usuario HU-31 y sus criterios de aceptación.
- Diseño de los modelos `Sucursal` y `Caja` y sus relaciones.
- Creación de la aplicación Django `cajas`.
- Generación y aplicación de la migración inicial en PostgreSQL.
- Implementación de formularios para registrar y modificar sucursales y cajas.
- Implementación de vistas basadas en clases para listar, crear, modificar y deshabilitar sucursales.
- Implementación de vistas para listar, crear, modificar, habilitar y deshabilitar cajas.
- Integración de las rutas del módulo con el sistema existente.
- Creación de plantillas HTML utilizando Bootstrap y AdminLTE.
- Integración de permisos mediante roles de Keycloak.
- Implementación de validaciones de negocio para mantener la consistencia entre sucursales y cajas.
- Desarrollo de pruebas automatizadas y verificación del funcionamiento desde el navegador.

## Decisiones tomadas con asistencia de IA
- Se decidió crear una aplicación Django independiente denominada `cajas`, para organizar las funcionalidades del módulo.
- Se estableció una relación de uno a muchos entre `Sucursal` y `Caja`.
- Se utilizó `on_delete=models.PROTECT` para impedir eliminar sucursales que tengan cajas asociadas.
- Se implementó una restricción de unicidad para evitar códigos de caja duplicados dentro de una misma sucursal.
- Se utilizó un campo booleano `activa` para permitir la deshabilitación lógica sin eliminar registros.