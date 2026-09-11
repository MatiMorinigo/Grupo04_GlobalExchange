# CHIA - SCRUM-51: Gestión de monedas admitidas

## Herramienta utilizada
Claude Code (Anthropic) - claude.com/code

## Enlace a la conversación
[Conversación con Claude Code](https://claude.ai/code)

## Resumen de la asistencia
Se utilizó IA para implementar, sobre la app `cotizaciones` ya existente, la gestión administrativa de monedas admitidas (HU 26):
- CRUD web de `Moneda` para administradores: `MonedaWebListView`, `MonedaWebCreateView`, `MonedaWebUpdateView` y `MonedaWebDeactivateView`, siguiendo el mismo patrón ya usado por el equipo para `Cliente` (`clientes/views.py`).
- Modelo `AuditoriaMoneda` (con `AccionAuditoriaMoneda` y un manager `registrar(...)`) para dejar trazabilidad de cada creación, modificación y deshabilitación de una moneda: quién la realizó y los datos antes/después.
- Registro de `AuditoriaMoneda` en el panel de administración como solo lectura.
- Corrección de una brecha respecto a la HU: `cotizaciones/services.py::obtener_tasa_para_simulacion` y `CotizacionWebListView.get_queryset()` no excluían las tasas de una moneda deshabilitada; ahora ambas filtran por `activa=True` en las dos monedas del par.
- Enlace "Monedas" agregado a la barra lateral (sección GESTIÓN, solo administradores).
- Suite de tests (`cotizaciones/tests.py`) cubriendo el CRUD, la auditoría y las dos correcciones de alcance.

## Decisiones tomadas con asistencia de IA
- No se implementó una opción para "reactivar" una moneda desde la web: se sigue el mismo patrón unidireccional que `ClienteWebDeactivateView` (el único precedente de desactivación en el proyecto). Si se necesitara reactivar una moneda, puede hacerse desde el admin de Django.
- El campo `codigo` es la clave primaria de `Moneda` y no puede modificarse una vez creada la moneda: el formulario lo deshabilita al editar.
- La auditoría se modela como una tabla dedicada (`AuditoriaMoneda`) en vez de agregar campos `modificado_por`/`modificado_en` directamente en `Moneda`, porque una edición in place no permite reconstruir qué cambió; la tabla guarda `datos_anteriores`/`datos_nuevos` como JSON para cada acción.
- `AuditoriaMonedaAdmin` deshabilita `has_add_permission` y `has_change_permission` para que el historial de auditoría no pueda alterarse manualmente desde el panel de administración.
- Se detectó que el simulador de conversión y el listado de cotizaciones vigentes no verificaban `Moneda.activa`, lo cual violaba directamente el criterio de aceptación "el sistema debe utilizar únicamente monedas habilitadas en las operaciones cambiarias"; se corrigió agregando el filtro en ambos lugares, con un test de regresión para cada uno.

## Validaciones realizadas
- `python manage.py test cotizaciones` (30 tests) y `python manage.py test clientes` (14 tests, regresión) en verde.
- `python manage.py makemigrations --check` sin cambios pendientes.
