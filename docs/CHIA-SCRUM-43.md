# CHIA - SCRUM-43: Consulta de tasas de cambio vigentes

## Herramienta utilizada
Claude Code (Anthropic) - claude.com/code

## Enlace a la conversación
[Conversación con Claude Code](https://claude.ai/code/session_017ocrhJy9S18euQRqBF5m3i)

## Resumen de la asistencia
Se utilizó IA para implementar la app `cotizaciones`, encargada de exponer las tasas de cambio vigentes, incluyendo:
- Modelos `Moneda` y `TasaCambio`, con migraciones y carga inicial de monedas base
- Endpoints REST: `MonedaListView`, `TasaCambioListView` (con filtros por `vigente`, `moneda_origen` y `moneda_destino`), `TasaCambioDetailView` y `TasaCambioParVigenteView`
- Vista web `CotizacionWebListView` y template `tasa_list.html` para el listado de cotizaciones vigentes, con filtro por moneda de origen
- Cálculo de variación respecto a la tasa anterior (`tasa_anterior`, `variacion_compra`, `variacion_venta`) para mostrar en el listado web
- Registro de los nuevos modelos en el panel de administración (`cotizaciones/admin.py`)
- Suite de tests (`cotizaciones/tests.py`) cubriendo los endpoints y el modelo `TasaCambio`

## Decisiones tomadas con asistencia de IA
- Se agregó un `CheckConstraint` para impedir que la moneda de origen y destino de una tasa sean la misma
- Se agregó un `UniqueConstraint` condicionado (`condition=Q(vigente=True)`) para garantizar una única tasa vigente por par de monedas
- El filtro `vigente` del endpoint de listado acepta variantes de texto (`true/1/si/sí`, `false/0/no`) para mayor tolerancia en la consulta
- Se expuso `TasaCambioParVigenteView` como endpoint dedicado para obtener la tasa vigente de un par específico de monedas
- La vista web reutiliza el mismo queryset de tasas vigentes que la API, calculando además la fecha de última actualización y la cantidad de tasas con variación
