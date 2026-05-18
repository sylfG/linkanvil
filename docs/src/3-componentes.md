<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# 🧩 Componentes Detallados

</div>


Este documento describe cada uno de los 22 servicios que componen LinkAnvil con una **analogía pedagógica**, un bloque *¿Qué hace?* (responsabilidades en lenguaje claro) y un bloque *¿Por qué se tomó esta decisión?* (motivación de la elección).

- Para puertos, imágenes, límites de RAM/CPU y otros datos operativos consulta el [catálogo de contenedores](./2_resumen_servicios.md).
- Para flujos de trabajo, decisiones de persistencia, seguridad, schema isolation, migraciones y observabilidad consulta [`4_arquitectura.md`](./4_arquitectura.md).

---

## Tabla de contenidos

1. [Gateway y Acceso Público](#1-gateway-y-acceso-público)
2. [Capa de API y Frontend](#2-capa-de-api-y-frontend)
3. [Workers Asíncronos](#3-workers-asíncronos)
4. [Motor LLM y Orquestación](#4-motor-llm-y-orquestación)
5. [Almacenamiento y Mensajería](#5-almacenamiento-y-mensajería)
6. [Observabilidad](#6-observabilidad)

---

## 1. Gateway y Acceso Público

### 🚪 Traefik — Recepción del clúster

*Analogía:* Imagina un hospital gigantesco con muchas alas diferentes. En lugar de tener una puerta a la calle para Cardiología, otra para Pediatría y otra para Urgencias, hay una única Gran Recepción (Traefik). El recepcionista verifica adónde vas, te pone una pulsera numerada para seguir tu historial médico, y si hay demasiada gente queriendo entrar al mismo tiempo, los hace pasar en orden. Si en Pediatría no contestan el teléfono al primer intento, el recepcionista vuelve a llamar un par de veces por ti.

**¿Qué hace?**

Traefik actúa como el sistema de recepción inteligente y centralizado del clúster.

- **Enrutamiento Automático:** Es la única puerta por la que entra el tráfico. Lee la dirección exacta que estás visitando (por ejemplo, `ingest.localhost`) y te dirige al contenedor correcto que sabe cómo responderte.
- **Control de Multitudes (Rate Limiting):** Para prevenir sobrecargas o ataques, bloquea automáticamente los excesos impidiendo que entren demasiadas peticiones de golpe (el máximo promedio es de 100 por segundo por usuario).
- **Reintentos a Prueba de Fallos:** Si uno de tus programas internos falla temporalmente al intentar responder, Traefik vuelve a intentar conectarse hasta 3 veces automáticamente antes de devolver un error.
- **Etiqueta de Seguimiento (Trace-ID):** Le coloca un identificador único (como un gafete de visitante numerado) a cada conexión. Esto permite rastrear el recorrido de la petición por todos tus sistemas si necesitas diagnosticar un problema.

**¿Por qué se tomó esta decisión?**

- **Seguridad Centralizada:** Al tener un único punto de entrada, las reglas pesadas (restricciones, reintentos y seguridad) se aplican una sola vez en la puerta principal. Así, no tienes que programar estas mismas defensas individualmente en cada aplicación de tu sistema.
- **Configuración Invisible:** Traefik es capaz de leer de manera automática las pequeñas etiquetas incrustadas en tus otros programas (labels de Docker). Esto permite que el sistema sepa adónde dirigir el tráfico sin necesidad de crear ni actualizar documentos de configuración larguísimos y propensos a errores humanos.
- **Monitoreo Transparente:** Avisa a tus herramientas de vigilancia (Prometheus y OpenTelemetry) qué rutas fallan y cuánto tardan en responder.
- **Seguridad Web en Producción:** Cuando pasas el sistema a la versión de vida real en internet, Traefik se encarga por sí solo de solicitar los candados de seguridad (certificados Let's Encrypt) y fuerza a que todo el mundo use conexiones cifradas (convierte HTTP normal a HTTPS).

### 🔌 Tailscale Funnel — Túnel Telegram (sidecar opcional)

*Analogía:* Imagina que tu casa (tu red local) no tiene buzón en la calle por seguridad. Tailscale Funnel es un apartado postal oficial y seguro que tú configuras en la oficina de correos. Cuando Telegram envía una carta allí, un mensajero de confianza la introduce mágicamente directo en tu escritorio, sin necesidad de abrir la puerta de tu casa.

**¿Qué hace?**

El bot de Telegram exige que LinkAnvil exponga `POST /webhook/telegram/{token_hash}` en una URL HTTPS pública. En entornos detrás de NAT no la hay, y `INGESTION_URL=http://ingestion-api:8000` solo es resoluble dentro de `cerebro-net`. La solución es un sidecar `tailscale/tailscale:stable` (profile `telegram`) que se conecta a la tailnet del usuario, declara un proxy `serve.json` hacia `ingestion-api:8000` y publica al exterior con `AllowFunnel: true`.

- **Recepción de Webhooks:** Funciona como un buzón seguro. Es la vía exclusiva por la cual el bot de Telegram envía los mensajes hacia LinkAnvil.
- **Dirección Web Fija:** Proporciona una URL pública permanente (`https://linkanvil-ingest.<tailnet>.ts.net`) que se inyecta en `PUBLIC_INGESTION_URL` del `.env` para que `cerebro-api` la use al llamar a `setWebhook` de Telegram.
- **Activación Manual:** Este servicio no se enciende solo. Requiere arrancar con `docker compose --profile telegram up -d`.
- **Seguridad sin Privilegios:** Opera sin pedir permisos delicados al sistema operativo. Las reglas de proxy se guardan en `serve.json`.

**¿Por qué se tomó esta decisión?**

Tailscale Funnel sobre Cloudflare Tunnel/ngrok porque (a) es gratuito sin necesidad de dominio propio, (b) el subdominio se mantiene fijo entre `docker compose down/up` mientras viva el volumen `tailscale-state`, (c) HTTPS con cert Let's Encrypt es automático, (d) no requiere abrir puertos en el router.

**Limitaciones:**

- El enlace solo funciona mientras el contenedor esté encendido — suficiente para webhooks, no para alta disponibilidad.
- Funnel sólo expone los puertos públicos 443/8443/10000.

Los pasos de configuración están en [`1_instalacion_y_configuracion.md`](./1_instalacion_y_configuracion.md) sección 6.4.

---

## 2. Capa de API y Frontend

### 📥 cerebro-ingestion — Recepción rápida

*Analogía:* Imagina la oficina de correos de un edificio gigante. Este servicio es el empleado de la ventanilla rápida. Cuando le entregas una carta (enlace), él no la abre para leerla; solo mira rápidamente su libreta para ver si ya le entregaste una igual (duplicado) y revisa que no le hayas traído 500 cartas hoy (control de abuso). Si todo está en orden, lanza la carta al cajón de procesamiento y te dice "¡Recibido!", despachándote al instante.

**Código:** `src/ingestion/main.py`

**¿Qué hace?**

Es un servicio ligero dedicado exclusivamente a recibir enlaces nuevos (ya sea desde la extensión de tu navegador, Telegram u otras aplicaciones). Antes de poner el enlace en la cola de trabajo, realiza dos filtros ultrarrápidos:

- **Filtro de Duplicados:** Utiliza una herramienta de memoria rápida (Bloom Filter en Redis) para comprobar en milisegundos si ese enlace ya existe en el sistema. El bloom es un *hint*, no un veto — la idempotencia real se resuelve aguas abajo.
- **Control de Abusos (Rate Limiting):** Verifica al instante quién está enviando el enlace y bloquea a los usuarios que estén enviando demasiadas peticiones al mismo tiempo.

**¿Por qué se tomó esta decisión?**

- **Respuestas Instantáneas:** Al separar la recepción de la lectura profunda del texto (scraping), el usuario no tiene que esperar con una pantalla de carga; el sistema le confirma la recepción de inmediato con un `202 Accepted`.
- **Corrección de Errores Ocultos:** El mecanismo de "control de abusos" se actualizó para hacer su comprobación en un solo paso indivisible (atómico, `INCR+EXPIRE`). Antes usaba dos pasos (leer y luego sumar), lo cual causaba errores si llegaban dos enlaces al mismo milisegundo. Además, ahora la comunicación se hace de forma "asíncrona", lo que significa que el programa no se queda congelado esperando respuestas.

### ⚙️ cerebro-api — Backend central

*Analogía:* Es el gerente central de un banco. Verifica tu identidad al entrar, lleva un registro exacto de cada movimiento que haces en tu cuenta y, cuando pides un análisis complejo, coordina a los especialistas (Inteligencia Artificial y motores de búsqueda) para entregarte un reporte detallado.

**Código:** `src/api/main.py`

**¿Qué hace?**

Es el "cerebro" central (backend) que conecta la interfaz que ve el usuario con las bases de datos.

- **Gestión de Usuarios:** Controla quién entra, quién sale y registra cuentas nuevas (auth JWT en cookie httpOnly + CSRF).
- **Chat Inteligente:** Conecta tus preguntas con la inteligencia artificial y te envía las respuestas poco a poco a medida que se generan (SSE streaming).
- **Gestión de Datos:** Guarda y recupera tu historial de sesiones y mensajes desde la base de datos principal.

**¿Por qué se tomó esta decisión?**

Se reconstruyó este motor por completo para priorizar la seguridad, abandonando el sistema anterior que guardaba las "llaves" del usuario en lugares poco seguros. Sus nuevas defensas incluyen:

- **Cajas Fuertes Temporales (httpOnly):** Guarda el token de acceso en un formato que el navegador web puede usar pero no puede leer directamente. Evita que un XSS robe credenciales.
- **Doble Verificación contra Falsificaciones (CSRF):** Al hacer cambios importantes, el sistema exige que el navegador presente dos credenciales que deben coincidir exactamente.
- **Límites de Seguridad:** Reglas estrictas sobre cuántas veces puedes intentar iniciar sesión o enviar mensajes por minuto, bloqueando ataques automatizados.
- **Ahorro de Recursos (Pool Compartido):** En lugar de abrir y cerrar una conexión HTTP nueva cada vez que consulta a LiteLLM, reutiliza un cliente `httpx.AsyncClient` compartido. Esto ahorra memoria y evita colapso bajo presión.

### 🌐 cerebro-web — Frontend Next.js

*Analogía:* Imagina el tablero de mandos de un coche moderno. Es la pantalla táctil que tocas para interactuar con el vehículo. Si la aplicación de la radio (un componente) tiene un error y se reinicia, el motor del coche, los frenos y el velocímetro siguen operando sin problema. Además, la pantalla guarda tu música favorita en una caja fuerte central protegida, no en una memoria frágil detrás de la pantalla que cualquiera podría sacar.

**Código:** `src/frontend/`

**¿Qué hace?**

Es la página web principal del sistema, construida con Next.js 15 y React.

- **Punto de Acceso:** Una pantalla segura para iniciar y cerrar sesión.
- **Chat Interactivo:** Conversación con la IA con respuestas en streaming palabra por palabra (SSE).
- **Panel de Control:** Espacio para ver todos los enlaces guardados y revisar el historial de conversaciones.
- **Diseño Antifragilidad (Límites de Error):** La pantalla está dividida en piezas independientes. Si un bloque falla, el sistema aísla el error para que el resto siga funcionando.

**¿Por qué se tomó esta decisión?**

- **Mayor Seguridad y Control:** Se reemplazó la tecnología anterior (Streamlit) porque era demasiado rígida. No permitía gestionar inicios de sesión complejos ni manejar cookies httpOnly.
- **Sincronización Total:** La tecnología actual se integra con la regla de "doble verificación" CSRF que exige la API central.
- **Secreto de Ubicación:** El diseño asegura que el navegador nunca se entere de cuál es la dirección IP interna del backend (`CEREBRO_API_URL`); esa información se queda exclusiva en el servidor (proxy server-side).
- **Solución a "Mensajes Fantasma":** Antes, los chats se guardaban en `localStorage`. Esto provocaba que, incluso si borrabas el sistema por completo, al volver a entrar aparecieran mensajes viejos. Ahora todo se pide directamente a la base de datos oficial (store Zustand API-backed).

---

## 3. Workers Asíncronos

El sistema usa "trabajadores" silenciosos: son independientes, pueden tomarse su tiempo para leer páginas complejas sin que la aplicación web se quede congelada. Cada uno tiene un sistema de "latidos de corazón" (Heartbeat): envían una señal cada 45 segundos para demostrar que siguen vivos y trabajando; si no lo hacen, el sistema detecta que se han quedado atascados (ver el detalle en [`4_arquitectura.md`](./4_arquitectura.md), sección de Heartbeat).

### 🕷️ cerebro-scraper — El Lector de Páginas

*Analogía:* Imagina a un investigador privado que envías a leer un libro a una biblioteca. A veces el bibliotecario es estricto y no lo deja pasar, así que el investigador usa un disfraz. Una vez adentro, lee el texto importante, le pide a un especialista que haga un resumen de los puntos clave, guarda el reporte en tu archivo y avisa que ya terminó.

**Código:** `src/scraper/worker.py`

**¿Qué hace?**

- **Lectura Inteligente:** Toma los enlaces que acaban de entrar al sistema (cola `q.url.ingesta`). Si la página es sencilla, extrae el texto directamente. Si es una página moderna y compleja, abre un "navegador invisible" Playwright (modo Stealth) en el fondo para poder leerla.
- **Evasión de Bloqueos:** Aplica trucos para saltarse las barreras anti-bot. Incluye reescritura por dominio (`medium.com` → `readmedium.com`).
- **Análisis Inicial:** Tras extraer el texto limpio, se lo envía a LiteLLM para extraer etiquetas y un resumen, y guarda todo en Postgres con un evento Outbox.

**Sistema de Cuarentena Automática:**

A veces, las páginas web se dan cuenta de que somos un robot e intentan bloquearnos mostrándonos páginas de error (ej. "¡Verifica que no eres un robot!"). El scraper reconoce estos mensajes con `_looks_blocked()` (marcadores específicos para evitar falsos positivos como `cdnjs.cloudflare.com`) y un guard de longitud mínima 300 chars. Si esto ocurre, en lugar de guardar texto basura, mueve el recurso a `cuarentena` (sin DLQ) para revisión manual.

**¿Por qué se tomó esta decisión?**

Separar la lectura de textos en un programa independiente permite que la aplicación principal siga funcionando aunque estemos descargando cientos de páginas web muy pesadas. Además, a este trabajador se le asigna mucha más RAM (con `shm_size: 1gb` para Chromium) para que su navegador invisible no colapse bajo presión.

### 🧮 cerebro-embedder — El Traductor Matemático

*Analogía:* Es como un archivero experto en sistemas numéricos. Recibe el texto que el investigador acaba de leer y lo convierte en coordenadas matemáticas precisas. Si ve que ese libro ya fue clasificado el mes pasado para otro cliente, simplemente fotocopia las coordenadas matemáticas en lugar de hacer todo el esfuerzo mental de nuevo.

**Código:** `src/data/embedder_worker.py`

**¿Qué hace?**

- **Conversión a Números (Embedding):** Toma el texto recién extraído (cola `q.embeddings`) y le pide a LiteLLM que lo convierta en vectores de alta dimensionalidad. Esto permite búsquedas por "significado" semántico.
- **Reciclaje Inteligente:** Puesto que las matemáticas de un texto público siempre son las mismas sin importar quién lo guarde, si un usuario guarda un enlace que otro usuario ya había procesado, el embedder simplemente reutiliza los números antiguos (flujo `reused=True`).

**¿Por qué se tomó esta decisión?**

El proceso de traducir palabras a matemáticas es lento y costoso. Al separarlo del scraper, evitamos que un fallo o lentitud en la IA detenga el proceso de recolección de las páginas web. Si algo sale mal en este paso, se puede volver a intentar la traducción más tarde sin tener que volver a entrar a la página original.

### 📤 cerebro-outbox — El Cartero Seguro

*Analogía:* Es un empleado de correo certificado muy meticuloso. Nunca echa una carta al buzón y se olvida de ella. Primero inscribe la carta en un registro oficial con estado "Pendiente" y, solo después de confirmar que el sistema de mensajería la recibió correctamente, le pone el sello de "Enviada".

**Código:** `src/data/outbox_publisher.py`

**¿Qué hace?**

Utiliza el **Patrón Outbox**. Este trabajador revisa constantemente la tabla `cerebro.outbox_eventos` en Postgres buscando tareas recién terminadas por el scraper que necesitan ser enviadas al embedder. Cuando encuentra una, la entrega de forma segura a RabbitMQ.

**¿Por qué se tomó esta decisión?**

Si el scraper intentara guardar su reporte en la base de datos *y al mismo tiempo* enviar la carta de aviso al embedder, un apagón repentino en el instante intermedio haría que se perdiera la notificación para siempre (problema Dual-Write). El Cartero Seguro garantiza que los mensajes jamás se pierdan ni se queden a medias, incluso si los sistemas se caen y se reinician.

---

## 4. Motor LLM y Orquestación

### 🤖 cerebro-litellm — Jefe de Traductores

*Analogía:* Imagina un jefe de traductores en la sede de las Naciones Unidas. Tú solo le entregas un documento y le dices "Tradúcelo". No te importa si usa al traductor de OpenAI, al de Anthropic o a su propio equipo local. Si el traductor principal está enfermo (caída del sistema), el jefe le pasa el documento al suplente automáticamente sin detener tu trabajo. Y si alguien le pide traducir exactamente el mismo documento que ayer, simplemente saca una copia del archivo (caché) para no hacer el trabajo dos veces.

**Configuración:** `infra/litellm/config.yaml`

**¿Qué hace?**

Es un intermediario inteligente (Proxy) entre nuestro sistema y las diferentes Inteligencias Artificiales del mercado.

- **Traductor Universal:** Permite a nuestras aplicaciones hablar con cualquier IA (OpenAI, Gemini, NVIDIA, modelos locales) usando siempre el mismo "idioma" de conexión.
- **Plan B Automático (Fallback):** Si nuestro proveedor de IA favorito falla, instantáneamente intenta con el segundo de la lista.
- **Interruptor de Seguridad (Circuit Breaker):** Si un proveedor se cae por completo, deja de enviarle preguntas temporalmente para no saturar el sistema.
- **Memoria de Ahorro (Caché):** Recuerda las preguntas frecuentes para responder al instante y ahorrar costos (caché en Redis).

**¿Por qué se tomó esta decisión?**

Nos da libertad absoluta. Si el día de mañana queremos cambiar la IA que usamos, solo tenemos que cambiar un par de líneas en un archivo de texto, sin tener que reprogramar nada del código principal del sistema.

**Nota de Seguridad:** LiteLLM (vía Prisma) limpia la zona `public` de la base de datos cada vez que se enciende. Por eso todas nuestras tablas se construyeron en un schema separado y exclusivo llamado `cerebro` — ver el detalle en [`4_arquitectura.md`](./4_arquitectura.md), sección de Aislamiento de Schema.

### 🔄 cerebro-n8n — Orquestador Visual

*Analogía:* Imagina a un ingeniero jefe frente a una pizarra gigante conectando cables de colores entre distintas máquinas. Cuando suena una alarma (por ejemplo, llega un mensaje de Telegram), la corriente viaja por los cables y activa una serie de interruptores que desencadenan acciones en cadena de forma completamente visual.

**¿Qué hace?**

Es una plataforma visual para crear "recetas" automatizadas (workflows).

- Se encarga de tareas de coordinación repetitivas como escuchar webhooks, conectar la plataforma con bots externos, o programar limpiezas nocturnas de datos (ver el flujo de Curación Nocturna en [`4_arquitectura.md`](./4_arquitectura.md)).
- Guarda todos sus esquemas en una zona privada separada de la base de datos (schema `n8n`).

### 🔧 cerebro-n8n-bootstrap — Cerrajero One-Shot

*Analogía:* Imagina un cerrajero que contrataste para preparar una oficina nueva. Llega temprano en la mañana, instala la cerradura central, deja las copias de las llaves en un cajón seguro y se marcha para siempre.

**¿Qué hace?**

Es un programa "desechable" que se ejecuta una única vez la primera vez que enciendes el sistema.

- Espera educadamente a que `cerebro-n8n` esté en su puesto.
- Genera las llaves de seguridad maestras (API key) y las guarda automáticamente en los archivos de configuración del sistema.

**¿Por qué se tomó esta decisión?**

Automatización total. Permite que cualquier persona pueda instalar y encender el sistema completo con un solo comando (`docker compose up -d`), de principio a fin, sin tener que abrir manuales para configurar contraseñas a mano.

---

## 5. Almacenamiento y Mensajería

### 🗄️ cerebro-postgres — Archivo Acorazado

*Analogía:* Es el archivo central y acorazado de un gran banco. Tiene diferentes bóvedas (schemas) asignadas a distintos departamentos. Como el departamento de IA (LiteLLM/Prisma) tiene la mala costumbre de limpiar su bóveda por completo todos los días, hemos construido una bóveda secreta y acorazada (`cerebro`) solo para nuestros documentos críticos, donde la IA no tiene llave.

**¿Qué hace?**

Es la base de datos principal y permanente del sistema.

- **Registros Universales:** Guarda la información de cada enlace web (recurso) una sola vez para no repetir datos.
- **Privacidad Estricta:** Usa Row-Level Security para asegurar que un usuario solo pueda ver sus propios enlaces guardados (vía `usuario_recursos`), aunque el sistema recicle y comparta los textos "tras bambalinas".
- **Historial y Memoria:** Almacena perfil de usuario, contraseñas y todas las conversaciones con la IA.
- **Gestor de Envíos:** Funciona como un registro transaccional para el Patrón Outbox.

**¿Por qué se tomó esta decisión?**

Además de separar las "bóvedas" para proteger los datos (schema `cerebro` invisible a LiteLLM, ver Aislamiento de Schema en [`4_arquitectura.md`](./4_arquitectura.md)), esta base de datos está afinada como un motor de Fórmula 1: tiene reglas precisas sobre cuántos workers pueden escribir a la vez y cuánta memoria utilizar para búsquedas, previniendo colapsos en momentos de pánico.

### ⚡ cerebro-redis — Libreta Rápida

*Analogía:* Es la libreta de apuntes rápidos del sistema o la memoria a corto plazo. No se usa para guardar archivos históricos vitales, sino para cálculos ultrarrápidos que deben ocurrir en una fracción de segundo para coordinarlo todo.

**¿Qué hace?**

Es una base de datos temporal extremadamente veloz. Cumple cuatro misiones:

1. **Detector Rápido (Bloom Filter):** Responde en un milisegundo si un enlace ya existe antes de aceptarlo.
2. **Guardia de Seguridad (Rate Limiter):** Cuenta cuántas peticiones estás haciendo por segundo y levanta un escudo si intentas abusar del sistema (`INCR+EXPIRE` atómico).
3. **Monitor de Vida (Heartbeat):** Los workers dejan aquí su firma cada 45 segundos para avisarle al sistema que siguen vivos (ver Heartbeat en [`4_arquitectura.md`](./4_arquitectura.md)).
4. **Caché de IA:** Acumula prompts previos para no gastar dólares repitiendo el trabajo de la IA (caché LiteLLM).

**¿Por qué se tomó esta decisión?**

Para garantizar estabilidad. Obligamos al sistema a no utilizar versiones "más recientes" de Redis con sorpresas, sino una versión probada para que cosas vitales como el Bloom Filter no se rompan por actualizaciones silenciosas.

### 📨 cerebro-rabbitmq — Bandas Transportadoras

*Analogía:* Son las bandas transportadoras de una fábrica automatizada. Si hay mucho trabajo, los paquetes (enlaces o textos) se acumulan ordenadamente en la banda, esperando su turno para ser procesados sin que ninguno se caiga al suelo.

**¿Qué hace?**

Es el sistema central de mensajería (colas de trabajo) en tiempo real.

- **Rutas de Trabajo:** Mueve los enlaces recién llegados hacia el scraper (`q.url.ingesta`) y los textos limpios hacia el embedder (`q.embeddings`).
- **Basurero de Emergencia (DLQ):** Si no se puede generar el cálculo matemático repetidas veces, no permite que un documento importante desaparezca; lo deposita en una Dead Letter Queue para ser arreglado manualmente después.

**¿Por qué se tomó esta decisión?**

Antes, los mensajes que fallaban no tenían un "hospital" hacia dónde ir, por lo cual simplemente se evaporaban, perdiendo parte del trabajo. Ahora, tenemos tuberías seguras para todos los casos de falla para que ningún proceso se corrompa sin dar aviso.

### 🧠 cerebro-qdrant — Mapa de Estrellas Semántico

*Analogía:* Es una supercomputadora programada con un mapa de estrellas gigante. En lugar de buscar archivos por orden alfabético, tú le das un poema y ella te dice "Ah, esa idea vive en este sector estelar de aquí, cerca de estas otras cinco ideas similares".

**¿Qué hace?**

Es un motor de búsqueda vectorial.

- **Búsqueda por Intuición:** Almacena todos los resúmenes en vectores de alta dimensionalidad. Cuando hablas con la IA, esta base de datos busca en el mapa estelar ideas similares en fracciones de segundo (HNSW).
- **Ahorro Compartido (Multi-tenant):** Si dos usuarios distintos guardan el enlace a la página oficial de la NASA, la IA no hace cálculos matemáticos dos veces; simplemente le crea un clon en el mapa estelar al segundo usuario y lo ata a un identificador único global (`point_id = uuid5(ns, "<recurso_id>:<tenant_id>")`).

**¿Por qué se tomó esta decisión?**

Aunque Postgres puede guardar vectores (con `pgvector`), Qdrant fue diseñado *únicamente* para buscar similitudes semánticas. Es cien veces más rápido (gracias a los índices HNSW) y permite filtrar por tu ID de tenant sin necesidad de JOINs adicionales.

---

## 6. Observabilidad

### 📡 cerebro-otel — Radar Universal

*Analogía:* Es el radar central de una torre de control de tráfico aéreo. Escucha las señales de radio de todos los aviones (aplicaciones) y las pasa en un formato limpio y unificado a las pantallas de los controladores (Jaeger).

**¿Qué hace?**

Es un recolector universal. Recibe las trazas que las aplicaciones dejan al funcionar y las enruta al sistema de visualización correspondiente.

**¿Por qué se tomó esta decisión?**

Nos da flexibilidad a futuro. Si mañana decidimos cambiar la pantalla donde analizamos los errores (por ejemplo, dejar de usar Jaeger), solo le avisamos al radar, sin tener que reprogramar las aplicaciones.

### 📊 cerebro-prometheus — Supervisor de Fábrica

*Analogía:* Es el supervisor de la fábrica que pasa cada 15 segundos preguntándole a cada máquina "¿A qué temperatura estás?", "¿Cuántos productos llevas?". Si una máquina pasa de los grados permitidos, hace sonar la alarma.

**¿Qué hace?**

Recopila métricas de salud de todo el sistema de manera periódica. Cuenta con reglas automáticas (alertas) configuradas — ver el detalle en la sección de Observabilidad de [`4_arquitectura.md`](./4_arquitectura.md).

### 🔭 cerebro-jaeger — Detective de Tiempos

*Analogía:* Es el detective experto que puede reconstruir el rastro de la escena del crimen, segundo a segundo.

**¿Qué hace?**

Muestra el mapa visual de cuánto tardó cada elemento. Si un usuario se queja de que "la aplicación está lenta", Jaeger permite ver en cascada que Traefik tardó 1 milisegundo, pero la conexión con LiteLLM tardó 3 segundos.

### 📈 cerebro-grafana — Pantalla de Control

*Analogía:* Es la pantalla gigante con gráficas vistosas y velocímetros en el centro de mando.

**¿Qué hace?**

Reúne toda la información dura del supervisor estadístico (Prometheus) y el detective de tiempos (Jaeger) mostrándolos en un mismo panel fácil de leer.

### 📦 Exporters (postgres, redis, rabbitmq)

*Analogía:* Son traductores simultáneos con un pequeño auricular. Puesto que las bases de datos antiguas (RabbitMQ, Redis, PostgreSQL) hablan sus propios idiomas cerrados y el supervisor estadístico (Prometheus) solo habla un idioma internacional (Prometheus Metrics), estos traductores escuchan a la base de datos y le traducen al supervisor qué tal van en tiempo real.

**¿Qué hace?**

Son tres pequeñas aplicaciones ultraligeras:

1. **`cerebro-postgres-exporter`:** Traduce cómo está la salud de la bóveda de datos (conexiones, locks, tamaño).
2. **`cerebro-redis-exporter`:** Traduce cuánta memoria temporal le queda a la libreta rápida (uso, hit rate, clientes).
3. **`cerebro-rabbitmq-exporter`:** Traduce cómo van las bandas transportadoras y si hay atascos. Se usa con una versión congelada para evitar que actualicen su diccionario sin avisarnos y rompan el sistema.

---

> Continúa con los flujos de trabajo y decisiones arquitectónicas en [`4_arquitectura.md`](./4_arquitectura.md).
