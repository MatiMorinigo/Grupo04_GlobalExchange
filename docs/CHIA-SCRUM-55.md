# CHIA - SCRUM-55: Gestión de métodos de pago del cliente (HU 27)

## Herramienta utilizada
Claude Code (Anthropic) - claude.com/code

## Enlace a la conversación
[Conversación con Claude Code](https://claude.ai/code)

## Resumen de la asistencia
Se utilizó IA para reemplazar por completo una implementación previa de esta misma rama (un catálogo de métodos de pago administrado por el admin, sin relación con `Cliente`, que nunca llegó a mergearse a `develop`) por la HU 27 real: que cada **cliente** pueda registrar y administrar sus propias tarjetas para usarlas en sus operaciones cambiarias. Se creó la app `pagos` desde cero, siguiendo el mismo patrón arquitectónico ya validado en `cotizaciones` para `Moneda`/`AuditoriaMoneda`:
- Modelo `MetodoPago` (tarjeta de crédito o débito) con `ForeignKey` a `Cliente` (no a `User`), de forma que el método de pago queda asociado al cliente y persiste aunque el usuario cambie de cliente activo.
- Modelo `AuditoriaMetodoPago` con log de creación, modificación, activación, desactivación y eliminación.
- Vistas web (`MetodoPagoWebListView`/`CreateView`/`UpdateView`/`DeactivateView`/`ActivateView`/`DeleteView`) y API REST equivalente (`serializers.py`), ambas restringidas al cliente activo del usuario autenticado.
- Nuevo mixin `ClienteActivoRequiredMixin` en `core/mixins.py` y helper `obtener_cliente_activo(usuario)` en `usuarios/models.py`, ya que esta lógica estaba duplicada de forma inline en `core/views.py` y `cotizaciones/views.py` y no existía como pieza reutilizable.
- Validación de número de tarjeta (formato + algoritmo de Luhn) y de vencimiento (formato MM/AA, rechazando tarjetas ya vencidas) en `pagos/validators.py`, compartida entre el formulario web y el serializer de la API.
- Ítem de menú "Métodos de pago" en `templates/base.html`, visible para cualquier usuario autenticado (no solo administradores).
- Suite de tests (`pagos/tests.py`) cubriendo el alcance por cliente activo, la auditoría y los casos de seguridad descritos abajo.

## Decisiones tomadas con asistencia de IA
- **No se almacena el número completo de tarjeta ni el CVV.** El formulario y la API piden el número completo únicamente para validarlo (formato y checksum de Luhn); solo se persisten los últimos 4 dígitos (`ultimos_cuatro_digitos`), suficientes para identificar la tarjeta ante el usuario. Es una decisión de seguridad, no un requisito explícito de la historia.
- **Todos los campos son editables excepto `tipo` y `cliente`** (decisión explícita del dueño de la historia): el tipo de tarjeta se deshabilita en el formulario de edición (`disabled=True` + `clean_tipo` que fuerza el valor original, igual que `MonedaForm` hace con `codigo`) y también se descarta explícitamente en `MetodoPagoSerializer.update()` del lado de la API.
- **Se agregaron activar y eliminar, además de desactivar** (decisión explícita, más allá de lo mínimo descrito en los criterios de aceptación): activar/desactivar siguen el patrón idempotente de `MonedaWebActivateView`/`DeactivateView` (no duplican auditoría si el estado ya era el solicitado); eliminar usa el `DeleteView` genérico de Django con página de confirmación.
- **`AuditoriaMetodoPago.metodo_pago` usa `on_delete=SET_NULL` en lugar de `CASCADE`.** Si el usuario elimina definitivamente un método de pago, el registro de auditoría de esa misma eliminación no debe desaparecer junto con él (lo cual pasaría con `CASCADE`, ya que la fila de auditoría referencia justamente al objeto que se está por borrar). El registro se crea primero, mientras el objeto todavía existe, y recién después se ejecuta el borrado; la fila de auditoría sobrevive con `metodo_pago=NULL` y conserva el snapshot completo en `datos_anteriores`.
- **Protección explícita contra IDOR**: toda vista y todo endpoint de API filtra siempre por `cliente=obtener_cliente_activo(request.user)`, nunca solo por el ID del método de pago en la URL. Esto es necesario porque, a diferencia de `Moneda` (datos globales), un método de pago es información sensible de un cliente puntual: sin este filtro, un usuario autenticado podría editar, desactivar o eliminar la tarjeta de otro cliente adivinando su ID.
- **Sin control por rol de Keycloak.** A diferencia de `AdminRequiredMixin`/`EsAdministrador` (usados en `clientes`/`cotizaciones`), acá el control de acceso relevante es "pertenece al cliente activo del usuario", no un rol administrativo, así que las vistas usan el nuevo `ClienteActivoRequiredMixin` y la API solo exige `IsAuthenticated` combinado con el filtrado por cliente activo.

## Validaciones realizadas
- `python manage.py test pagos` (24 tests) y `python manage.py test` completo (99 tests) en verde.
- `python manage.py makemigrations --check` sin cambios pendientes.
- Se detectó que la base de datos local todavía tenía la tabla `pagos_metodopago` con el esquema de la implementación abandonada (marcada como migrada en `django_migrations` pese a tener una definición completamente distinta). Se resolvió con `migrate pagos zero --fake` seguido del borrado de la tabla física vieja (1 fila de prueba, sin datos reales) y la aplicación normal de la nueva migración `0001_initial`.
