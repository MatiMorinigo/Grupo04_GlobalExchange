# CHIA - BUGFIX: Ajustes de interfaz y formato numérico

## Herramientas utilizadas
ChatGPT (OpenAI) y Codex.

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia

Se utilizó asistencia de IA para realizar ajustes de presentación y usabilidad en la interfaz de Global Exchange.

Los cambios se limitaron principalmente a la visualización de información y no modificaron la lógica de negocio del sistema.

## Cambios realizados

- Se agregó scroll vertical independiente a la barra lateral para permitir el acceso a todas las opciones en resoluciones o niveles de zoom reducidos.
- Se implementó un filtro reutilizable de Django para mejorar la presentación de valores monetarios.
- Los importes utilizan punto como separador de miles y coma como separador decimal.
- Se eliminaron ceros decimales innecesarios en valores mostrados al usuario.
- Se actualizaron templates de cotizaciones, simulación, configuración y transacciones para utilizar el nuevo formato.
- Se eliminaron visualmente los controles de incremento/decremento de los campos numéricos, manteniendo la escritura manual y las validaciones existentes.
- No se modificaron cálculos, modelos ni reglas de negocio.

## Validaciones realizadas

- `python manage.py check`
- `git diff --check`
- Ejecución completa de pruebas unitarias:

  ```bash
  python manage.py test
  