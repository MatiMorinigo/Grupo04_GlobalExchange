# CHIA - SCRUM-44: Simulación de conversión de moneda

## Herramienta utilizada
Claude Code (Anthropic) - claude.com/code

## Enlace a la conversación
[Conversación con Claude Code](https://claude.ai/code/session_017ocrhJy9S18euQRqBF5m3i)

## Resumen de la asistencia
Se utilizó IA para implementar el simulador de conversión de moneda sobre la app `cotizaciones`, incluyendo:
- `SimulacionConversionForm` para seleccionar moneda de origen, moneda de destino y monto a convertir
- Módulo `services.py` con `simular_conversion` y `obtener_tasa_para_simulacion`, encargados de resolver la tasa aplicable y calcular el resultado de la conversión
- Integración del simulador en `views.py` y `web_urls.py`, junto con el template `simulador.html`
- Actualización de `cotizaciones/serializers.py` y de `tasa_list.html` para reflejar los datos necesarios del simulador
- Suite de tests (`cotizaciones/tests.py`) cubriendo casos válidos e inválidos de la simulación

## Decisiones tomadas con asistencia de IA
- Se definió como regla de negocio que toda simulación debe incluir guaraníes (PYG) como moneda de origen o destino, dado que las tasas se cargan siempre contra PYG
- Se utiliza `precio_compra` cuando la moneda de destino es PYG y `precio_venta` cuando la moneda de origen es PYG, replicando la lógica de una casa de cambio
- Los montos se redondean con `ROUND_HALF_UP` a 2 decimales para evitar resultados con precisión excesiva
- El resultado de la simulación ya contempla campos de descuento (`descuento_porcentaje`, `descuento_monto`) fijados en cero, dejando la estructura preparada para una futura funcionalidad de descuentos sin requerir cambios de contrato
- Se validó que el monto a convertir sea mayor a cero y que las monedas de origen y destino sean distintas, tanto a nivel de formulario como de servicio
