# CHIA - SCRUM-54

## Historia de Usuario

**SCRUM-54 - HU-19: Asignación automática temporal de categoría VIP**

Como cliente, quiero obtener temporalmente la categoría VIP cuando alcance el volumen de operaciones requerido, para acceder a beneficios preferenciales durante un período determinado, manteniendo mi categoría base original.

## Herramienta de IA utilizada

- **Herramienta:** ChatGPT
- **Uso:** apoyo para análisis, diseño de la solución, revisión de reglas de negocio, elaboración de pruebas unitarias, documentación y revisión de integración.

## Resumen del uso de IA

Se utilizó ChatGPT como herramienta de apoyo durante la implementación de la HU-19. La IA ayudó principalmente a analizar cómo incorporar una promoción VIP temporal sin reemplazar la categoría base del cliente, definir la evaluación mensual del volumen de operaciones y revisar su integración con los módulos existentes de cotizaciones y transacciones.

También se utilizó para proponer y revisar casos de prueba, interpretar errores encontrados durante la implementación y documentar el mecanismo de ejecución automática mensual.

El código y las decisiones finales fueron revisados y validados mediante pruebas ejecutadas localmente por el equipo.

## Principales decisiones tomadas

### 1. Separación entre categoría base y categoría efectiva

Se decidió conservar el campo existente `Cliente.categoria` como categoría base y agregar el concepto de `categoria_efectiva`.

La categoría efectiva devuelve VIP cuando:

- la categoría base del cliente ya es VIP; o
- existe una promoción VIP temporal vigente.

De esta forma, un cliente Minorista o Corporativo puede recibir temporalmente beneficios VIP sin perder su categoría original.

### 2. Vigencia del VIP temporal

Se incorporó el campo:

`Cliente.vip_vigente_hasta`

Este campo almacena la fecha hasta la cual permanece vigente la promoción. Al vencer, `categoria_efectiva` vuelve automáticamente a la categoría base sin necesidad de modificar nuevamente el registro del cliente.

### 3. Configuración global

Se agregó `ConfiguracionVIP`, que permite definir:

- `umbral_mensual_pyg`: volumen requerido para obtener VIP temporal.
- `duracion_meses`: cantidad de meses calendario de vigencia.

Se definió que un umbral igual a `0` representa una promoción desactivada.

### 4. Cálculo del volumen mensual

La evaluación utiliza únicamente transacciones con estado `COMPLETADA`.

No se consideran:

- `PENDIENTE`
- `CANCELADA`
- `ANULADA`

El volumen se calcula sumando `subtotal_pyg`, porque representa el valor de la operación expresado en guaraníes antes de beneficios y comisiones.

Las compras y ventas completadas participan del mismo volumen acumulado.

### 5. Momento de evaluación

La evaluación se realiza al inicio de cada mes utilizando las operaciones del mes calendario anterior.

Ejemplo:

- Evaluación: 01/10/2026
- Período analizado: 01/09/2026 al 30/09/2026

Se agregó el parámetro opcional `fecha_referencia` al servicio para facilitar pruebas controladas sin depender de la fecha actual del sistema.

### 6. Renovación

Si el cliente vuelve a alcanzar el umbral mientras posee VIP temporal, la fecha de vencimiento se recalcula desde la nueva evaluación.

La duración no se acumula sobre la vigencia anterior.

### 7. Integración con compra, venta y simulación

Los lugares donde anteriormente se utilizaba directamente `cliente.categoria` para aplicar beneficios fueron adaptados para utilizar `cliente.categoria_efectiva`.

Esto permite que la promoción VIP temporal sea respetada por:

- simulación de cotizaciones;
- compra de divisas;
- venta de divisas.

Las transacciones conservan `categoria_aplicada`, por lo que el historial mantiene la categoría utilizada en el momento de cada operación.

### 8. Ejecución automática

El proyecto no posee actualmente infraestructura propia de Celery/Redis para tareas programadas.

Se creó el management command:

`python manage.py evaluar_vip_temporal`

También permite indicar una fecha para pruebas:

`python manage.py evaluar_vip_temporal --fecha YYYY-MM-DD`

En producción, el comando debe ser ejecutado el día 1 de cada mes mediante el scheduler del servidor, por ejemplo `cron` en Linux.

## Pruebas realizadas

Se agregaron pruebas para verificar:

- mantenimiento de la categoría base;
- categoría efectiva con VIP temporal vigente;
- vencimiento de la promoción;
- permanencia de clientes VIP base;
- asignación al alcanzar exactamente el umbral;
- rechazo cuando no se alcanza el umbral;
- exclusión de transacciones no completadas;
- acumulación de compras y ventas;
- renovación de la vigencia;
- comportamiento cuando no existe renovación;
- desactivación mediante umbral igual a cero;
- acceso y modificación de la configuración VIP;
- control de permisos de administrador;
- aplicación del beneficio VIP temporal en compras;
- aplicación del beneficio VIP temporal en ventas;
- ejecución del management command;
- validación del parámetro `--fecha`.

Además se ejecutaron las pruebas existentes de los módulos `clientes` y `transacciones` para comprobar que los cambios no introdujeran incompatibilidades.

## Archivos principales involucrados

- `clientes/models.py`
- `clientes/services.py`
- `clientes/forms.py`
- `clientes/views.py`
- `clientes/web_urls.py`
- `clientes/tests.py`
- `clientes/management/commands/evaluar_vip_temporal.py`
- `transacciones/services.py`
- `transacciones/tests.py`
- `cotizaciones/views.py`
- `templates/clientes/configuracion_vip_form.html`
- `templates/core/home.html`

## Resultado

La implementación permite asignar y renovar automáticamente una categoría VIP temporal en función del volumen mensual de operaciones completadas, manteniendo intacta la categoría base del cliente y aplicando correctamente los beneficios VIP durante la vigencia de la promoción.
