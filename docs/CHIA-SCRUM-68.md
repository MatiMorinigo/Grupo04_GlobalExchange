# CHIA - SCRUM-68: Iniciar pago de transacción pendiente

## Historia de Usuario

**SCRUM-68 - HU-15: Iniciar pago de transacción pendiente**

Como cliente asociado quiero iniciar el pago de una transacción pendiente mediante un proveedor de pagos externo para poder completar mi operación cambiaria.

## Herramienta utilizada
Claude Code (Anthropic) - sesión local en la terminal, sin enlace público a la conversación.

## Resumen de la asistencia
Se utilizó Claude Code como apoyo durante el análisis, el diseño y la implementación de la HU-15.

La asistencia incluyó:
- Análisis de la historia de usuario, de sus criterios de aceptación y de su relación con la HU-18 (SCRUM-53, confirmación automática del pago).
- Revisión del código existente: modelo `Transaccion`, métodos de pago del cliente y flujo de compra y venta.
- Elaboración de un plan detallado. El equipo tomó las decisiones de diseño: proveedores por tipo de método de pago, uso de PaymentIntents de Stripe y asignación del token de las tarjetas de prueba.
- Implementación del modelo `Pago`, de la capa de proveedores en `integrations` y de la acción de pago en el detalle de la operación.
- Pruebas automatizadas y documentación técnica.

El código y las decisiones finales fueron revisados por el equipo y validados con las pruebas ejecutadas localmente sobre PostgreSQL.

## Decisiones tomadas con asistencia de IA

### 1. Un proveedor por tipo de método de pago
La función `get_proveedor(metodo_pago)` es el único punto que decide qué proveedor usar:
- Tarjetas de crédito y débito: **Stripe**.
- Billeteras electrónicas: **simulador de billetera**, porque Tigo Money, Personal Pay y similares no tienen una pasarela de prueba disponible.

Los dos proveedores implementan la misma interfaz (`ProveedorPagoBase`).

### 2. Stripe con PaymentIntents confirmados desde el servidor
El cliente ya elige su tarjeta registrada en la plataforma, así que no se usa Stripe Checkout ni Stripe Elements. Al iniciar el pago se crea y confirma un PaymentIntent con `confirm=True` y `allow_redirects="never"`.
- La referencia externa guardada es el identificador del PaymentIntent (`pi_...`).
- Se envía una `idempotency_key` por pago, para que un reintento de red no genere dos cobros.

### 3. Nunca se guarda el número de la tarjeta
`MetodoPago` incorpora el campo `stripe_payment_method_id`. Al registrar una tarjeta de prueba oficial de Stripe se guarda su token en lugar del número:
- `4242 4242 4242 4242` → `pm_card_visa` (aprobada).
- `4000 0000 0000 0002` → `pm_card_chargeDeclined` (rechazada).
- `4000 0000 0000 9995` → `pm_card_chargeDeclinedInsufficientFunds` (fondos insuficientes).

El número completo se sigue descartando después de validarlo. Una migración de datos asigna el token a las tarjetas ya registradas según sus últimos cuatro dígitos.

### 4. Iniciar el pago no completa la transacción
La transacción permanece en `PENDIENTE`, aunque Stripe responda `succeeded`. El pago queda `EN_PROCESO` hasta que llegue la confirmación del proveedor, que se implementa en la HU-18 (webhook de Stripe y aprobación del simulador). Si el proveedor rechaza el pago o no puede procesarlo, el pago queda `RECHAZADO` o `ERROR` y se informa el motivo al cliente.

### 5. Importe y moneda según la operación
- En una **compra** se cobra el total en guaraníes.
- En una **venta** se cobra la divisa que entrega el cliente.

PYG no tiene decimales en Stripe, así que el total se redondea a guaraníes enteros y el `Pago` registra el importe efectivamente cobrado. El simulador de billetera admite cualquier moneda.

### 6. Un solo pago activo por transacción
Una restricción única parcial de la base de datos impide que una transacción tenga dos pagos `INICIADO` o `EN_PROCESO` al mismo tiempo, aunque el cliente haga doble clic o use dos pestañas. Después de un rechazo o un error se puede reintentar con un pago nuevo, y queda el historial de intentos.

### 7. Llamada al proveedor fuera de la transacción de base de datos
El servicio `iniciar_pago` trabaja en dos fases:
1. Valida y registra el pago con la transacción bloqueada.
2. Contacta al proveedor sin mantener el bloqueo durante la llamada de red.

El bloqueo usa `select_for_update(of=("self",))`, porque PostgreSQL no admite `FOR UPDATE` sobre el lado nulable de un JOIN.

### 8. Solo el cliente de la operación puede pagarla
La acción de pago busca la transacción dentro del cliente activo del usuario y acepta únicamente POST con token CSRF. Un administrador o analista que consulta el historial general no puede pagar operaciones de otros clientes.

### 9. Reintento con otro método de pago
Si el intento anterior fue rechazado o terminó en error, o si el método de la operación ni siquiera permite iniciar el pago (por ejemplo, una tarjeta sin token), el detalle de la operación ofrece un selector con los métodos activos del cliente para pagar con otro, o con el mismo. Aplica por igual a compras y ventas.
- El método elegido pasa a ser el método de la operación solo si el pago puede iniciarse; si el nuevo método no está habilitado, la operación conserva el anterior.
- Cada intento conserva el método con el que se hizo, de modo que el historial de pagos sigue siendo fiel.
- El servidor valida que el método sea activo y del cliente de la operación, sin confiar en lo que muestra el selector.

## Criterios de aceptación cumplidos
- **Solo transacciones pendientes:** el servicio lo verifica con la fila bloqueada y el botón "Pagar" solo aparece en ese estado.
- **Método de pago habilitado:** el método debe estar activo y pertenecer al cliente. `get_proveedor` y la validación de cada proveedor controlan el tipo de método, el token y el importe.
- **Referencia del proveedor:** se guarda en `Pago.referencia_externa` (`pi_...` o `SIM-...`), incluso cuando Stripe rechaza la tarjeta.
- **Rechazo o falla sin completar la transacción:** ningún camino de la HU-15 modifica el estado de la transacción.
- **Aviso al usuario:** se muestra un mensaje con el motivo, y el detalle de la operación lista los intentos de pago con su estado.

## Validaciones realizadas
- Pruebas automatizadas de `pagos`, `integrations` y `transacciones`, ejecutadas sobre PostgreSQL. Stripe se simula con `unittest.mock`, de modo que las pruebas nunca contactan al servicio real.
- Documentación generada con Sphinx sin advertencias nuevas.

## Consideraciones pendientes
- **HU-18 (SCRUM-53):** webhook de Stripe, página del simulador para aprobar o rechazar, función idempotente de confirmación y paso de la transacción a `COMPLETADA`.
- **Cotización vencida:** no se vuelve a verificar la cotización antes de pagar. Queda fuera del alcance de esta historia.
