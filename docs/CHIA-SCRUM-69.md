# CHIA - SCRUM-69: Configuración de tolerancia y alertas de arqueo

## Historia de Usuario

**SCRUM-69 - HU-32: Configuración de tolerancia y alertas de arqueo**

Como administrador quiero configurar el límite máximo permitido para las diferencias de caja y recibir una alerta cuando dicho límite sea superado para detectar posibles irregularidades.

## Herramienta utilizada
Claude Code (Anthropic) - sesión local en la terminal, sin enlace público a la conversación.

## Resumen de la asistencia
Se utilizó Claude Code como apoyo durante el análisis, el diseño y la implementación de la HU-32.

La asistencia incluyó:
- Análisis de la historia de usuario y de su relación con la HU-37 (SCRUM-30, cierre y arqueo de caja), que es donde se calculan las diferencias.
- Revisión del código existente: `CierreCaja`, `DetalleCierreCaja`, `cerrar_caja`, la consulta de usuarios de Keycloak y el envío de correo de `notificaciones`.
- Elaboración de una propuesta de diseño previa a la implementación. El equipo tomó las decisiones de negocio: tolerancia por moneda y moneda sin configurar equivalente a tolerancia cero.
- Implementación de los modelos, la lógica de comparación, el envío de la alerta y las pantallas de configuración y consulta.
- Pruebas automatizadas, documentación técnica y una guía de prueba manual del flujo completo de caja.

El código y las decisiones finales fueron revisados por el equipo y validados con las pruebas ejecutadas localmente sobre PostgreSQL.

## Decisiones tomadas con asistencia de IA

### 1. El arqueo es el cierre de caja
No existe un modelo de arqueo independiente: el arqueo vive en `CierreCaja` y `DetalleCierreCaja` (una fila por moneda, con `diferencia = físico − teórico`). Como `CierreCaja` es uno a uno con `AperturaCaja`, hay un solo arqueo por apertura y no existen arqueos parciales. Por eso `AlertaArqueo` es una relación uno a uno con `CierreCaja`: a lo sumo una alerta por cierre.

### 2. Tolerancia por moneda, sin conversión
`ToleranciaArqueo` guarda una fila por moneda con su diferencia máxima tolerada. La diferencia se compara en la moneda original, sin convertir a PYG.
- Validación `MinValueValidator(0)` en el campo y `CheckConstraint(monto_maximo >= 0)` en la base de datos.
- El cero es un valor válido.
- Una moneda sin fila se trata como tolerancia **cero**: cualquier diferencia alerta. Es el valor por defecto más seguro.
- Se guarda quién la modificó y cuándo.

### 3. Comparación en valor absoluto y estricta
Se alerta cuando `abs(diferencia) > tolerancia`. Faltante y sobrante se tratan igual, y una diferencia exactamente igual al límite no genera alerta. La comparación es una función pura (`detectar_excedidos`), sin acceso a la base de datos ni al correo, para poder probarla de forma aislada.

### 4. Una alerta por cierre, con copia de la tolerancia aplicada
Si fallan varias monedas se registra una sola alerta, con un `DetalleAlertaArqueo` por moneda excedida y un solo correo con todas. Cada detalle guarda una copia de la diferencia y de la tolerancia aplicada, de modo que el registro sigue siendo válido aunque el administrador cambie el límite después.

### 5. La alerta se registra en la transacción del cierre
`cerrar_caja` llama a `evaluar_cierre` justo después de crear los detalles del cierre. La alerta y su detalle se guardan en la misma transacción, por lo que nunca hay un cierre con diferencia excedida sin alerta. Si el registro de la alerta falla por la base de datos, el cierre también se revierte; ese fallo no se silencia a propósito.

### 6. El correo sale después del commit y en un hilo
El envío se programa con `transaction.on_commit` y un hilo, con el mismo esquema que `notificar_al_confirmar` de las tasas de cambio. Un fallo de Keycloak o del servidor de correo no revierte el cierre ni la alerta: queda registrado como envío fallido en `EnvioAlertaArqueo`, con el motivo.

### 7. Destinatarios desde Keycloak
La consulta de `cajas/keycloak_service.py` se generalizó a cualquier rol (`obtener_usuarios_por_rol`); `obtener_cajeros_keycloak` queda como envoltorio del rol `cajero`. Los destinatarios son los usuarios habilitados con rol `administrador` o `tesorero`, sin los que no tienen correo y sin duplicados por correo (sin distinguir mayúsculas).

### 8. Reutilización del envío de `notificaciones`
Se reutilizan `_abrir_conexion` y `_enviar` de `notificaciones/services.py`, incluida la pausa `NOTIFICACIONES_PAUSA_ENVIO` entre correos que exige el sandbox de Mailtrap. El único cambio allí es el texto de un log, que mencionaba tasas. No se reutiliza el modelo `Notificacion`, porque está atado a tasas de cambio.

## Criterios de aceptación cumplidos
- **Configurar un valor máximo de diferencia tolerada:** pantalla `Gestión de Caja → Tolerancia de arqueo`, exclusiva del administrador, con una fila por moneda activa y guardado en un solo formulario.
- **El valor no puede ser negativo:** se rechaza en el formulario, en el campo del modelo y con una restricción en la base de datos.
- **Comparación automática en cada arqueo:** `cerrar_caja` evalúa todas las monedas del cierre sin intervención del usuario.
- **Alerta cuando se supera el límite:** se crea `AlertaArqueo` con el detalle de cada moneda excedida.
- **Dirigida al Administrador y al Tesorero:** correo a ambos roles y listado de alertas visible solo para ellos.
- **Registro para consulta posterior:** `Gestión de Caja → Alertas de arqueo` muestra caja, cajero, fecha, monedas excedidas con su límite y el estado de cada envío. También se registran los cuatro modelos en el admin de Django.

## Validaciones realizadas
- 42 pruebas nuevas en `cajas/test_alertas.py`: comparación (bajo, igual y sobre el límite, faltante y sobrante, moneda sin configurar, varias monedas), tolerancia (negativos, cero, una por moneda, acceso solo del administrador), destinatarios (unión de roles, duplicados, sin correo, Keycloak caído), correo (contenido, envío, fallo de SMTP y de conexión), registro (sin alerta dentro del límite, copia de la tolerancia, alerta aunque falle el correo, programación posterior al commit) y consulta (administrador y tesorero sí, cajero no).
- Ejecución conjunta de `cajas`, `notificaciones` y `core`: 171 pruebas, sin fallos, sobre PostgreSQL.
- `makemigrations --check` sin cambios pendientes; la migración es `cajas/0007_tolerancia_alertas_arqueo_hu32`.
- Documentación generada con Sphinx: el módulo `cajas` se agrega a `docs/source/cajas.rst` y al índice.
- El envío real contra Mailtrap y Keycloak se verifica manualmente con la guía del flujo de gestión de caja.

## Consideraciones pendientes
- **Permisos de Keycloak:** el cliente `global-exchange-cajas-service` necesita los roles `view-users`, `query-users` y `view-realm` de `realm-management`. Con solo `view-users` la consulta `/roles/{rol}/users` responde 403 en Keycloak 26.2.5.
- **Cierres anteriores:** los cierres registrados antes de esta HU no se evalúan; no hay migración de datos.
- **Reintento de correos fallidos y marca de alerta revisada:** ningún criterio lo pide, por lo que quedan fuera del alcance de esta historia.
- **Historial de cambios de tolerancia:** solo se conserva quién y cuándo modificó el último valor.
