# CHIA - SCRUM-57: Modificación manual de tasas de cambio

## Herramienta utilizada
Claude Code (Anthropic) - claude.com/code

## Enlace a la conversación
[Conversación con Claude Code](https://claude.ai/code)

## Resumen de la asistencia
Se utilizó IA para implementar, sobre la app `cotizaciones` ya existente, la modificación manual de tasas de cambio (HU 29):
- Un flujo web en dos pasos (`TasaCambioEditarView`): un primer envío solicita los nuevos precios de compra y venta; un segundo envío, de confirmación, aplica el cambio mostrando antes una comparación "antes/después".
- Nuevo mixin `AnalistaCambiarioRequiredMixin` en `core/mixins.py`, que habilita el acceso tanto a `analista_cambiario` como a `administrador` (rol con "acceso total al sistema" según Keycloak).
- Campo `TasaCambio.modificado_por` y modelo `AuditoriaTasaCambio` para dejar el log de auditoría explícito que exige la historia (quién, cuándo, precios antes/después).
- Botón "Editar" agregado al listado de cotizaciones vigentes (`tasa_list.html`), visible solo para administradores y analistas cambiarios.
- Registro de `AuditoriaTasaCambio` en el panel de administración como solo lectura.
- Suite de tests (`cotizaciones/tests.py`) cubriendo el flujo de dos pasos, la auditoría, la validación de precios y el control de acceso.

## Decisiones tomadas con asistencia de IA
- `TasaCambio` ya estaba diseñado como historial "append-only" (`vigente` + `fecha_vigencia` + restricción de unicidad de vigente por par + `tasa_anterior()`/`variacion_*()`). Por eso una modificación manual **no edita** la fila vigente: crea una nueva fila `TasaCambio` con los nuevos precios y `vigente=True`, y retira la anterior (`vigente=False`). Esto preserva el historial y el cálculo de variación ya existentes en el listado de cotizaciones.
- Al confirmar, primero se retira la tasa vigente (`vigente=False`) y luego se crea la nueva con `vigente=True`, en ese orden, dentro de la misma transacción: crear la nueva antes de retirar la anterior violaría momentáneamente la restricción de unicidad de tasa vigente por par de monedas.
- El campo `creado_en` (ya existente, `auto_now_add`) cubre la fecha y hora de la nueva tasa; se agregó `modificado_por` para registrar quién la generó.
- Se creó además `AuditoriaTasaCambio` como tabla explícita de log de auditoría (con precios anteriores y nuevos), separada del historial implícito de `TasaCambio`, ya que la historia pide explícitamente que la modificación "quede registrada en el log de auditoría".
- El paso de confirmación se resuelve sin estado de sesión ni tablas temporales: un campo oculto `confirmado` viaja en el propio formulario junto con los precios ingresados, y se reenvía tal cual al confirmar.
- Se usó `select_for_update()` sobre la tasa vigente al momento de confirmar, dentro de una transacción atómica, para evitar una condición de carrera si dos personas intentan modificar la misma tasa al mismo tiempo; si la tasa ya no está vigente en ese momento, la operación falla con 404 en vez de crear un estado inconsistente.
- Se limitó el alcance a la interfaz web: no se agregó un endpoint de escritura en la API REST de `cotizaciones`, ya que la historia describe un flujo de usuario (analista cambiario) y no existía previamente ningún endpoint de escritura para `TasaCambio` que extender.

## Bug encontrado y corregido: dirección del par en `TasaCambioCrearForm`
- Al agregar `TasaCambioCrearView`/`TasaCambioCrearForm` (para permitir cargar la tasa inicial de un par), el formulario dejaba elegir **cualquier** combinación de moneda de origen y destino, incluyendo PYG como origen. Sin embargo, todo el resto del sistema (`cotizaciones/services.py::obtener_tasa_para_simulacion`, líneas 86-108, y `simular_conversion`) asume que una `TasaCambio` siempre se guarda como **moneda extranjera → PYG**, nunca al revés: busca la fila `origen=<divisa>, destino=PYG` tanto para convertir hacia PYG (con `precio_compra`) como desde PYG (con `precio_venta`, sobre esa misma fila).
- Detectado en pruebas manuales: se creó una tasa `PYG → USD` desde la web y el simulador de conversión falló con "No existe una tasa vigente para el par seleccionado", aunque existía una fila para ese par, porque el simulador la busca en la dirección `USD → PYG` y no la encuentra.
- Corrección aplicada: `TasaCambioCrearForm` ya no deja elegir la moneda de destino. Ahora solo pide la "moneda extranjera" (`moneda_origen`, con PYG excluido del queryset) y fija `moneda_destino` en PYG dentro de `clean()`, validando además que PYG exista y esté habilitada. El template `tasa_crear_form.html` refleja esto quitando el selector de destino y mostrando el texto fijo "La tasa se registrará frente al guaraní paraguayo (PYG)". Así, estructuralmente ya no se puede volver a cargar un par en la dirección incorrecta.
- La tasa `PYG → USD` cargada por error durante las pruebas se borró manualmente vía `manage.py shell` antes de este arreglo; no quedó como dato de prueba ni fixture.

## Validaciones realizadas
- `python manage.py test cotizaciones` (38 tests, incluye la creación de tasas y su corrección) y `python manage.py test clientes` (14 tests, regresión) en verde.
- `python manage.py makemigrations --check` sin cambios pendientes.
