# CHIA - PDO: Documentación automática con Sphinx

## Herramienta utilizada
ChatGPT (OpenAI) y Codex.

## Enlace a la conversación
[Conversación con ChatGPT](https://chatgpt.com/)

## Resumen de la asistencia
Se utilizó asistencia de IA para configurar documentación automática del código fuente mediante Sphinx y docstrings compatibles con `sphinx.ext.napoleon`.

También se utilizó Codex para agregar docstrings en español a clases, métodos y funciones relevantes de los módulos del proyecto, sin modificar la lógica existente.

## Decisiones tomadas con asistencia de IA
- Utilizar Sphinx como herramienta de documentación automática.
- Utilizar docstrings en español con formato compatible con Napoleon.
- Habilitar las extensiones `autodoc`, `napoleon` y `viewcode`.
- Integrar Sphinx con la configuración de Django.
- Crear documentación para los módulos:
  - clientes
  - core
  - cotizaciones
  - config
- Excluir `docs/build/` del repositorio mediante `.gitignore`.
- No documentar migraciones históricas para evitar modificar archivos que forman parte del historial de la base de datos.
- No exponer variables sensibles de `config.settings` mediante `:members:`.
- Agregar Sphinx a `requirements.txt`.

## Validaciones realizadas
- Generación correcta de documentación HTML mediante:

  ```bash
  sphinx-build -b html docs/source docs/build/html