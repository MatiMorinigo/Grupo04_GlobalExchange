# CHIA - SCRUM-24: HU-21 Consulta del historial de transacciones

## Herramienta utilizada
OpenAI Codex

## Enlace a la conversacion
[Conversacion con Codex](https://chatgpt.com/codex)

## Resumen de la asistencia
Se utilizo IA para implementar el historial web de transacciones sobre el
modelo `Transaccion` compartido por las operaciones cambiarias. El trabajo
incluye:

- Listado paginado con identificador, fecha, cliente, tipo, moneda, monto,
  tasa, comision, total y estado.
- Filtros por cliente, rango de fechas, tipo de operacion y estado.
- Consulta limitada al cliente activo para usuarios comunes.
- Consulta general para administradores y analistas cambiarios.
- Acceso al detalle con la misma politica de autorizacion del historial.
- Detalle adaptable a compras y ventas.
- Visualizacion de operaciones canceladas sin permitir editarlas ni borrarlas.
- Pruebas de aceptacion agregadas al final de `transacciones/tests.py`.

## Decisiones tomadas con asistencia de IA

- **La HU-21 no depende del formulario de venta.** El historial consulta el
  modelo comun `Transaccion`. Las pruebas crean una venta valida directamente
  para comprobar que aparecera cuando el flujo de venta empiece a persistirla.
- **Una sola politica protege listado, detalle y comprobante.** Los roles
  `administrador` y `analista_cambiario` reciben alcance general; los demas
  usuarios quedan limitados al cliente activo. Esto evita acceso por URL a una
  transaccion ajena.
- **Los filtros usan parametros GET.** La consulta puede compartirse,
  actualizarse y paginarse sin producir modificaciones en la base de datos.
- **El cliente no es un filtro para usuarios comunes.** Aunque se agregue un
  identificador de otro cliente manualmente a la URL, el queryset permanece
  restringido al cliente activo.
- **No se agregaron endpoints de edicion o eliminacion.** El historial y el
  detalle son exclusivamente de consulta, y las solicitudes POST al listado
  son rechazadas por la vista.
- **No se modifico el modelo ni se genero una migracion.** Los campos e indices
  requeridos ya estaban disponibles en `Transaccion`.

## Validaciones realizadas

- `git diff --check` sin errores.
- Revision estatica de rutas, permisos, formularios y balance de bloques de
  las plantillas Django.
- La ejecucion de `python manage.py test transacciones`, `python manage.py
  check` y `python manage.py makemigrations --check --dry-run` queda pendiente:
  el entorno local disponible no tiene Python ni Docker instalados.
