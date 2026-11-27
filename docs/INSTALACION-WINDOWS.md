# Instalación y uso en Windows

## Descarga normal

Desde [Releases](https://github.com/guzadev/jarvis/releases/tag/v0.1.3), bajá **Jarvis-Windows.exe**. Elegí una carpeta con espacio y pulsá **Descargar e instalar**. Comprueba los archivos con SHA-256 y ejecuta el instalador completo. No descarga ni guarda claves personales.

El instalador permite elegir la ubicación. Crea accesos directos a Jarvis, al instructivo y a Conectar Claude Code. Si la síntesis local no dispone de una GPU NVIDIA compatible, no se promete una voz CPU equivalente.

## Descarga manual

Descargá el EXE `Jarvis-Windows-Instalador.exe` y todas sus partes `.bin`, de la misma versión, a la misma carpeta. Ejecutá ese EXE después de terminar todas las descargas. Un mensaje de parte faltante se resuelve completando las partes, no descargando `Source code.zip`.

Los SHA-256 de los archivos están en `SHA256SUMS.txt`. Podés comprobar un archivo con:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\Jarvis-Windows-Instalador.exe'
```

El ejecutable no está firmado por un editor comercial. Si Windows o tu antivirus lo bloquea, comprobá el origen oficial y las huellas; este proyecto no modifica esas protecciones.

## Primera configuración

Seguí [Clave OpenAI](CLAVE-OPENAI.md), [Claude Code](CONECTAR-CLAUDE.md) y [APIs propias](AGREGAR-APIS.md). Son cuentas tuyas, configuradas en tu equipo. El perfil de voz incluido se carga localmente y puede tardar en preparar la primera frase.

## Micrófono

La escucha comienza apagada. **ESCUCHA APAGADA · ACTIVAR** habilita el detector local de «Jarvis» mientras usás esa ventana. Al detectarlo, abre la conversación OpenAI. **Apagar** termina la captura y la sesión.

Cerrar con X termina la aplicación. Minimizar, ocultar o cambiar de ventana también apaga la escucha. Volvé a activarla cuando regreses. El inicio con Windows es optativo y no se activa solo. Si querés abrir Jarvis al iniciar Windows, podés habilitar la opción de su bandeja; eso no activa por sí solo el micrófono.

Windows elige el micrófono disponible. No está fijado a una marca: podés cambiar el dispositivo predeterminado de entrada en Windows. Auriculares y parlante pueden ser dispositivos diferentes; la salida depende de la salida de audio de Windows.

## Archivos y memoria

Los archivos se guardan en `Documentos/Jarvis/General` y en carpetas separadas por proyecto. La memoria es local y no se sincroniza automáticamente entre PCs. No se incluye un historial personal del desarrollador.

## Si algo falla

- Error de saldo OpenAI: revisá Facturación; la aplicación no puede reponer crédito.
- La voz tarda en cargar: dejá que prepare el modelo; revisá GPU, controlador y espacio disponible.
- Claude no recibe una tarea: comprobá `claude auth status --json`, elegí Claude en Misiones y verificá que haya una misión creada.
- No hay una aplicación de Office: generar el archivo puede funcionar, pero abrirlo requiere Excel/Word instalado.
- Una API no responde: probá la integración y revisá permisos/cuota de tu cuenta. No publiques la clave para pedir ayuda.

## Actualizar y desinstalar

Descargá la versión nueva del instalador completo desde este repositorio. La aplicación conserva las preferencias y el perfil ya aprobados. El actualizador del compañero solo cambia código del backend/interfaz, no instala un núcleo Electron nuevo ni modelos adicionales.

Podés desinstalar desde Configuración de Windows. Los documentos que creaste se mantienen en Documentos/Jarvis. No borres carpetas con claves o modelos de otra instalación para intentar reparar una conexión.
