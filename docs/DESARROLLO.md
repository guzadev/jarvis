# Arquitectura y desarrollo

Este repositorio contiene las fuentes, pruebas y scripts de empaquetado. Los binarios, runtimes y modelos pesados están en Releases.

- `desktop/`: Electron, pantalla de primera configuración, permisos y empaquetado Inno Setup.
- `server.py`, `app_api.py`: API local FastAPI/Uvicorn.
- `app_runtime.py`: configuración de conversación/tareas, rutas y motores.
- `agent_worker.py`: adaptador Claude Code/OpenAI/Ollama y herramientas OpenJarvis.
- `data_tools.py`: fuentes de datos, APOD y resolución dinámica de lugares.
- `integrations.py`, `integration_store.py`, `integration_http.py`: REST/OpenAPI y claves DPAPI.
- `public/assets/`, `index.html`: interfaz, esfera, voz y resultados.
- `qwen_voice_service.py`: síntesis local; `wake_word.py`: activación local con Whisper.

## Preparar el entorno

Para desarrollar necesitás Windows x64, Python 3.13, Node.js y las dependencias descritas en `requirements*.txt` y `desktop/package.json`. Usá entornos virtuales y copiá `.env.example` a `.env` solo si preferís configurar tu propia clave por archivo. Nunca versionés `.env`.

La versión completa instalada ofrece una distribución preparada de Python y modelos. El script `desktop/stage-offline.py` requiere esas dependencias y modelos preparados en el almacenamiento indicado; no son archivos que aparezcan al hacer git clone.

```powershell
cd desktop
npm ci
npm test
npm run pack
```

Pruebas Python desde la raíz, con un entorno preparado:

```powershell
python -m unittest discover -s tests -p 'test*.py'
```

Las pruebas usan respuestas simuladas. No deben abrir el micrófono ni consumir una clave real.

## Compilar el instalador completo

Usá Inno Setup y `desktop/build.ps1` con una carpeta nueva de salida y el almacenamiento preparado. El script incluye Python, entornos y el perfil aprobado por listas controladas; no copia la configuración personal ni los pesos. Los modelos se descargan de Hugging Face y Ollama, con versiones y comprobaciones fijadas. `--include-models` en stage-offline.py queda reservado a una compilación privada offline que no debe subirse a Releases.

Para reconstruir una versión a partir de una carga offline limpia anterior, `scripts/stage-release.py` reutiliza exclusivamente su manifiesto, excluye los modelos y actualiza el núcleo y el backend. Verificá siempre los archivos y las huellas antes de publicar. El descargador de Windows se compila desde `desktop/download/Downloader.cs`, con el manifiesto de archivos de esa versión embebido.

## Privacidad al publicar

No publicar `.env`, archivos `.jarvis-*`, DPAPI, SQLite, proyectos, artefactos personales, cookies, sesiones Claude, grabaciones de referencia ni carpetas de caché. Los pesos de modelos no se distribuyen en GitHub. El perfil de voz genérico sí forma parte del instalador; el perfil incluye el texto genérico de referencia necesario para la síntesis.

Este repositorio se inició desde una exportación limpia del código, sin historial privado. Los archivos de ejemplo contienen valores vacíos o fixtures artificiales. Las versiones deberían incluir SHA-256 y sus notas de compatibilidad; no se anuncia compatibilidad con todo hardware por haber probado un único equipo.

## Gestor de modelos

`bootstrap_models.py` prepara los pesos de voz y activación desde sus publicadores. `local_models.py` administra Ollama y los modelos de razonamiento; las rutas `/api/agent/local/*` muestran inventario, descarga, selección y borrado. Cambiar un modelo de tareas conserva la voz y el proveedor de conversación efectivo. El instalador puede dejar una selección inicial que la app completa al abrir.
