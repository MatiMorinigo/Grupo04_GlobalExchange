# CHIA - SCRUM-29: HU-36 Registro de remesas de efectivo

## Herramienta utilizada
Antigravity / Gemini

## Resumen de la asistencia
Se implementó de manera completa la historia de usuario **HU-36 — Registro de remesas de efectivo** para la gestión de tesorería y abastecimiento/devolución de fondos con las cajas operativas:

1. **Modelos de datos (`Remesa` y `DetalleRemesa`)**:
   - `Remesa`: Registro inmutable con tipo de movimiento (`ENTREGA` de Tesorería a Caja o `DEVOLUCION` de Caja a Tesorería), origen y destino explícitos, relación obligatoria a la caja y a su apertura activa (`AperturaCaja`), moneda, monto total (`monto_total > 0`), usuario responsable (auditoría), fecha y hora real con marca de tiempo del sistema (`timezone.now`), y observaciones.
   - `DetalleRemesa`: Desglose detallado por denominación de billete (`DenominacionBillete`) con validación de correspondencia de moneda, captura histórica del valor facial del billete (`valor_denominacion`), cantidad positiva (`cantidad > 0`), restricción de unicidad por denominación y cálculo de subtotal.

2. **Cálculo de inventario y saldos teóricos en `AperturaCaja`**:
   - `saldos_actuales`: Propiedad que calcula el saldo teórico de la caja en tiempo real sumando entregas y restando devoluciones al saldo inicial de la apertura.
   - `obtener_saldo_actual(moneda_id)`: Consulta del saldo teórico por moneda.
   - `obtener_inventario_actual(moneda_id)`: Consulta del stock de billetes por denominación disponible en caja.

3. **Lógica de negocio y control transaccional (`cajas/services.py`)**:
   - Función `registrar_remesa`:
     - Verificación de permisos de usuario (`tesorero` o `administrador`).
     - Bloqueo transaccional de concurrencia usando `apertura_para_movimiento(caja_id)` (orden estricto `Caja -> AperturaCaja` con `select_for_update`).
     - Control estricto de egresos (Criterio 6): En devoluciones (Caja → Tesorería), el sistema valida que el monto a devolver no exceda el saldo disponible en caja y que la cantidad de billetes por denominación no supere el stock disponible en el inventario físico de la apertura.
     - Determinación automática de origen y destino coherentes.

4. **Formularios e interfaz reactiva (`cajas/forms.py` y templates)**:
   - `RemesaForm` y `DetalleRemesaFormSet` con validaciones de unicidad y cantidad.
   - Plantilla `remesa_form.html`: cálculo en tiempo real con JavaScript de subtotales, totales y filtrado dinámico de denominaciones según la moneda seleccionada.
   - Plantilla `remesa_list.html`: consulta histórica con filtros por caja, tipo de remesa, moneda y rango de fechas.
   - Plantilla `remesa_detail.html`: desglose detallado con comprobante imprimible.
   - Actualización de `apertura_detail.html`: visualización de los saldos teóricos actuales y tabla de remesas asociadas a la sesión.
   - Integración en el menú lateral (`templates/base.html`) para administradores y tesoreros.

5. **Pruebas automatizadas (`cajas/test_remesas.py`)**:
   - 10 pruebas unitarias e integrales que cubren todos los criterios de aceptación: entregas, devoluciones, actualización de saldos e inventarios, rechazo de egresos superiores a lo disponible, validación de monedas/denominaciones, control de permisos y consulta histórica.
