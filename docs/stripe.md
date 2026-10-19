# Stripe en Global Exchange

La integración actual utiliza el modo de prueba: Django crea un PaymentIntent
con un token `pm_card_*` y completa la operación cuando recibe un webhook firmado.
No requiere una clave pública `pk_test_` porque no utiliza Stripe.js.

## Preparación en Windows (PowerShell)

Desde la raíz del proyecto, con PostgreSQL y Keycloak disponibles:

1. Activá el entorno e instalá las dependencias si todavía no están instaladas:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

2. Conservá tu `.env` existente. Si aún no existe, copialo desde `.env.example`
   y completá también la configuración de base de datos y autenticación.
   En el [Dashboard de Stripe](https://dashboard.stripe.com/test/apikeys), obtené
   la clave secreta del sandbox y asignala a `STRIPE_SECRET_KEY`. Nunca la
   publiques ni la incluyas en Git. El proyecto ignora `.env`.

3. Instalá [Stripe CLI](https://docs.stripe.com/cli/install) si `stripe --version`
   no está disponible. El siguiente comando usa la clave de `.env` para obtener
   el secreto del listener de esa misma cuenta y guarda `STRIPE_WEBHOOK_SECRET`:

   ```powershell
   python manage.py configurar_stripe
   python manage.py check --tag stripe
   python manage.py migrate
   ```

   El comando no crea cobros ni registra un endpoint público. No necesitás
   ejecutar `stripe login`: se autentica con la clave de prueba configurada.

4. En una terminal, iniciá la escucha y dejala abierta:

   ```powershell
   python manage.py configurar_stripe --escuchar
   ```

   Reenvía únicamente `payment_intent.succeeded` y `payment_intent.payment_failed`
   a `http://127.0.0.1:8000/transacciones/webhooks/stripe/`.
   Podés cambiar el puerto con `--puerto 8001`.

5. En otra terminal con el mismo entorno activado, iniciá Django:

   ```powershell
   python manage.py runserver 127.0.0.1:8000
   ```

   Si Django ya estaba abierto al actualizar `.env`, reinicialo: los cambios del
   archivo no se cargan automáticamente. Las variables del entorno del sistema
   tienen prioridad sobre `.env`; evitá valores distintos para las mismas claves.

## Probar una operación

Iniciá sesión, seleccioná un cliente y registrá un método de pago de tipo tarjeta
en `/metodos-pago/`, con titular y un vencimiento futuro como `12/30`.

| Número de prueba | Resultado esperado |
| --- | --- |
| `4242 4242 4242 4242` | Pago aprobado |
| `4000 0000 0000 0002` | Tarjeta rechazada |
| `4000 0000 0000 9995` | Fondos insuficientes |

Creá una compra o venta con esa tarjeta y pagala desde el detalle. Usá un importe
que Stripe admita para la moneda elegida. Los guaraníes se cobran en unidades
enteras; USD y EUR, en centavos. El pago aprobado pasa a **EN_PROCESO** hasta que
el webhook confirma la operación. Stripe CLI debe mostrar una respuesta HTTP 200.
El rechazo conserva la operación pendiente y permite reintentar con otra tarjeta.

Un evento genérico creado con `stripe trigger` carece de la metadata `id_pago` de
Global Exchange: sirve para probar la entrega HTTP, pero no completa una operación
del sistema. Para probar el flujo completo, iniciá el pago desde Global Exchange.

## Diagnóstico

- **Webhook HTTP 400:** verificá el secreto ejecutando `configurar_stripe` y
  reiniciá Django. El secreto del Dashboard corresponde a otro destino y no
  sirve para verificar la firma del listener del CLI.
- **Pago en proceso:** comprobá que ambas terminales sigan abiertas y que el
  puerto del listener coincida con Django. Para recuperar pagos sin webhook:
  `python manage.py sincronizar_pagos`, o agregá `--id-pago ID` para uno concreto.
  Este comando consulta Stripe y aplica el resultado real al pago local.
- **Tarjeta no habilitada:** solo los tres números de prueba de la tabla reciben
  un token automáticamente. Ejecutá las migraciones para tarjetas antiguas.
- **Sin conexión o CLI sin permisos:** verificá que `stripe --version` funcione
  y que el equipo pueda acceder a Stripe por HTTPS.

## Alcance

Esta configuración sirve para pruebas. El formulario asigna tokens de prueba y
el flujo actual no resuelve autenticación adicional como 3D Secure. Usar tarjetas
reales requiere implementar captura y tokenización con Stripe.js/Elements y el
flujo de autenticación correspondiente. Los controles de configuración rechazan
claves de producción para este flujo.

Referencias oficiales: [webhooks y escucha local](https://docs.stripe.com/webhooks),
[tarjetas de prueba](https://docs.stripe.com/testing),
[claves API](https://docs.stripe.com/keys).
