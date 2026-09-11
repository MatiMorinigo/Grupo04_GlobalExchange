# CHIA - SCRUM-56: Configuración de beneficios y límites por categoría

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia

Se utilizó asistencia de IA durante el análisis, diseño e implementación de la funcionalidad de configuración de beneficios y límites mensuales por categoría de cliente.

La asistencia incluyó la definición de la regla de negocio, el diseño del modelo de configuración, validaciones, integración con la interfaz administrativa y adaptación del simulador de conversiones para utilizar automáticamente la categoría del cliente asociado.

## Decisiones tomadas con asistencia de IA

- Se reemplazó conceptualmente el término "descuento" por "beneficio", ya que el tratamiento debe favorecer al cliente tanto en operaciones de compra como de venta de divisas.
- En una compra de divisas por parte del cliente, el beneficio reduce el precio de venta aplicado.
- En una venta de divisas por parte del cliente, el beneficio incrementa el precio de compra aplicado.
- Se decidió expresar el límite mensual en guaraníes (PYG), debido a que las operaciones del sistema siempre involucran PYG en uno de los extremos.
- Se creó el modelo `ConfiguracionBeneficioCategoria` para almacenar:
  - categoría del cliente;
  - porcentaje de beneficio;
  - límite mensual en PYG.
- Se definió un beneficio máximo absoluto del 30% para prevenir configuraciones comerciales inválidas o errores humanos.
- El límite mensual no puede tener valores negativos.
- Se creó una migración de datos para inicializar configuraciones para las categorías:
  - Minorista;
  - Corporativo;
  - VIP.
- La configuración solamente puede ser modificada por usuarios con rol `administrador`.
- Se incorporó una pantalla para listar y editar los beneficios y límites por categoría.
- La opción "Configuración" de la barra lateral fue habilitada temporalmente como acceso directo a la configuración de beneficios.
- El simulador de conversiones fue adaptado para aplicar los beneficios configurados.
- La categoría utilizada por el simulador no es seleccionada manualmente por el usuario.
- Para usuarios con cliente activo, el sistema obtiene automáticamente la categoría del cliente asociado.
- Para visitantes o usuarios sin cliente activo, se utiliza la categoría Minorista.
- Si una simulación se encuentra completamente dentro del límite, el beneficio se aplica a la totalidad de la operación.
- Si el monto supera el límite configurado, el beneficio se aplica únicamente a la parte cubierta por el límite y el excedente utiliza la cotización normal.
- El simulador no consume ni modifica el límite mensual, ya que no genera una transacción real.
- El consumo acumulado mensual será implementado cuando exista el módulo de transacciones.
- Se mejoró el simulador para que, al seleccionar una moneda distinta de PYG como origen o destino, el otro extremo se establezca automáticamente como PYG.

## Validaciones y pruebas manuales realizadas

Se verificaron los siguientes escenarios:

- Creación automática de configuraciones para Minorista, Corporativo y VIP.
- Edición del porcentaje de beneficio y del límite mensual.
- Persistencia correcta de los valores configurados.
- Rechazo de porcentajes negativos.
- Rechazo de porcentajes superiores al 30%.
- Rechazo de límites mensuales negativos.
- Aplicación automática de la categoría del cliente activo.
- Aplicación de Minorista como categoría por defecto cuando corresponde.
- Simulación USD → PYG sin beneficio.
- Simulación USD → PYG con beneficio VIP.
- Aplicación completa del beneficio cuando el monto se encuentra dentro del límite.
- Aplicación parcial del beneficio cuando el equivalente en PYG supera el límite mensual.
- Simulación PYG → moneda extranjera aplicando el beneficio correspondiente.
- Visualización en el simulador de la categoría aplicada y del beneficio utilizado.

## Ejemplo validado

Para un cliente VIP con:

- Beneficio: 5%
- Límite mensual: 50.000.000 PYG
- Tasa de compra USD/PYG: 7.500 PYG

Se simuló una venta de USD 10.000:

- Subtotal normal: 75.000.000 PYG
- Parte cubierta por el beneficio: 50.000.000 PYG
- Beneficio aplicado: 2.500.000 PYG
- Parte excedente sin beneficio: 25.000.000 PYG
- Total estimado a recibir: 77.500.000 PYG

El sistema informó correctamente que el beneficio fue aplicado parcialmente hasta alcanzar el límite configurado.

## Consideraciones pendientes

El límite mensual actualmente representa una configuración disponible para las futuras operaciones cambiarias.

El simulador utiliza dicho límite únicamente para calcular el resultado estimado y no registra consumo acumulado. La persistencia del consumo mensual deberá implementarse junto con las transacciones reales.
