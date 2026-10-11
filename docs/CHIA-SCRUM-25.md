# CHIA - SCRUM-25: Asignación de cajero a caja y turno

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó ChatGPT como apoyo durante la implementación de la historia de usuario HU-33, correspondiente a la asignación de cajeros a cajas durante turnos determinados.

La asistencia incluyó:
- Análisis de los criterios de aceptación y definición de reglas de negocio.
- Diseño del modelo `AsignacionCaja` y sus relaciones con `Caja` y los usuarios del sistema.
- Definición de horarios programados de inicio y finalización del turno.
- Integración con la API administrativa de Keycloak para consultar usuarios con rol `cajero`.
- Configuración de un cliente de servicio con permisos de consulta.
- Implementación de la validación del rol del cajero seleccionado.
- Uso del identificador UUID de Keycloak para registrar cajeros sin requerir un inicio de sesión previo.
- Implementación de formularios, vistas y rutas para registrar y consultar asignaciones.
- Creación de interfaces HTML utilizando Bootstrap y AdminLTE.
- Implementación de restricciones para impedir superposiciones horarias.
- Incorporación de restricciones `ExclusionConstraint` de PostgreSQL.
- Configuración de la extensión `btree_gist`.
- Manejo de errores de integridad durante registros simultáneos.
- Desarrollo y ejecución de pruebas automatizadas.

## Decisiones tomadas con asistencia de IA
- Se decidió reutilizar la aplicación Django `cajas`, creada durante SCRUM-22.
- Se estableció que solamente administradores y tesoreros pueden registrar asignaciones.
- Se determinó que únicamente usuarios con el rol `cajero` en Keycloak pueden ser asignados.
- Se decidió consultar los cajeros directamente desde Keycloak mediante su API administrativa.
- Se utilizó un cliente de servicio independiente con permisos `view-users` y `view-realm`.
- Se utilizó el UUID de Keycloak como identificador estable del cajero, conservando también su nombre de usuario.
- Se separó el horario programado del turno de la apertura y el cierre efectivo de caja.
- Se impidió asignar un mismo cajero a dos cajas durante horarios superpuestos.
- Se impidió asignar dos cajeros a una misma caja durante horarios superpuestos.
- Se permitió registrar turnos consecutivos sin superposición.
- Se estableció que solamente pueden asignarse cajas pertenecientes a sucursales habilitadas.
- Se incorporaron restricciones en PostgreSQL para proteger la integridad de los datos ante operaciones concurrentes.
- Se decidió conservar el historial de asignaciones para identificar a los responsables de cada turno.

## Pruebas realizadas
- Se verificó la creación de asignaciones válidas.
- Se comprobó el rechazo de horarios superpuestos para una misma caja.
- Se comprobó el rechazo de asignaciones simultáneas de un mismo cajero en distintas cajas.
- Se verificó la aceptación de turnos consecutivos.
- Se comprobó la validación de fechas y cajas inactivas.
- Se probaron directamente las restricciones de PostgreSQL sin ejecutar `full_clean()`.
- Se verificó la consulta de cajeros y sus roles mediante Keycloak.
- Se comprobaron los permisos de acceso de administradores y tesoreros.
- Se verificó el rechazo de usuarios que no tienen el rol `cajero`.
- Se realizaron pruebas manuales de registro y consulta desde el navegador.
- Se ejecutaron satisfactoriamente 20 tests del módulo `cajas`.
- Se ejecutó la suite general del proyecto, con 253 tests aprobados.

## Resultado
Se implementó la funcionalidad de asignación de cajeros a cajas durante turnos programados, incorporando integración con Keycloak, validaciones de negocio, restricciones de integridad en PostgreSQL e interfaces web.

La implementación establece una base para SCRUM-26, correspondiente a la apertura de caja con inventario inicial, y para las funcionalidades posteriores de movimientos de efectivo, cierre y arqueo.