# Conectar Claude Code con tu Jarvis

OpenAI mantiene la conversación en tiempo real. Claude Code ejecuta el razonamiento de las misiones a través de las herramientas de Jarvis. La voz elegida sigue siendo Qwen local. **Claude abierto en una web no equivale a tener Claude Code conectado en esta PC.**

## 1. Instalar el programa oficial

Necesitás una cuenta con acceso a Claude Code. En Windows abrí PowerShell y ejecutá el comando oficial:

```powershell
irm https://claude.ai/install.ps1 | iex
```

También existe la opción oficial `winget install Anthropic.ClaudeCode`. Seguí [la documentación de instalación de Anthropic](https://code.claude.com/docs/en/setup). Git para Windows es opcional para este adaptador; las herramientas nativas de Claude están desactivadas durante las misiones de Jarvis.

Cerrá y volvé a abrir PowerShell. Comprobá:

```powershell
claude --version
```

## 2. Iniciar sesión

Desde el menú Inicio abrí **Jarvis → Conectar Claude Code**. Es un acceso directo al script de conexión que acompaña al instalador. También podés abrir `backend/CONECTAR_CLAUDE.cmd` en la carpeta donde instalaste Jarvis.

1. Se abre una terminal y la página oficial de inicio de sesión.
2. Entrá con **tu cuenta** y autorizá Claude Code.
3. Si la terminal pide un código, pegalo en esa terminal. Si informa que está listo o pide Enter, seguí esa indicación. No publiques códigos ni tokens.
4. La terminal informa si quedó conectado.

Comprobación manual opcional:

```powershell
claude auth status --json
```

Debe indicar `loggedIn: true`. La autenticación queda en tu perfil de Windows, fuera del repositorio.

## 3. Elegirlo en Jarvis

1. Abrí Jarvis → **Misiones**.
2. En el motor de tareas elegí **Claude Code** y guardá la configuración.
3. Comprobá la conexión desde **Conexión → Verificar conexión**.
4. La conversación sigue en OpenAI y la voz local se conserva. En una instalación nueva esta separación ya viene configurada.

## 4. Probar una tarea real

Por voz: «Jarvis, creá una calculadora web sencilla y abrila en Chrome».

Debe aparecer una misión. Claude escribe el HTML y la herramienta `open_web_project` lo abre en Chrome o Edge. Los archivos quedan en `Documentos/Jarvis/General`. Crear una aplicación tarda más que una respuesta conversacional. No repitas el pedido mientras la misión siga en curso.

Podés pedir primero algo más corto: «Creá un archivo prueba.txt que diga que esta es mi primera tarea con Jarvis».

## Qué conexión utiliza

El adaptador usa la **CLI oficial con tu sesión de Claude**, no una clave Anthropic incluida por el desarrollador. Claude razona y solicita herramientas; el compañero local las ejecuta. El acceso puede depender de tu plan y sus límites. No significa uso ilimitado ni acceso automático a tus correos o redes.

Python o PowerShell de propósito general requieren revisar y aprobar la ejecución propuesta. Crear un HTML y abrirlo con la herramienta dedicada no instala dependencias ni ejecuta un lote arbitrario de sistema.
