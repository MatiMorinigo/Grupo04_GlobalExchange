# CHIA - Bugfix: Permisos mediante Keycloak y ajustes de interfaz

## Herramienta utilizada
ChatGPT (OpenAI) - chatgpt.com

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó ChatGPT como apoyo para corregir problemas detectados luego de integrar las funcionalidades de clientes y asociaciones usuario-cliente.

La asistencia incluyó:
- Identificación del uso incorrecto de `is_staff` e `is_superuser` para determinar permisos administrativos.
- Centralización de la obtención y validación de roles provenientes de Keycloak.
- Creación de funciones reutilizables para consultar roles del usuario.
- Adaptación del permiso `EsAdministrador` para utilizar el rol `administrador` de Keycloak.
- Protección de las vistas web del CRUD de clientes.
- Corrección del acceso administrativo al panel de aprobación y rechazo de solicitudes.
- Adaptación del menú principal y de la barra lateral según los roles del usuario.
- Ocultamiento de funcionalidades administrativas para usuarios sin autorización.
- Mantenimiento de las funcionalidades de asociación con clientes también para usuarios administradores.
- Corrección de la visualización del usuario autenticado en la interfaz.
- Implementación de filtros web de clientes por estado, categoría y tipo.
- Integración de búsqueda de clientes por nombre o RUC desde la interfaz.
- Corrección del botón de búsqueda.
- Conservación de filtros durante la paginación.
- Creación del directorio `static` requerido por la configuración de Django.
- Pruebas con usuarios administradores y usuarios sin permisos administrativos.

## Decisiones tomadas con asistencia de IA
- Keycloak se mantiene como fuente de verdad para roles y autorización.
- Se eliminó del código propio el uso de `is_staff` e `is_superuser` para controlar funcionalidades de Global Exchange.
- Se centralizó la lectura de roles en `core/keycloak.py`.
- Se creó un mixin reutilizable para proteger vistas web administrativas.
- El CRUD de clientes se restringió al rol `administrador` tanto en la API como en las vistas web.
- Las funcionalidades administrativas se ocultan en la interfaz para usuarios sin el rol correspondiente.
- La seguridad no depende únicamente de ocultar elementos del frontend: las rutas protegidas también rechazan accesos directos no autorizados.
- Un administrador conserva también las funcionalidades normales de asociación con clientes.
- Los filtros del listado de clientes pueden combinar estado, categoría, tipo y búsqueda por nombre o RUC.
- Los filtros se aplican mediante el botón `Filtrar` en lugar de ejecutar una consulta al modificar cada selector.
- Se agregó el directorio `static` al repositorio para eliminar el warning de configuración de Django.