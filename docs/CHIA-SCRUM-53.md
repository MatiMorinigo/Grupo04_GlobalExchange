# CHIA - SCRUM-53: Confirmación automática de pago

## Historia de Usuario

**SCRUM-53 - HU-18: Confirmación automática de pago**

Como cliente quiero que el sistema confirme automáticamente el resultado de mi pago para conocer si mi operación cambiaria fue completada correctamente.

## Herramienta utilizada
Claude Code (Anthropic) - sesión local en la terminal, sin enlace público a la conversación.

## Resumen de la asistencia
Se utilizó Claude Code como apoyo durante el análisis, el diseño y la implementación de la HU-18, continuación directa de la HU-15 (SCRUM-68, inicio del pago).

La asistencia incluyó:
- Análisis de los criterios de aceptación y de lo que dejó preparado la HU-15: el modelo `Pago`, la referencia externa y la metadata enviada a Stripe.
- Elaboración de un plan detallado. El equipo tomó las decisiones de diseño: estado final de la operación, respaldo para entornos sin Stripe CLI y quién resuelve los pagos simulados.
- Implementación de la validación del webhook de Stripe, de la función idempotente de confirmación, de la pantalla de pagos simulados y del comando de sincronización.
- Pruebas automatizadas y documentación técnica.

El código y las decisiones finales fueron revisados por el equipo y validados con las pruebas ejecutadas localmente sobre PostgreSQL.

## Decisiones tomadas con asistencia de IA

### 1. Una única función para confirmar o rechazar pagos
`procesar_resultado_pago` es el único punto que aplica el resultado de un pago. La usan:
- el webhook de Stripe;
- la pantalla de pagos simulados;
- el comando `sincronizar_pagos`.

Así, las reglas de validación e idempotencia son las mismas sin importar por dónde llegue el resultado.

### 2. La operación pasa a `COMPLETADA`
Una confirmación exitosa deja el pago en `CONFIRMADO`, con la fecha y hora de confirmación, y la transacción pendiente en `COMPLETADA` con esa misma fecha. No se creó un estado nuevo: `COMPLETADA` ya existía y es el que usa la promoción VIP temporal para medir el volumen de cada cliente.

### 3. Validación de la confirmación
- **Stripe:** el webhook verifica la firma del encabezado `Stripe-Signature` con el secreto `STRIPE_WEBHOOK_SECRET`. Una notificación con firma inválida responde 400 y no modifica nada.
- **Coincidencia con el pago registrado:** además de la firma, la referencia, el importe y la moneda informados deben coincidir con el `Pago`. Si no coinciden, el resultado se descarta y se registra en el log.
- **Billetera simulada:** solo pueden resolverla un analista cambiario o un administrador, mediante un formulario con token CSRF.

### 4. Idempotencia sin tabla de eventos
La función bloquea la operación y el pago (`select_for_update`) y solo actúa sobre pagos que todavía no tienen un resultado definitivo. Una notificación repetida (por ejemplo, un reenvío de Stripe) se reconoce como duplicada: no cambia la fecha de confirmación ni completa dos veces la operación.

### 5. Carrera entre el inicio del pago y el webhook
Stripe puede enviar el webhook antes de que termine la llamada que inició el pago (HU-15). Para que esa respuesta tardía no pise la confirmación:
- el pago se busca por el `id_pago` enviado en la metadata, que existe desde antes de llamar a Stripe;
- la respuesta del inicio solo se guarda si el pago sigue `INICIADO`.

Hay un test que reproduce esta carrera.

### 6. Respaldo sin Stripe CLI: comando `sincronizar_pagos`
En desarrollo, el webhook solo llega a `localhost` con la Stripe CLI (`stripe listen`). El comando `python manage.py sincronizar_pagos` consulta en Stripe los pagos que siguen sin confirmar y aplica su resultado con la misma función. También sirve en producción si alguna notificación se perdió.

### 7. Pagos simulados resueltos por personal interno
Las billeteras electrónicas no tienen una pasarela de prueba disponible. La pantalla "Pagos simulados", visible para analistas cambiarios y administradores, permite aprobar o rechazar cada pago, haciendo las veces de la respuesta de la billetera.

### 8. Compatibilidad con stripe-python 16
Desde la versión 15 de la librería, los objetos de Stripe ya no se comportan como diccionarios. Los eventos y PaymentIntents se convierten con `to_dict()` antes de leerlos. Las pruebas automatizadas detectaron esta incompatibilidad.

## Criterios de aceptación cumplidos
- **Recibir y validar la confirmación:** el webhook verifica la firma, y además la referencia, el importe y la moneda deben coincidir con el pago registrado.
- **Confirmación exitosa → pago confirmado:** el pago queda `CONFIRMADO` y la transacción `COMPLETADA`.
- **Fecha y hora de confirmación:** se guardan en `Pago.confirmado_en` y en `Transaccion.completada_en`.
- **Referencia externa conservada:** nunca se sobrescribe; si el webhook llegó antes que la respuesta del inicio, se completa.
- **Notificación repetida:** se reconoce como duplicada y no modifica la operación.
- **Pago rechazado:** queda `RECHAZADO`, la operación sigue `PENDIENTE` y el cliente puede reintentar.

## Validaciones realizadas
- Pruebas automatizadas de `integrations`, `transacciones` y `core`, ejecutadas sobre PostgreSQL. Los webhooks se firman localmente con la librería de Stripe y las consultas se simulan con `unittest.mock`, de modo que las pruebas nunca contactan al servicio real.
- La suite completa del proyecto (445 pruebas) pasa.
- Documentación generada con Sphinx sin advertencias nuevas.

## Consideraciones pendientes
- **Reembolsos y conciliación:** si un pago se confirma sobre una operación que ya no está pendiente, el pago se marca "requiere revisión", pero no se reembolsa automáticamente.
- **Producción:** el webhook necesita una URL pública HTTPS registrada en el Dashboard de Stripe, con su propio secreto `whsec_`.
