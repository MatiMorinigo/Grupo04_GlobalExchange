# CHIA - SCRUM-58: Notificación de cambios en las tasas de cambio

## Historia de Usuario

**SCRUM-58 - HU-30: Notificación de cambios en las tasas de cambio**

Como usuario registrado quiero recibir una notificación cuando se modifiquen las tasas de cambio de Global Exchange para mantenerme informado sobre los valores vigentes.

## Herramienta utilizada
Claude Code (Anthropic) - sesión local en la terminal, sin enlace público a la conversación.

## Resumen de la asistencia
Se utilizó Claude Code como apoyo durante el análisis, el diseño y la implementación de la HU-30.

La asistencia incluyó:
- Análisis de la historia de usuario y de sus criterios de aceptación.
- Revisión del código existente para ubicar dónde se publican las tasas y qué infraestructura de correo había disponible.
- Propuesta y comparación de alternativas de diseño (señales, envío síncrono, registro en base de datos).
- Implementación de la aplicación `notificaciones`, su integración con `cotizaciones` y sus pruebas automatizadas.
- Redacción de la documentación técnica.

El código y las decisiones finales fueron revisados por el equipo y validados con las pruebas ejecutadas localmente.

## Decisiones tomadas con asistencia de IA

### 1. Aplicación independiente `notificaciones`
La notificación es una responsabilidad transversal y distinta de la gestión de tasas. Se creó una aplicación propia en lugar de agregar el envío de correos dentro de `cotizaciones`.

### 2. Disparo explícito después del commit
La notificación se programa con `transaction.on_commit` desde los tres puntos donde se publica una tasa:
- `TasaCambioEditarView` (modificación confirmada).
- `TasaCambioCrearView` (tasa inicial de un par).
- `TasaCambioAdmin.save_model` (admin de Django), solo si la tasa está vigente y cambió `precio_compra`, `precio_venta` o `vigente`.

Se descartó la señal `post_save` porque no permite saber qué campos cambiaron y notificaría ediciones que no modifican los valores publicados.

### 3. Un error de envío no revierte la tasa
Como el envío ocurre después del commit, la tasa ya está guardada cuando se intenta notificar. El manejo de errores tiene dos niveles:
- Los errores esperados de envío (`SMTPException`, `OSError`) se capturan, se registran en el log y quedan guardados en la notificación.
- Cualquier error inesperado se registra en el log dentro del hilo de envío, de modo que el analista nunca recibe un error después de guardar la tasa.

### 4. Destinatarios
Se notifica a todos los usuarios activos (`is_active=True`) que tengan correo. Se considera "usuario registrado" a quien ingresó al sistema al menos una vez, porque en ese momento Django crea el usuario local a partir de Keycloak. No se filtra por rol porque los roles solo existen en el token de Keycloak.

### 5. Registro de cada notificación
El modelo `Notificacion` guarda un registro por destinatario con el estado del envío (`ENVIADA` o `FALLIDA`) y el detalle del error. Conserva además una copia del correo de destino y de los precios informados, para que el registro siga siendo válido como evidencia aunque el usuario cambie su correo o la tasa se edite después.

### 6. Envío en segundo plano con una sola conexión
El proyecto no posee infraestructura de Celery/Redis, por lo que el envío se lanza en un hilo aparte (`threading.Thread`) después del commit, reutilizando una única conexión SMTP. Así quien publica la tasa recibe su respuesta de inmediato, sin esperar a los correos. Cada notificación se registra apenas se intenta su envío. Si la conexión no puede abrirse, todas las notificaciones quedan como fallidas sin intentar cada envío por separado. Se agregó `EMAIL_TIMEOUT` para acotar la espera.

### 7. Pausa configurable entre correos
En la prueba manual con dos usuarios, el sandbox de Mailtrap rechazó el segundo correo con `550 Too many emails per second`; la tasa se guardó y la notificación quedó registrada como fallida. Se agregó la variable `NOTIFICACIONES_PAUSA_ENVIO` (segundos de espera entre un correo y el siguiente, `0` por defecto) para adaptarse a servidores que limitan el ritmo de envío. El plan gratuito del sandbox admite un correo cada 10 segundos, por lo que en desarrollo se usa una pausa de 11 segundos. Se evaluó enviar un único correo con copia oculta, pero se mantuvo el envío individual para conservar el estado de cada notificación.

## Limitaciones conocidas
- El hilo de envío no es una cola persistente: si el servidor se reinicia durante el envío, los correos pendientes se pierden sin dejar registro.
- Un usuario registrado en Keycloak que nunca ingresó a la aplicación no recibe notificaciones hasta su primer inicio de sesión.
- El admin de Django notifica los cambios, pero sigue sin generar `AuditoriaTasaCambio`.
- No hay reintentos automáticos de las notificaciones fallidas.
- Con la pausa activada, el último usuario recibe el correo con ese retraso acumulado.

## Pruebas realizadas
Se agregaron pruebas para verificar:
- contenido del correo: moneda, par y nuevos valores de compra y venta;
- registro de la notificación con correo, precios y estado;
- exclusión de usuarios inactivos y sin correo;
- espera de la pausa configurada entre correos;
- ausencia de conexión al servidor cuando no hay destinatarios;
- fallo de conexión: todas las notificaciones quedan como fallidas;
- fallo de un destinatario: no interrumpe el envío a los demás;
- notificación al modificar una tasa confirmada y al crear una tasa inicial;
- ausencia de notificación cuando la modificación no fue confirmada;
- un error de envío o un error inesperado no revierten la tasa ni interrumpen la respuesta;
- el envío se lanza en un hilo y recién después del commit;
- el admin notifica solo cuando cambian los valores publicados.

Además se ejecutó la suite completa del proyecto (254 pruebas) para comprobar que los cambios no introdujeran incompatibilidades.

## Archivos principales involucrados
- `notificaciones/models.py`
- `notificaciones/services.py`
- `notificaciones/admin.py`
- `notificaciones/tests.py`
- `notificaciones/migrations/0001_initial.py`
- `templates/notificaciones/cambio_tasa.txt`
- `cotizaciones/views.py`
- `cotizaciones/admin.py`
- `config/settings.py`
- `.env.example`
- `docs/source/notificaciones.rst`
- `docs/source/index.rst`
