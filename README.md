# Jarvis para Windows

Asistente de escritorio con conversación en tiempo real, voz generada en tu PC, memoria local y herramientas para crear archivos y consultar información. **Windows x64 solamente. Versión beta 0.1.3.**

## Descargar e instalar

**[Descargar Jarvis-Windows.exe](https://github.com/guzadev/jarvis/releases/download/v0.1.3/Jarvis-Windows.exe)** · [Ver todos los archivos de la versión](https://github.com/guzadev/jarvis/releases/tag/v0.1.3)

1. Descargá **Jarvis-Windows.exe** desde ese enlace. Es el asistente de descarga, no el código fuente.
2. Abrilo, elegí una carpeta con espacio y pulsá **Descargar e instalar**. Descarga las partes del instalador desde este repositorio, verifica sus SHA-256 y abre el instalador completo.
3. Seguí el instalador y abrí **Jarvis** desde el escritorio o el menú Inicio.
4. Pegá **tu propia clave de OpenAI** en el formulario de Jarvis.
5. La escucha empieza apagada. Pulsá **ESCUCHA APAGADA · ACTIVAR** y decí «Jarvis» para conversar. También podés pulsar Iniciar voz.

La descarga completa ocupa varios GB porque contiene Python, las dependencias y los modelos. Reservá **40 GB libres** para descarga e instalación. El descargador necesita Internet y los archivos quedan en la carpeta que elegiste.

Modelos incluidos: **Qwen3-TTS 1.7B Base** para la voz, **Whisper small** para la activación local y **Qwen3 8B** de Ollama como motor local opcional. La configuración inicial conserva OpenAI para conversar; incluir estos modelos no convierte la API de OpenAI en un servicio gratuito.

**Alternativa manual:** descargá `Jarvis-Windows-Instalador.exe` y **todas** las partes `Jarvis-Windows-Instalador-*.bin` de la misma versión. Dejalas juntas en una carpeta y ejecutá ese EXE. `Source code.zip` contiene código; no es el instalador.

### Requisitos

- Windows 10/11 de 64 bits. La instalación se validó en Windows 11.
- **GPU NVIDIA compatible con CUDA y controlador instalado** para la voz local incluida. Probado en una RTX 3060; no se garantiza la misma velocidad en cualquier hardware. Esta edición no ofrece una voz CPU equivalente ni cambia automáticamente la voz.
- Internet y cuenta OpenAI con saldo de API para la conversación principal.
- Una cuenta con acceso a Claude Code si querés usarlo para las tareas.

No hace falta instalar Python ni Node para usar el instalador completo. No se incluyen cuentas, claves, memoria ni proyectos del desarrollador.

## Configuración paso a paso

- **[Crear y cargar tu clave de OpenAI](docs/CLAVE-OPENAI.md)**
- **[Conectar Jarvis con Claude Code](docs/CONECTAR-CLAUDE.md)**
- **[Agregar tus propias APIs, gratis o pagas](docs/AGREGAR-APIS.md)**
- [Instalación, controles y problemas frecuentes](docs/INSTALACION-WINDOWS.md)
- [Cómo está construido y cómo trabajar con el código](docs/DESARROLLO.md)

## Qué podés pedirle

- «¿A cuánto está Bitcoin en dólares? Mostralo en pantalla».
- «Mostrame la publicación astronómica del día de la NASA». Puede ser imagen o video y se presenta dentro de Jarvis.
- «¿Cómo va a estar el clima mañana en Rosario?».
- «¿Cómo está el tránsito cerca del Obelisco de Buenos Aires?». Muestra flujo e incidentes de la zona; **no calcula una ruta ni hora de llegada**.
- «Creá una calculadora web sencilla y abrila en Chrome». Con Claude Code configurado, delega la creación y abre el HTML del proyecto.
- «Creá un Excel con estos datos…». Los trabajos se guardan en `Documentos/Jarvis/General`.

Crear una app es una tarea en segundo plano; no termina al instante. Solo se considera iniciada cuando el motor devuelve una misión. La conversación puede seguir disponible mientras trabaja.

## Cómo funciona

| Parte | Qué hace |
| --- | --- |
| Electron + HTML/CSS/JavaScript | Aplicación de Windows e interfaz con esfera molecular |
| Servicio Python local | Conecta archivos, memoria y herramientas de tu PC |
| OpenAI Realtime + WebRTC | Entiende el audio, conversa y solicita herramientas |
| Qwen3-TTS local | Pronuncia las respuestas con el perfil de voz incluido |
| Claude Code, opcional | Razona sobre las tareas delegadas; usa tu propia sesión |
| OpenJarvis | Orquesta las herramientas del motor de tareas |
| SQLite y Windows DPAPI | Memoria local y protección local de credenciales |

La conversación y las tareas tienen selecciones independientes: podés usar **OpenAI para conversar y Claude para las tareas**, sin reemplazar la voz local. La síntesis local no llama a Fish Audio. No entrenamos un modelo desde cero.

La interfaz [online](https://jarvis-aurelio.vercel.app/) requiere el compañero instalado en **la PC que querés utilizar**. Vercel no ejecuta los modelos de voz ni controla por sí solo tu computadora.

## Control del micrófono y costos

- La escucha arranca **apagada** y se activa por una acción tuya.
- El botón **Apagar** corta el micrófono y la conversación. Cerrar con la X sale de la app, sin ocultarla en la bandeja.
- Ocultar, minimizar o cambiar de ventana también suspende la escucha. Para continuar, volvé a activarla.
- El inicio con Windows es opcional y no se habilita solo.
- La detección de «Jarvis» y la síntesis se realizan localmente. Durante la conversación activa, el audio se envía a OpenAI.
- **OpenAI cobra por uso.** ChatGPT Plus/Pro y el saldo de la API se administran por separado. Claude Code utiliza el acceso y los límites de tu propia cuenta.
- Otras APIs pueden tener cuotas, planes gratuitos o cargos. Un límite de solicitudes de Jarvis no es un límite monetario del proveedor.

## Fuentes e integraciones

Incluye herramientas para clima, tránsito, dólar, divisas, acciones, criptomonedas, noticias y NASA. Cada persona conecta las claves que necesite en **Integraciones → Fuentes de datos de Jarvis**.

También podés importar OpenAPI 3.0/3.1 en JSON o configurar operaciones REST manualmente. No basta siempre con el nombre de la app y una clave: Jarvis necesita conocer la URL y las funciones. OAuth, cargas de archivos y protocolos especiales no son conectores universales automáticos.

## Estado de esta versión

Es una beta para el hardware indicado. Conserva limitaciones: la voz puede variar de timbre en algunas frases; no hay sincronización automática de memoria entre PCs; correo, calendario y redes requieren sus conectores; las tareas ejecutan las herramientas habilitadas, no control ilimitado de cualquier programa. El instalador incluye los componentes, pero no se probó en todos los equipos ni sustituye los controladores NVIDIA.

El ejecutable no tiene firma de editor comercial. `SHA256SUMS.txt` permite comprobar que los archivos coinciden con la versión publicada.

## Código y contribuciones

El código está en este repositorio. Los modelos y ejecutables grandes se distribuyen en Releases, no en Git. Leé [DESARROLLO.md](docs/DESARROLLO.md) para compilar y verificar paquetes. No publiques `.env`, tokens, perfiles personales, bases de datos ni archivos de tus proyectos en issues o pull requests.

Basado en el template de Thomas Berton y ampliado con [OpenJarvis](https://github.com/open-jarvis/OpenJarvis), [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) y [faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts). Se conserva la [licencia del código base](LICENSE); los componentes incluidos conservan sus avisos de terceros. No es un producto oficial de Marvel.
