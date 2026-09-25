# CHIA - SCRUM-45: HU-11 Compra de divisas

## Herramienta utilizada
Claude Code (Anthropic) - claude.com/code

## Enlace a la conversación
[Conversación con Claude Code](https://claude.ai/code)

## Resumen de la asistencia
Se utilizó IA para implementar la HU-11 (compra de divisas) sobre el modelo `Transaccion` que ya existía en `develop` pero que hasta ahora no tenía ninguna capa de aplicación: la app `transacciones` solo contenía `models.py`, su `admin.py` de solo lectura y sus tests de modelo, sin vistas, formularios, servicios, URLs ni plantillas, y no estaba montada en `config/urls.py`. Se detectaron además dos vacíos que bloqueaban la historia y se resolvieron dentro de la misma rama:

- **No existía ninguna configuración de comisión en el sistema.** `Transaccion.comision_porcentaje` y `comision_monto_pyg` existían como copia, pero ningún modelo, `settings` ni pantalla los definía, pese a que el criterio de aceptación exige "el porcentaje de comisión de compra configurado en el sistema".
- **No existía nada relacionado con destinos de acreditación**, necesarios para que el cliente indique dónde recibir la divisa comprada.

Trabajo realizado:

- Modelo `ConfiguracionComision` en `cotizaciones/models.py`, de fila única, con los porcentajes de compra y venta, editable desde la sección **Configuración** del menú lateral.
- Servicio `transacciones/services.py` con la búsqueda de la cotización vigente, el cálculo completo de la operación (`calcular_compra`) y el alta de la transacción pendiente.
- Flujo web de compra en dos pasos sobre una única vista: carga de los datos (moneda, monto, destino de acreditación y método de pago), resumen con el desglose y confirmación, seguido del comprobante imprimible. Todas las vistas restringidas al cliente activo.
- Aplicación nueva `destinos` con el modelo `DestinoAcreditacion` (cuenta bancaria o billetera electrónica), su CRUD web completo y su auditoría, siguiendo el patrón ya validado en `pagos`.
- Se habilitó el ítem "Operaciones de cambio" del menú lateral y de la página principal, que hasta ahora figuraba como módulo no disponible.

## Decisiones tomadas con asistencia de IA

- **La fórmula de cálculo se dedujo de los tests ya existentes, no se inventó.** `transacciones/tests.py` fijaba un caso de 100 USD a un precio de venta de 7350, con beneficio VIP del 5 % y comisión del 1 %, cuyos importes esperados eran subtotal 735.000, beneficio 36.750, comisión 7.350 y total 705.600. El único cálculo compatible es `total = subtotal - beneficio + comision`, con el beneficio y la comisión aplicados sobre el subtotal en guaraníes. Un segundo caso del mismo archivo (la misma operación recalculada a 7400) confirma la fórmula. Se implementó exactamente esa, de modo que los doce tests de modelo preexistentes siguen siendo la referencia.

- **`ConfiguracionComision` se ubicó en `cotizaciones` y no en `clientes` ni en `transacciones`.** Situarla en `clientes` habría creado un ciclo de importación, porque `cotizaciones/services.py` ya importa de `clientes.models`. Situarla en `transacciones` habría obligado a que `cotizaciones` dependiera de `transacciones`. En `cotizaciones` conviven con `Moneda` y `TasaCambio`, que es donde está el resto de los parámetros del cálculo cambiario.

- **El modelo de comisión es de fila única (patrón *singleton*).** `save()` fuerza siempre la clave primaria 1 y `obtener()` crea la fila en cero si no existe. La alternativa de poner la comisión en `Moneda` o en `TasaCambio` se descartó: el criterio de aceptación habla de una comisión "configurada en el sistema", no por divisa ni por cotización, y esas opciones habrían modificado modelos mantenidos por otros integrantes del equipo.

- **No se modificó `simular_conversion()`.** El simulador (SCRUM-44 y SCRUM-56) aplica el beneficio de compra mediante una *tasa preferencial* sobre el monto en guaraníes entregado, que es un criterio distinto del que fijan los tests de `Transaccion`. Ambos conviven: el simulador es una estimación sin registro y el servicio de transacciones es el cálculo que se persiste. Tocar el simulador habría roto sus tests y generado conflicto con el trabajo de otro integrante.

- **El usuario ingresa el monto en la divisa que compra, no en guaraníes.** Es lo que modela `Transaccion.monto_divisa`, evita ambigüedades de redondeo en la conversión inversa y coincide con la forma en que están escritos los tests preexistentes.

- **Un solo modelo `DestinoAcreditacion` con campo `tipo`, en lugar de dos modelos separados.** Replica exactamente el patrón de `pagos.MetodoPago`: campos opcionales por tipo, coherencia forzada en `Model.clean()`, en el formulario y con JavaScript en la plantilla. Evita duplicar vistas, formularios, URLs y plantillas, y mantiene el código familiar para el equipo.

- **Cada destino se registra en una sola moneda (`ForeignKey` a `Moneda`).** Una cuenta bancaria real solo recibe acreditaciones en la moneda en que fue abierta. Esto convierte la regla "la cuenta debe admitir esa divisa" en un filtro directo, validado en tres capas: el *queryset* del formulario de compra, su método `clean()` y el `clean()` de `Transaccion`.

- **El catálogo de bancos es una lista fija en el formulario**, igual que los proveedores de billetera de `pagos`, porque no existe un módulo de administración de entidades bancarias. Se extrajo la lista de proveedores a `pagos/constants.py` para que las billeteras de métodos de pago y las de destinos de acreditación ofrezcan el mismo catálogo en lugar de duplicarlo.

- **El alcance llega hasta el paso previo al pago.** La historia termina en "podrá continuar con el proceso de pago", de modo que la confirmación del pago y el paso a estado `COMPLETADA` quedan como punto de entrada de la historia siguiente. `porcentaje_venta` queda creado y configurable, pero todavía sin flujo que lo consuma.

- **No se incluyó la pantalla de consulta del historial de transacciones**, que corresponde a otra historia a cargo de otro integrante del equipo. Solo se implementaron el resumen de la operación recién registrada y su comprobante, porque el flujo de esta historia termina ahí. La ruta `/transacciones/` no expone un listado: el módulo entra por `/transacciones/compra/`.

- **La transacción se persiste recién al confirmar.** El resumen que ve el cliente es una previsualización que no toca la base de datos: se calcula con `calcular_compra()` y se muestra sin guardar nada. Solo al pulsar "Confirmar compra" se crea la fila en estado `PENDIENTE`. Esto evita acumular transacciones abandonadas por clientes que se arrepienten al ver el total.

- **El paso de confirmación se resuelve sin estado de sesión**, siguiendo la decisión que el equipo ya había tomado en `docs/CHIA-SCRUM-57.md` y el patrón de `TasaCambioEditarView`: un campo oculto `confirmado` distingue el envío que pide el resumen del que registra la operación, y el resumen reenvía los datos por campos ocultos. Una sola vista y una sola URL.

- **El cambio de cotización se detecta con un campo oculto `id_tasa_vista`**, que viaja en el resumen con el identificador de la cotización usada para calcularlo. Al confirmar, la vista compara ese valor con la tasa vigente en ese instante; si difieren, recalcula, muestra la advertencia con los importes nuevos y no persiste nada. Aceptar la nueva cotización es, simplemente, volver a confirmar.

- **La cancelación de una transacción ya `PENDIENTE` quedó fuera de esta historia.** Como la operación no existe hasta que se confirma, el botón "Cancelar compra" del resumen solo descarta el formulario. Cancelar una operación pendiente se hará desde el historial de transacciones, en otra historia a cargo de otro integrante, junto con el pago. Por eso se retiraron del servicio `recalcular_con_nueva_tasa()` y `cancelar_transaccion()`, que habrían quedado sin consumidor.

- **El comprobante es HTML imprimible, no un PDF generado en el servidor.** El proyecto no tiene ninguna librería de PDF y agregar una (ReportLab o WeasyPrint) obligaría a todo el equipo a reinstalar dependencias, con el agravante de que WeasyPrint requiere GTK en Windows. La plantilla `templates/transacciones/comprobante.html` usa un bloque `@media print` que oculta el menú lateral, la cabecera y los botones, y un botón que llama a `window.print()`; desde ahí el navegador permite guardar como PDF.

- **Se agregó la clave foránea `metodo_pago` a `Transaccion`**, obligatoria en el formulario pero `null=True` en la base para no invalidar filas previas. Registra con qué medio se abonará la operación; la integración real del pago (SIPAP) corresponde a una historia posterior.

- **Protección contra IDOR en todas las vistas nuevas**, siguiendo lo establecido en SCRUM-55: toda consulta filtra por `cliente=obtener_cliente_activo(request.user)`, de modo que un usuario autenticado no puede ver la operación ni el comprobante de otro cliente, ni usar un destino de acreditación o un método de pago ajeno.

## Validaciones realizadas

- `python manage.py test` completo en verde: **180 tests**, sin fallos ni errores, sobre PostgreSQL.
- Por aplicación: `destinos` 19 tests, `transacciones` 38 tests (los 12 de modelo preexistentes más 26 nuevos), `cotizaciones` 57 tests.
- Entre los tests del flujo se verifica explícitamente que el primer envío **no persiste nada** (`Transaccion.objects.count() == 0`), que la advertencia por cambio de cotización tampoco persiste, y que el método de pago y el destino de otro cliente son rechazados por el formulario.
- Los doce tests de modelo que ya existían en `transacciones/tests.py` pasan sin modificaciones, lo que confirma que la fórmula implementada coincide con la que el equipo había fijado.
- `python manage.py makemigrations --check --dry-run` sin cambios pendientes.
- `python manage.py check` sin incidencias.
- `sphinx-build -b html docs/source docs/build/html` correcto; el único aviso (`html_static_path entry '_static' does not exist`) es previo a esta rama y no guarda relación con estos cambios.

### Tests ajenos que fue necesario actualizar

- `core/tests.py`: dos comprobaciones daban por sentado que "Operaciones de cambio" era un módulo no disponible (`test_home_renders_for_anonymous_user` y `test_upcoming_modules_are_not_keyboard_links`). Como esta historia habilita justamente ese módulo, se actualizó el texto esperado. Para un visitante sin sesión iniciada, la tarjeta y el ítem del menú siguen sin ser enlaces navegables, pero ahora indican "Iniciá sesión para operar" en lugar de "Módulo aún no disponible", que ya sería incorrecto.
- `clientes/tests.py` **no** se modificó. La página de configuración pasó a ser el punto central de configuración del sistema, con el título "Configuración del sistema" y dos secciones, pero el encabezado de la tabla de beneficios conserva el texto exacto que ese test verifica.
