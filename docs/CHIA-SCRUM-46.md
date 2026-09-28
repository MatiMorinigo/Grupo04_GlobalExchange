# CHIA - SCRUM-46: Venta de divisas

## Herramienta utilizada
Antigravity AI (Google DeepMind)

## Enlace a la conversación
[Conversación con Antigravity AI](file:///)

## Resumen de la asistencia
Se utilizó IA para implementar y refinar la historia de usuario **SCRUM-46: Venta de divisas** sobre el modelo `Transaccion` de la app `transacciones`. El flujo permite a los usuarios autenticados entregar divisas (moneda extranjera) y recibir guaraníes (PYG) aplicando la cotización de compra vigente, las comisiones de venta configuradas y los beneficios correspondientes a la categoría del cliente activo.

Trabajo realizado y consolidado:
- **Formulario y Servicios**: Implementación de `VentaDivisaForm`, `calcular_venta` y `crear_transaccion_venta` en `transacciones/services.py` y `transacciones/forms.py`.
- **Vista Web**: `VentaDivisaWebCreateView` en `transacciones/views.py` para el flujo en dos pasos (carga y confirmación con detección de variaciones de cotización).
- **Plantillas Dinámicas**: Adaptación de `transaccion_detail.html` para presentar datos dinámicos según el tipo de operación (`COMPRA` o `VENTA`).
- **Navegación e Interfaz**: Integración en el menú principal (`core/views.py`) con la tarjeta unificada de Operaciones de Cambio (botones de Comprar divisas y Vender divisas) y en la barra lateral (`base.html`) con su ícono representativo `bi-arrow-left-right` y resaltado dinámico de menú.
- **Documentación y Pruebas**: Cobertura con pruebas unitarias en `core/tests.py` y `transacciones/tests.py`, y actualización del índice de Sphinx en `docs/source/transacciones.rst`.

## Decisiones tomadas con asistencia de IA

- **Uso de Tasa de Compra (`precio_compra`)**: Dado que el cliente entrega divisa y recibe PYG, el sistema aplica la tasa de compra del par divisa/PYG.
- **Fórmula de Venta**: `total_pyg = subtotal_pyg + beneficio_monto_pyg - comision_monto_pyg`. El beneficio suma a favor del cliente y la comisión de venta se descuenta del total recibido en guaraníes.
- **Flujo de Confirmación y Recálculo**: Se utiliza el campo oculto `id_tasa_vista`. Si la cotización cambia antes de confirmar, el sistema precalcula y muestra la advertencia con la nueva tasa sin generar transacciones adicionales. Si el usuario acepta, la transacción se recalcula desde cero en estado `PENDIENTE`. Si cancela, no se persiste nada o pasa a estado `CANCELADA` para trazabilidad sin pago confirmado.
- **Navegación Unificada**: El módulo "Operaciones de cambio" en el menú principal incluye dos botones distribuidos horizontalmente para "Comprar divisas" y "Vender divisas". En el menú lateral se habilitaron botones independientes con ícono dinámico e indicación visual activa.

## Criterios de aceptación cumplidos

1. **Cliente activo seleccionado**: Operación bloqueada y validada si no hay cliente activo.
2. **Selección de moneda y monto**: El usuario elige una divisa habilitada con cotización vigente y especifica el monto a entregar.
3. **Moneda entregada y recibida**: La divisa entregada es extranjera y la moneda recibida es PYG.
4. **Tasa de compra aplicada**: Se utiliza `precio_compra` vigente para el par seleccionado.
5. **Beneficios y límites operacionales**: Se aplican los beneficios según la categoría del cliente respetando límites configurados.
6. **Identificador único y estado PENDIENTE**: Al crear la transacción se le asigna su identificador y estado inicial `PENDIENTE`.
7. **Verificación de cotización pre-pago**: Detección de cambios de cotización e informe de valores recalculados antes de confirmar.
8. **Reemplazo sin duplicación**: Si se acepta la nueva cotización, la operación se recalcula reemplazando valores sin generar registros históricos ni transacciones adicionales.
9. **Trazabilidad y Cancelación**: Si se cancela antes de abonar, la transacción queda en estado `CANCELADA` (no anulada).
10. **Comisión de venta**: Se aplica el porcentaje de comisión de venta configurado en `ConfiguracionComision`.

## Validaciones realizadas

- Pruebas unitarias ejecutadas exitosamente sobre `core` y `transacciones`.
- Documentación automática generada en Sphinx sin errores ni advertencias.
