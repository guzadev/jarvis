# Tu clave de OpenAI

## 1. Crear una clave propia

1. Entrá en [OpenAI Platform](https://platform.openai.com/) con tu cuenta.
2. Revisá [Facturación](https://platform.openai.com/settings/organization/billing) y agregá saldo para usar la API.
3. Abrí [API keys](https://platform.openai.com/api-keys), elegí el proyecto correcto y creá una clave secreta.
4. Copiala para pegarla en **tu Jarvis**, no en GitHub ni en un chat público.

La clave autoriza solicitudes que pueden generar cargos. La API se paga por separado de una suscripción a ChatGPT. Consultá las tarifas y límites de tu cuenta antes de usarla de forma continua.

## 2. Cargarla en Jarvis

1. Instalá y abrí Jarvis.
2. En el primer inicio aparece **Clave de OpenAI**. Pegá tu clave en el campo de contraseña.
3. Pulsá **Conectar y abrir Jarvis**. El campo se vacía después del envío.
4. Jarvis guarda la clave cifrada con Windows DPAPI, vinculada a tu usuario. No va incluida en este repositorio ni en el instalador.
5. La escucha sigue apagada hasta que la actives.

Para cambiarla, con Jarvis abierto usá el icono junto al reloj → **Conexión con OpenAI…**. No hace falta editar código ni enviar la clave a otra persona.

## 3. Primera prueba

Activá escucha y decí: «Jarvis». Después del saludo preguntá: «¿Cuánto es dos más dos?». Apagá escucha al terminar. La voz se genera localmente; OpenAI recibe el audio de la conversación y devuelve el texto y las llamadas a herramientas.

## Problemas habituales

- **Sin crédito / credit_balance_exhausted:** agregá saldo en la cuenta asociada a esa clave. Reintentar no repone el saldo.
- **Límite temporal:** esperá el plazo indicado. No cambies la clave por ese motivo.
- **Clave no aceptada:** comprobá proyecto, permisos y que la hayas copiado completa. No la publiques para pedir ayuda.
- **Sin acceso al modelo:** revisá el acceso del proyecto al modelo configurado.
- **La clave de otra PC no abre:** el cifrado es propio de cada usuario Windows. Cargá tu propia clave en esa PC; no copies archivos DPAPI.

Documentación oficial: [primeros pasos](https://developers.openai.com/api/docs/quickstart) y [errores de API](https://developers.openai.com/api/docs/guides/error-codes).
