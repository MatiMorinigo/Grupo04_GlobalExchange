# CHIA - SCRUM-30: HU-37 Cierre y arqueo de caja

## Herramienta utilizada
Antigravity / Gemini

## Resumen de la asistencia
Se implementó de manera completa la historia de usuario **HU-37 — Cierre y arqueo de caja** para permitir a los cajeros registrar el conteo físico final al culminar su jornada, compararlo con el saldo teórico y detectar faltantes o sobrantes:

1. **Modelos de datos (`CierreCaja`, `DetalleCierreCaja`, `ConteoBilleteCierre`)**:
   - `CierreCaja`: Registro de cierre vinculado uno-a-uno (`OneToOneField`) a `AperturaCaja`, con fecha y hora de cierre (`timezone.now`), usuario responsable (auditoría), y observaciones opcionales.
   - `DetalleCierreCaja`: Registro consolidado por moneda con saldo teórico del sistema, saldo físico ingresado y diferencia calculada (`saldo_fisico - saldo_teorico`), identificando estado (`CUADRADO`, `FALTANTE`, `SOBRANTE`).
   - `ConteoBilleteCierre`: Desglose físico por denominación de billete con captura del valor facial, cantidad contada y subtotal.

2. **Lógica de negocio y control transaccional (`cajas/services.py`)**:
   - Función `cerrar_caja`:
     - Verificación estricta de que la caja tenga una apertura activa (`estado == ABIERTA`) y pertenezca al cajero autenticado.
     - Bloqueo concurrente mediante `select_for_update()`.
     - Cálculo del saldo físico final a partir del conteo ingresado por moneda y denominación.
     - Obtención y cálculo del saldo teórico del sistema usando la apertura y los movimientos de la jornada (`apertura.saldos_actuales`).
     - Comparación de saldos y persistencia de teórico, físico y diferencia por moneda.
     - Cierre formal de la apertura (`estado = CERRADA`, `fecha_cierre = ahora`), impidiendo nuevos movimientos transaccionales correspondientes a ese turno.

3. **Formularios e interfaz de usuario (`cajas/forms.py` y plantillas HTML)**:
   - `ConteoBilleteForm`, `BaseConteoBilleteFormSet` y `CierreCajaForm`.
   - `cierre_list.html`: Módulo de cierre de caja accesible para el cajero desde el menú lateral debajo de "Apertura de caja", con tarjetas de aperturas activas pendientes de cierre e historial de cierres previos.
   - `cierre_form.html`: Formulario interactivo con cálculo dinámico en tiempo real de subtotales, totales físicos, diferencias y estados de arqueo (cuadrado / faltante / sobrante), modal interactivo de confirmación de Bootstrap 5 en lugar de alerts/confirms nativos del navegador, y protección contra scroll accidental en campos numéricos.
   - `cierre_detail.html`: Comprobante oficial de finalización de jornada con comparativa de saldos y desglose físico completo de billetes, con función de impresión.
   - Actualización del menú lateral en `templates/base.html` ubicando "Cierre de caja" directamente debajo de "Apertura de caja" dentro de "Gestión de Caja". Flujo de cierre centralizado a través del módulo de cierre.

4. **Pruebas automatizadas (`cajas/test_cierres.py`)**:
   - 10 pruebas unitarias e integrales que cubren todos los criterios de aceptación:
     - Cierre únicamente sobre aperturas activas.
     - Conteo físico y cálculo correcto de saldos.
     - Comparación con saldo teórico (incluyendo remesas de la jornada).
     - Identificación y registro de arqueos cuadrados, faltantes y sobrantes.
     - Rechazo de movimientos posteriores tras el cierre de caja.
     - Registro de fecha, hora y usuario responsable.
     - Integración completa de formularios, vistas y listados.
