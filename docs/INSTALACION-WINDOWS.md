# Instalación y uso en Windows

## Antes de empezar

**Beta 0.1.4 · Windows 10/11 x64.** Validado en Windows 11. La voz incluida requiere **GPU NVIDIA compatible con CUDA y controlador instalado**; se probó en RTX 3060. No se promete una voz CPU equivalente ni la misma velocidad en todos los equipos.

Reservá **25 GB libres para la base**. Para razonamiento local, considerá **15 GB adicionales como orientación**; el espacio y la memoria necesarios dependen del modelo y del equipo. El tamaño del instalador figura en la [Release v0.1.4](https://github.com/guzadev/jarvis/releases/tag/v0.1.4).

## Descarga normal

Desde [Releases](https://github.com/guzadev/jarvis/releases/tag/v0.1.4), bajá **Jarvis-Windows.exe**. Es el asistente de descarga: elegí una carpeta con espacio y pulsá **Descargar e instalar**. Comprueba los archivos con SHA-256 y ejecuta el instalador completo. No descarga ni guarda claves personales.

El instalador permite elegir la ubicación y un modelo de razonamiento local opcional. Crea accesos directos a Jarvis, al instructivo y a Conectar Claude Code. Incluye runtimes, Python, las dependencias preparadas y el perfil de voz. No necesitás instalar Python ni Node por separado.

**Los pesos de los modelos no están dentro del instalador ni en las Releases de GitHub.** Se obtienen desde sus proveedores oficiales.

## Primer inicio: preparar los modelos de voz

Al abrir Jarvis por primera vez descarga automáticamente desde **Hugging Face**:

| Modelo | Uso | Descarga de pesos |
| --- | --- | --- |
| Qwen3-TTS 1.7B Base | Síntesis de la voz local | 4,544 GB |
| Whisper small | Activación local por «Jarvis» | 0,486 GB |
| **Total** | | **5,03 GB** |

Las revisiones están fijadas y los archivos se verifican por SHA-256. La preparación muestra progreso y permite reanudar o cancelar. Necesita Internet y espacio libre; separar estas descargas del instalador no elimina su tamaño ni su almacenamiento local. El perfil de voz elegido se conserva.

Cuando termine, seguí [Clave OpenAI](CLAVE-OPENAI.md), [Claude Code](CONECTAR-CLAUDE.md) y [APIs propias](AGREGAR-APIS.md). Son cuentas tuyas configuradas en tu equipo. La primera frase puede tardar mientras se prepara el modelo de voz.

## Elegir un modelo de razonamiento local

El motor local es opcional; la conversación principal conserva OpenAI y su cobro por uso. Podés elegir **Qwen3 1.7B, 4B, 8B o 14B** en el instalador.

En la app, abrí **Acciones → Motor, voz y carpeta → Modelos locales** para ver los instalados, descargar otro, cambiar el que usás o eliminar uno anterior. El runtime de Ollama se descarga desde sus Releases oficiales y los modelos, desde el registro de Ollama. Los tamaños y las notas de memoria son orientativos.

El motor actual se conserva hasta que la preparación termina correctamente. La descarga muestra progreso y se puede cancelar. Para borrar un modelo tenés que escribir su nombre exacto; el modelo que está en uso queda protegido. Esta selección corresponde al razonamiento y las tareas: el perfil de voz se conserva.

## Descarga manual del instalador

Descargá el EXE `Jarvis-Windows-Instalador.exe` y todas sus partes `.bin`, de la misma versión, a la misma carpeta. Ejecutá ese EXE después de terminar todas las descargas. Si falta una parte, completá las descargas. `Source code.zip` contiene código fuente.

Los SHA-256 de los archivos están en `SHA256SUMS.txt`. Podés comprobar un archivo con:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\Jarvis-Windows-Instalador.exe'
```

El ejecutable no está firmado por un editor comercial. Si Windows o tu antivirus lo bloquea, comprobá el origen oficial y las huellas; este proyecto no modifica esas protecciones. La alternativa manual también necesita descargar los pesos oficiales en el primer inicio.

## Micrófono

La escucha comienza apagada. **ESCUCHA APAGADA · ACTIVAR** habilita el detector local de «Jarvis» mientras usás esa ventana. Al detectarlo, abre la conversación OpenAI. **Apagar** termina la captura y la sesión. Durante la conversación activa, el audio se envía a OpenAI.

Cerrar con X termina la aplicación. Minimizar, ocultar o cambiar de ventana también apaga la escucha. Volvé a activarla cuando regreses. El inicio con Windows es optativo y no se activa solo. Abrir Jarvis al iniciar Windows no activa por sí solo el micrófono.

Windows elige el micrófono disponible. Podés cambiar el dispositivo predeterminado de entrada en Windows; no está fijado a una marca. La salida depende del dispositivo de audio elegido en Windows.

## Archivos y memoria

Los archivos se guardan en `Documentos/Jarvis/General` y en carpetas separadas por proyecto. La memoria es local y no se sincroniza automáticamente entre PCs. No se incluye un historial personal del desarrollador.

## Si algo falla

- **Preparación interrumpida:** volvé a abrir Jarvis y retomá la descarga. Revisá Internet y espacio disponible.
- **Error de saldo OpenAI:** revisá Facturación; la aplicación no puede reponer crédito. La API se paga por separado de ChatGPT Plus/Pro.
- **La voz tarda:** dejá que prepare el modelo y revisá GPU, controlador y espacio. No borres el perfil elegido para reparar una descarga.
- **Modelo local sin preparar:** abrí Modelos locales y revisá el estado. Podés conservar el motor anterior mientras termina.
- **Claude no recibe una tarea:** comprobá `claude auth status --json`, elegí Claude para las acciones y verificá que haya una misión creada.
- **No hay una aplicación de Office:** generar el archivo puede funcionar; abrirlo requiere Excel/Word instalado.
- **Una API no responde:** probá la integración y revisá permisos y cuota de tu cuenta. No publiques la clave para pedir ayuda.

## Actualizar y desinstalar

Descargá la versión nueva del instalador completo desde este repositorio. La aplicación conserva las preferencias y el perfil de voz ya aprobados. El actualizador del compañero solo cambia código del backend/interfaz; no instala un núcleo Electron nuevo.

Podés desinstalar desde Configuración de Windows. Los documentos que creaste se mantienen en Documentos/Jarvis. Usá Modelos locales para eliminar un modelo de razonamiento que ya no necesites. No borres carpetas con claves o modelos de otra instalación para reparar una conexión.
