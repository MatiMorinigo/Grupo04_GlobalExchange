# CHIA - SCRUM-38: HU-07 — Selección y cambio del cliente activo

## Herramienta utilizada
Gemini (google.com)

## Enlace a la conversación
[Conversación con Gemini](https://share.gemini.google/YOLHyIqYgtpN)

## Resumen de la asistencia
Se utilizó IA para guiar la implementación del mecanismo de selección y persistencia del cliente activo, incluyendo:
- Creación del modelo `UsuarioCliente` para vincular un `User` con su `cliente_activo` seleccionado
- Implementación de un componente visual en el panel principal (`home.html`) que muestra el cliente activo actual
- Inclusión de un selector dinámico (`<select>`) para alternar entre los clientes aprobados cuando el usuario posee más de uno
- Creación de la vista `ClienteActivoSeleccionarView` para procesar y validar el cambio de cliente activo
- Asignación automática del primer cliente aprobado como activo cuando el usuario no posea uno configurado previa aprobación

## Decisiones tomadas con asistencia de IA
- Definir `UsuarioCliente` con su propia clave primaria `id` (BigAutoKey) en lugar de usar `primary_key=True` en `OneToOneField`, garantizando compatibilidad completa con Django ORM
- Persistir la selección del cliente activo en la base de datos a través del modelo `UsuarioCliente` para que se mantenga entre sesiones
- Validar del lado del servidor que el usuario solo pueda seleccionar como activo un cliente que tenga en estado `APROBADA`
- Ocultar la sección y componente del cliente activo a usuarios administradores (`is_staff` / `is_superuser`) ya que operan a nivel global del sistema
