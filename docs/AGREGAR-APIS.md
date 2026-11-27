# Agregar tus propias APIs

Las claves se cargan una sola vez **en tu PC**, no en el repositorio. Jarvis las guarda cifradas para tu usuario Windows. No uses las claves de otra persona ni las pongas en ejemplos compartidos.

## A. Servicios ya incorporados

1. Abrí **Integraciones** en Jarvis.
2. Pulsá **Fuentes de datos de Jarvis**.
3. Elegí el servicio y seguí el enlace a su sitio oficial para crear tu propia clave.
4. Pegá la clave en el campo de contraseña y pulsá **Guardar clave**.

| Servicio | Para qué se usa | Clave |
| --- | --- | --- |
| TomTom | Resolver lugares, flujo e incidentes de tránsito | Propia de TomTom |
| Finnhub | Acciones y noticias de empresas | Propia de Finnhub |
| CoinGecko | Criptomonedas | Clave Demo propia |
| NASA APOD | Publicación astronómica del día | La fuente pública utilizada no exige clave; campo opcional |
| GNews | Respaldo para noticias | Propia si querés ese respaldo |
| Open-Meteo | Clima de una ubicación resuelta | No requiere clave para esta fuente |
| Google News RSS | Noticias | No requiere clave |
| DolarAPI | Cotizaciones del dólar | No requiere clave |
| Frankfurter | Tipos de cambio de referencia | No requiere clave |

Las condiciones y cuotas pueden cambiar. Que una API tenga un plan gratuito no significa que el razonamiento de OpenAI o Claude sea gratuito. Para clima de un lugar nuevo se usa TomTom para identificarlo; esa resolución sí necesita tu clave TomTom.

## B. Sumar una API nueva con OpenAPI

1. Entrá en **Integraciones → Añadir**.
2. Elegí importar **OpenAPI 3.0 o 3.1 en JSON**.
3. Pegá la especificación del servicio. El archivo describe su URL, rutas, parámetros y funciones.
4. Revisá el nombre y seleccioná solo las funciones que querés habilitar.
5. Configurá la autenticación: sin clave, Bearer, API key en encabezado o API key en la URL, según indique ese proveedor.
6. Cargá **tu** clave, si corresponde.
7. Indicá si el servicio es gratis, pago o de costo desconocido y fijá un máximo diario de solicitudes.
8. Guardá y usá **Configurar y probar** para comprobar una operación.
9. Pedile a Jarvis que utilice esa integración por su nombre y función.

### Ejemplo sin clave: Open Library

En [examples/openlibrary.openapi.json](../examples/openlibrary.openapi.json) tenés una especificación mínima para buscar libros. Copiá ese JSON en la importación, elegí **sin clave**, habilitá `buscar_libros` y guardá. Podés pedir: «Buscá tres libros sobre física usando la integración Open Library».

Este ejemplo no contiene ninguna credencial. [Documentación oficial de búsqueda](https://openlibrary.org/dev/docs/api/search).

## C. Configuración REST manual

Si el proveedor no ofrece OpenAPI, elegí configuración manual e indicá:

- Nombre de la aplicación y URL base HTTPS.
- Cómo autenticar: tipo, nombre exacto del encabezado o parámetro y tu clave.
- Por cada función: nombre, método HTTP, ruta, descripción y parámetros.
- Si necesita un cuerpo JSON, su esquema y si es obligatorio.
- Costo y cupo diario.

Por eso **el nombre de la app y una clave no bastan siempre**: Jarvis necesita saber cómo invocar sus funciones. Usá la documentación oficial del proveedor para completar estos campos.

## Permisos y límites

Las operaciones que modifican datos o cuyo costo no fue autorizado quedan sujetas a revisión. Las consultas de pago pueden exigir aprobación; existe una opción explícita para permitirlas automáticamente. El contador diario limita solicitudes, no pesos ni dólares. El proveedor puede facturar según su propio plan.

Esta versión soporta REST/JSON con los métodos y autenticación indicados. OAuth, APIs con multipart, WebSockets o SDK propietarios pueden necesitar desarrollo adicional. Si una integración requiere iniciar sesión en una cuenta, no pegues las cookies del navegador ni códigos de acceso en los parámetros.
