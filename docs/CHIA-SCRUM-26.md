# CHIA - SCRUM-26: HU-34 Apertura de caja con inventario inicial de billetes

## Herramienta utilizada
Codex / ChatGPT (OpenAI), con acceso al repositorio local y ejecución de pruebas.

## Enlace a la conversación
La implementación se realizó en la sesión de Codex del proyecto. No se dispone
de un enlace compartido de esta conversación; no se consigna uno ficticio.

## Resumen de la asistencia
Se revisaron `cajas`, SCRUM-25 (`AsignacionCaja`), la autenticación OIDC,
`cotizaciones.Moneda`, las transacciones y los componentes Bootstrap 5 / AdminLTE 4.
Se implementaron persistencia, validaciones, servicios, formularios, vistas,
plantillas, acceso lateral y pruebas para registrar aperturas con conteos iniciales.

Se trabajó en `feature/SCRUM-26`, conservando los cambios de navegación existentes.
No se modificaron migraciones publicadas ni se ejecutaron commit, push o
`git flow feature finish`.

## Decisiones tomadas con asistencia de IA

### Modelos y relaciones estables

| Modelo | Campos y contrato |
| --- | --- |
| `DenominacionBillete` | FK `moneda` a `cotizaciones.Moneda`, `valor` Decimal(18,2), `activa`. Una combinación moneda/valor; valor positivo. |
| `AperturaCaja` | PK `id_apertura`, FK `caja` (`caja.aperturas`), FK `asignacion` (`asignacion.aperturas`), UUID `cajero_keycloak_id`, `fecha_apertura`, `estado` (`ABIERTA` / `CERRADA`), `fecha_cierre` nullable. |
| `DetalleInventarioInicial` | FK `apertura` (`apertura.detalles_inventario`), FK `denominacion` (`denominacion.detalles_iniciales`), `cantidad`, copia histórica `moneda` y `valor_denominacion`. |

Todas las relaciones nuevas usan `PROTECT`. No se duplican registros de moneda.
La copia del código de moneda referenciado y del valor del billete conserva el
saldo histórico aunque posteriormente se edite o desactive el catálogo.

`apertura.saldos_iniciales` devuelve un diccionario `{codigo_moneda: Decimal}`,
calculado por el servidor como `SUM(valor_denominacion * cantidad)`, agrupado por
moneda, con salida Decimal(32,2). No existe un saldo editable, una suma entre
monedas ni una conversión cambiaria implícita. Cada detalle expone `subtotal`.

### Reglas de negocio e identidad

- Solo usuarios autenticados con rol de reino `cajero` pueden acceder. Ser
  administrador, tesorero o superusuario Django no sustituye este rol.
- El responsable es el `sub` UUID del access token OIDC verificado, nunca el
  username local, el nombre de SCRUM-25 ni un campo enviado en el formulario.
- `core.keycloak.obtener_claims_verificados` valida firma RS256 mediante JWKS,
  expiración, presencia de `sub` y emisor derivado de
  `OIDC_OP_AUTHORIZATION_ENDPOINT`. Exige `azp == OIDC_RP_CLIENT_ID`. Mantiene
  deshabilitada la validación de `aud` del access token, como la integración
  existente (Keycloak puede usar `account`), verificando el cliente mediante
  `azp`. Los roles y la identidad comparten los claims verificados durante la
  solicitud. Esta validación también se aplica a los menús y permisos que
  consumen `obtener_roles`.
- La asignación debe pertenecer al mismo UUID y a la caja; caja y sucursal deben
  estar activas. La vigencia es `fecha_inicio <= ahora < fecha_fin`.
- La hora real se toma del servidor después de adquirir los bloqueos; no se
  utiliza el inicio programado como fecha de apertura.
- Se exige entre 1 y 100 líneas, con denominaciones existentes y habilitadas,
  monedas activas y cantidades enteras entre 0 y 2.147.483.647. Se rechazan
  duplicados y combinaciones moneda/denominación inconsistentes.
- Se permite un inventario explícito con cantidades todas en cero. No se permite
  inventario vacío, líneas incompletas ni todas las líneas omitidas.
- Una apertura continúa activa después del vencimiento del turno. Solo el futuro
  cierre manual podrá cambiar este estado.

### Integridad y concurrencia

`cajas.services.abrir_caja(request=..., asignacion_id=..., inventario=...)` es el
punto de escritura de aperturas. `inventario` es una lista de diccionarios con
`denominacion_id` entero y `cantidad` entera; no recibe totales, valores, moneda,
fechas ni identidad del cliente.

La operación usa `transaction.atomic()` y `select_for_update()` en el orden
Asignación → Caja → Sucursal → denominaciones/monedas. Relee y valida los datos
dentro de la transacción. Crea la apertura y cada detalle; cualquier error revierte
todos los registros, incluso si ya se guardó una línea.

PostgreSQL aplica:

- Índice único parcial `caja_apertura_activa_unica` por caja con estado `ABIERTA`.
  Protege incluso inserciones concurrentes que omitan el servicio.
- Restricción `apertura_cierre_coherente`: abierta sin fecha de cierre, o cerrada
  con fecha igual o posterior a la apertura. También rechaza estados desconocidos.
- Unicidad moneda/valor en el catálogo y apertura/denominación en los detalles,
  además de apertura/moneda/valor histórico.
- Restricciones de cantidades no negativas y valores positivos.

El conflicto esperado del índice único se transforma, fuera del bloque atómico,
en `AperturaCajaError` (subclase de `ValidationError`); las vistas muestran el
mensaje conservando el inventario. Los errores de integridad inesperados no se
ocultan. La existencia de líneas y las relaciones entre asignación, caja e
identidad se validan en el servicio; una inserción ORM/SQL arbitraria puede omitir
estas reglas entre tablas. Los futuros consumidores deben usar el servicio.

### Interfaz y configuración del catálogo

Rutas públicas de la aplicación, protegidas por el rol cajero:

- `apertura-list`: `/cajas/aperturas/`, asignaciones vigentes, estado de la caja y
  últimas 50 aperturas propias, incluso después del turno.
- `apertura-create`: `/cajas/asignaciones/<id_asignacion>/abrir/`.
- `apertura-detail`: `/cajas/aperturas/<id_apertura>/`, inventario y saldos propios.

Los recursos ajenos responden 404; un usuario autenticado sin rol responde 403;
un visitante anónimo se redirige al login. Los POST requieren CSRF. No se publican
rutas de edición de inventarios, identidades o saldos.

El menú **Gestión de Caja → Apertura de caja** es visible para cajeros; se
conservan las opciones previas de administradores y tesoreros y sus estados activos.
El formulario permite agregar líneas, filtra denominaciones según la moneda y
permite omitir líneas mediante un checkbox. El formset valida todo nuevamente en
el servidor, incluyendo el límite máximo y el formulario de administración.

Antes del primer uso, un administrador con permisos Django debe cargar las
denominaciones aceptadas por la empresa en
`/admin/cajas/denominacionbillete/`, seleccionando las monedas existentes.
No se inventa un catálogo de billetes ni se insertan datos operativos en la base.
Las denominaciones pueden deshabilitarse. Si no existe catálogo habilitado, la
pantalla explica cómo configurarlo y no ofrece guardar una apertura vacía.
El permiso de catálogo es el del administrador Django existente, independiente
del rol de cajero; no se agrega una pantalla de mantenimiento para cajeros.

## Contrato para Dev 4: movimientos, cierre y arqueo

No se encontró un módulo de movimientos físicos de caja. Las transacciones
cambiarias actuales son registros de compra/venta en estado pendiente, sin
relación con cajas; no se alteraron sus reglas.

`obtener_apertura_activa(caja_id)` devuelve una `AperturaCaja` abierta o lanza
`AperturaCajaError`. No filtra por vigencia del turno. Sirve para consultar;
usarla aisladamente antes de guardar NO impide una carrera con el cierre.

Para el futuro registro de efectivo debe utilizarse el contexto transaccional:

```python
from cajas.services import apertura_para_movimiento

# Ejemplo de integración futura: MovimientoEfectivo todavía no existe.
with apertura_para_movimiento(caja_id) as apertura:
    # Validar aquí permisos del operador, importes, moneda y saldo disponible.
    # Guardar aquí el movimiento con FK a apertura (on_delete=PROTECT).
    # Toda la escritura debe terminar antes de salir del bloque.
    pass
```

Este contexto bloquea **Caja → Apertura** y mantiene ambos bloqueos y la
transacción durante el `with`. Una caja inexistente o sin apertura activa impide
entrar al bloque. Un error dentro del bloque revierte la transacción.

El cierre de Dev 4 deberá usar `transaction.atomic()`, bloquear primero la misma
`Caja` y luego su `AperturaCaja`, registrar el arqueo y cambiar conjuntamente
`estado=Estado.CERRADA` y `fecha_cierre=timezone.now()`. Debe respetar este orden
para coordinarse con movimientos y nuevas aperturas. Si el cierre precisa validar
la asignación con bloqueo, adquirir Asignación antes de Caja, nunca al revés.

Dev 4 debe añadir sus modelos de movimientos/arqueo referenciando la apertura,
registrar responsable del cierre, calcular saldo disponible y diferencias por
moneda y definir sus permisos. El inventario inicial y su identidad no deben
reescribirse al cerrar. La relación asignación/aperturas es FK, no OneToOne, para
permitir otra apertura después de un cierre dentro del mismo turno.

No se implementan cierre, arqueo ni endpoints de movimientos en esta historia.
El servicio está probado; no se afirma que endpoints futuros estén protegidos
antes de que lo integren.

## Migraciones

Se generó y aplicó en PostgreSQL local
`cajas/migrations/0004_apertura_inventario_inicial.py`, con los tres modelos y
sus restricciones. Depende de SCRUM-25 y de la migración vigente de cotizaciones.
No se modificaron migraciones anteriores, registros de monedas ni datos existentes.

## Archivos de la entrega

| Tipo | Archivos |
| --- | --- |
| Nuevos: persistencia y servicios | `cajas/migrations/0004_apertura_inventario_inicial.py`, `cajas/services.py` |
| Nuevos: pruebas | `cajas/test_aperturas.py` |
| Nuevos: interfaz | `templates/cajas/apertura_list.html`, `templates/cajas/apertura_form.html`, `templates/cajas/_inventario_linea.html`, `templates/cajas/apertura_detail.html` |
| Nuevo: documentación | `docs/CHIA-SCRUM-26.md` |
| Modificados: aplicación | `cajas/models.py`, `cajas/forms.py`, `cajas/views.py`, `cajas/mixins.py`, `cajas/web_urls.py`, `cajas/admin.py` |
| Modificados: identidad, navegación y regresión | `core/keycloak.py`, `core/context_processors.py`, `core/tests.py`, `templates/base.html` |

Los cambios previos de `cajas/tests.py` se conservaron sin alteraciones adicionales;
también se conservaron las mejoras previas de navegación en los archivos compartidos.

## Pruebas realizadas

Se utilizó Python 3.14.5 y Django 6.1 del entorno `.venv`, con PostgreSQL real.
El `python` global no tenía `mozilla_django_oidc`; todos los comandos de
validación se ejecutaron con `.\.venv\Scripts\python.exe`.

Las pruebas nuevas incluyen:

- Apertura válida, responsable y hora real; límites inicial/final del turno.
- Cajero ajeno, rol ausente, UUID inválido, caja/sucursal deshabilitadas.
- Inventarios vacíos, duplicados, incompletos, monedas inconsistentes,
  denominaciones inexistentes/inactivas, cantidades negativas, fraccionarias y cero.
- Cálculo decimal separado por moneda y conservación histórica tras editar catálogo.
- Rollback al fallar el segundo detalle y traducción del conflicto de apertura activa.
- Restricciones PostgreSQL por inserciones directas y **dos conexiones concurrentes**:
  tanto inserciones directas como llamadas simultáneas al servicio.
- Rechazo de movimientos sin apertura y conservación de una apertura tras el turno.
- Permisos GET/POST, protección de recursos ajenos, CSRF, datos manipulados,
  formulario de varias líneas, resumen y navegación.
- Tokens RS256 firmados localmente con JWKS simulado: firma, emisor, cliente,
  expiración, claims requeridos, ausencia de sesión y fallos de consulta.
  Las pruebas no dependen de un servidor Keycloak.

Resultados finales del 11/10/2026 (comandos con el Python de `.venv`):

| Comando | Resultado |
| --- | --- |
| `python manage.py check` | Sin incidencias. |
| `python manage.py makemigrations --check` | No hay cambios pendientes. |
| `python manage.py test cajas --noinput` | 61 pruebas aprobadas. |
| `python manage.py test cajas core --noinput` | 80 pruebas aprobadas tras ajustar las expectativas de navegación. |
| `python manage.py test --noinput` | 309 pruebas aprobadas, 62,902 segundos. |
| `python manage.py migrate cajas --noinput` | `0004_apertura_inventario_inicial` aplicada correctamente. |
| `python manage.py showmigrations cajas` | Migraciones 0001 a 0004 aplicadas. |
| `git diff --check` | Sin errores de whitespace. |

La primera ejecución de la suite general detectó tres expectativas de los tests
del menú que requerían actualizarse: la nueva clave `es_cajero` y la distinción
entre el enlace exacto `/cajas/` y el prefijo de `/cajas/aperturas/`. Se corrigieron
y se volvió a ejecutar la suite completa con el resultado aprobado indicado.

## Ampliación: Gestión de denominaciones de billetes

Se implementó una interfaz de gestión de denominaciones accesible desde el menú lateral de Global Exchange, sin depender de Django Admin.

La funcionalidad permite:
- Listar denominaciones por moneda, valor y estado.
- Registrar y modificar denominaciones.
- Habilitar y deshabilitar denominaciones.
- Validar valores positivos y evitar duplicados.
- Restringir el acceso a administradores y tesoreros mediante los roles de Keycloak.
- Conservar el historial monetario de aperturas anteriores, incluso cuando se modifican o deshabilitan denominaciones.

Se incorporaron formularios, vistas, rutas, plantillas HTML y pruebas automatizadas.

## Pruebas funcionales manuales

Se verificaron satisfactoriamente:
- Apertura de caja mediante un cajero con asignación vigente.
- Registro de fecha, hora real y responsable.
- Cálculo del saldo inicial a partir del inventario.
- Identificación de cajas con apertura activa.
- Rechazo de aperturas duplicadas, incluso mediante acceso directo al formulario.
- Rechazo de cantidades negativas.
- Rechazo de acceso a las aperturas por un administrador sin rol cajero.
- Registro, modificación, habilitación y deshabilitación de denominaciones.
- Rechazo de denominaciones duplicadas.

Las pruebas de inventarios con varias monedas y de acceso a cajas ajenas fueron cubiertas mediante tests automatizados, sin una comprobación manual adicional.

Durante una primera solicitud de apertura se presentó una respuesta HTTP 403 por ausencia del rol cajero en los claims verificados. Posteriormente, el acceso funcionó al recargar. La causa del incidente no fue determinada y queda registrada para seguimiento si vuelve a producirse.

## Verificación final

El 11/10/2026 se ejecutó nuevamente la suite general del proyecto:

- `python manage.py check`: sin errores.
- `python manage.py test`: 322 tests aprobados.
- `git diff --check`: sin problemas de formato detectados.

## Resultado

Se implementó SCRUM-26 — HU-34, incluyendo apertura de caja, inventario inicial por moneda y denominación, cálculo de saldos, identificación del cajero mediante Keycloak y restricciones contra aperturas simultáneas.

Se incorporó adicionalmente la gestión de denominaciones para administradores y tesoreros desde la interfaz principal.

Las funcionalidades principales fueron verificadas desde el navegador y mediante pruebas automatizadas. La suite general del proyecto finalizó con 322 tests aprobados.

Se dejó preparado el contrato de servicios para que Dev 4 pueda implementar movimientos de efectivo, cierre y arqueo de caja. Estas funcionalidades no forman parte de SCRUM-26.
