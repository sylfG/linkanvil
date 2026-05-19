## Glosario Rápido


* **API Gateway:** Una puerta de acceso digital que controla, filtra y organiza el tráfico de datos que entra a un sistema informático.
* **audit_policy:** Política de auditoría JSONB almacenada por usuario en la columna `usuarios.audit_policy`. Tiene **6 claves** resultado de la matriz `temporal_class × valor_archivistico`: `evento_pasado_alto`, `evento_pasado_medio`, `evento_pasado_nulo`, `referencia_pasada_alto`, `referencia_pasada_medio`, `referencia_pasada_nulo`. Cada clave decide qué hacer con el recurso (`expirado` o `cuarentena`). **Reemplazó** al antiguo campo `audit_strictness` en la migración `0007_audit_policy_y_auto_archive.sql`.
* **auto_archive_pending:** Flag booleano en la tabla `recursos` (migración 0007) que marca un recurso que la auditoría ha decidido archivar pero que aún no ha completado su transición a `expirado`. El `embedder_worker` lo lee para terminar la transición y el `audit_cron` lo limpia tras consumarse el cambio.
* **Base de Datos Vectorial:** Un tipo de almacén digital que organiza la información según el significado de las palabras, permitiendo encontrar temas parecidos aunque utilicen vocabulario diferente. En LinkAnvil este rol lo cumple **Qdrant** con dos colecciones (`cerebro_recursos` y `cerebro_chunks`) de 1536 dimensiones y distancia Cosine.
* **BYOK (Bring Your Own Key):** Modelo en el que cada usuario registrado aporta sus propias credenciales para LiteLLM en lugar de usar las del operador. En LinkAnvil cada cuenta registrada tiene **3 virtual-keys de LiteLLM** (migración `0008_byok_y_demo_flag.sql`); las sesiones del demo están exentas. Cuando un usuario registrado no tiene claves configuradas, la API devuelve `402 byok_required` con CTA al modal de configuración.
* **Circuit Breaker (Disyuntor):** Un mecanismo de seguridad que corta temporalmente la conexión con un servicio externo si este empieza a fallar repetidamente, evitando que todo el sistema se bloquee.
* **DLQ (Dead-Letter Queue):** Cola de RabbitMQ a la que se enrutan los mensajes que han fallado el procesamiento normal tras los reintentos definidos. En LinkAnvil el `embedder_worker` declara la routing key `dlq.url.fallidas` (`src/data/embedder_worker.py:83`) vía el header `x-dead-letter-routing-key`.
* **Embedding (Incrustación):** El proceso de traducir un texto o una idea en una serie de números para que una computadora pueda medir qué tan similar es a otra idea. En LinkAnvil se generan vía **LiteLLM** (modelo `cerebro-embeddings`, dimensión **1536**) y se upsertan en Qdrant de forma idempotente (mismo par genera siempre el mismo id).
* **evento_pasado / referencia_pasada:** Tipos de evento que el `audit_cron` emite y el `notifier_worker` consume. Aparecen también como dos de las tres claves del prefijo de `audit_policy`. En la UI se traducen al usuario final como "fecha pasada" / "tiene fecha pasada y requiere revisión".
* **JSONB:** Tipo de columna binaria de PostgreSQL para almacenar JSON. En LinkAnvil se usa en `usuarios.audit_policy` (las 6 claves de la matriz) y en `outbox_eventos.payload` (carga de cada evento del patrón Outbox).
* **JWT (JSON Web Token):** Token firmado con clave simétrica que LinkAnvil usa como **access token de sesión** (cookie `cerebro_session`, vida corta). Implementado vía `python-jose` (`src/api/auth.py`). **No confundir con el Refresh Token**, que es un *string opaque random* (no JWT) almacenado hasheado en la cookie `cerebro_refresh`.
* **Patrón Outbox:** Patrón transaccional que garantiza que un evento se persiste en la base de datos en la misma transacción que el cambio de estado, y un consumer posterior lo publica al broker. En LinkAnvil concreta la cadena **`outbox_eventos` (tabla PG) → RabbitMQ → notifier → Redis → SSE**, con `outbox_eventos.payload` en JSONB. Productores: `audit_cron`, `embedder_worker`. Lector: `export_manager` / publisher hacia RabbitMQ.
* **RAG (Generación Aumentada por Recuperación):** Técnica que permite a una IA responder preguntas basándose exclusivamente en los documentos y enlaces aportados por el usuario, evitando que invente información. En LinkAnvil el RAG tiene dos modos de recuperación según el toggle del chat:
  - **Archivo OFF (por defecto):** solo recupera de la KB activa (recursos en estado `activo`).
  - **Archivo ON:** además recupera del archivo histórico — recursos `expirado` con `valor_archivistico` alto que siguen indexados en Qdrant aunque aparezcan en `/expired`.
  Además existe una pipeline de **staged embeddings** para el demo (`ops/build_staged_embeddings.py`, migración 0011) y el embedder reutiliza vectores ya existentes en otros tenants para colisión global (no re-embebe el mismo recurso). El streaming de la respuesta usa **SSE** (ver entrada propia).
* **Rate Limiting (Límite de Tasa):** Una restricción de seguridad que define cuántas acciones o peticiones puede hacer un usuario o una dirección IP por minuto para evitar sobrecargas.
* **Streaming SSE (Server-Sent Events):** Tecnología que permite al servidor enviar datos a la pantalla del usuario de forma continua y progresiva (palabra por palabra), sin necesidad de esperar a que toda la respuesta esté terminada. En LinkAnvil se usa para dos cosas: (1) el streaming token-a-token de la **respuesta del chat RAG**, y (2) el fan-out de notificaciones del notifier al canal Redis pub/sub **`resources:{tenant_id}`**, al que se suscribe la UI vía cookies same-origin (`src/frontend/lib/sse.ts`, `lib/api.ts:sseUrl`).
* **Sub-tenant demo:** Espacio de aislamiento **efímero** creado por cada sesión del demo público. A diferencia del Tenant persistente, no tiene fila en `usuarios`; se identifica con el formato **`demo_<8hex>`** y tiene un **TTL de 15 minutos** (tabla `demo_sessions`, migración 0009). Las queries de datos hacen `UNION` con el tenant persistente del demo. Las claves LLM se keyean por `user_id` (no por `tenant_id`) precisamente porque los sub-tenants comparten usuario del demo.
* **temporal_class:** Columna VARCHAR(20) de la tabla `recursos` (migración 0006) que clasifica el recurso por su naturaleza temporal. CHECK constraint con **tres valores**: `evento` (algo con fecha — caduca tras la fecha), `referencia` (algo útil un tiempo limitado), `evergreen` (no caduca). Junto con `valor_archivistico` forma la matriz que decide qué hacer al expirar.
* **Tenant (Inquilino / Cuenta):** Espacio de usuario aislado dentro del sistema multi-tenant. En LinkAnvil existen **dos clases**:
  - **Tenant persistente:** fila en la tabla `usuarios`, `tenant_id` estable; corresponde a una cuenta registrada normal.
  - **Sub-tenant demo:** sesión efímera del demo público, sin fila en `usuarios`, identificada por `demo_<8hex>` con TTL 15 min (ver entrada propia "Sub-tenant demo"). Afecta a auth, audit_cron, LLM keys y cleanup.
* **valor_archivistico:** Columna VARCHAR(20) de la tabla `recursos` (migración 0006) que indica si el contenido merece conservarse como referencia histórica una vez expirado. CHECK constraint con **tres valores**: `alto`, `medio`, `nulo`. Junto con `temporal_class` forma la matriz que parametriza `audit_policy`.

*   **Contenedor / Docker:** Una caja virtual donde se ejecuta un programa de manera aislada, empaquetado con todo lo que necesita para funcionar.
*   **HTTPS:** Un canal que cifra la conexión de internet, garantizando que nadie más pueda espiar la comunicación.
*   **NAT (Traducción de Direcciones de Red):** El mecanismo de tu router (el aparato que te da internet) que oculta y protege tus dispositivos, evitando que reciban conexiones desde el exterior.
*   **Proxy:** Un programa que actúa como intermediario. Recibe una solicitud de internet y decide a qué parte interna de tu sistema debe enviarla para que se resuelva.
*   **Puerto (de red):** Un número que actúa como una "puerta" específica en tu computadora para un tipo de comunicación de red determinado.
*   **Webhook:** Un aviso automático por internet. Es la forma en la que una aplicación (como Telegram) notifica a otra al instante de que ha sucedido un evento nuevo.
*   **Clúster:** Un grupo de programas o computadoras que trabajan juntos como un solo sistema organizado.
*   **Host Header:** Una sección invisible en tu petición web que indica exactamente qué nombre de dominio estás buscando (ej. midominio.com).
*   **Trace-ID:** Una "matrícula" de rastreo. Es un código muy largo (ej. `af46...9b12`) que se le pega a un evento para seguir sus huellas aunque cruce por cinco programas distintos.
*   **Backend:** La "sala de máquinas" de una aplicación. La parte del sistema que el usuario no ve, donde se procesan los datos y se aplican las reglas de negocio.
*   **Bloom Filter:** Un mecanismo matemático extremadamente rápido que permite saber si algo (como un enlace) ya está registrado sin necesidad de buscar en toda la base de datos. En LinkAnvil se implementa con **RedisBloom**, una key per-tenant, y se usa en `src/ingestion/deduplicator.py` para deduplicar URLs en la ingesta.
*   **CSRF (Falsificación de Petición en Sitios Cruzados):** Un tipo de ataque donde un delincuente intenta engañar a tu navegador para que haga acciones no deseadas en tu cuenta.
*   **Operación Atómica:** Una tarea informática que ocurre en un instante indivisible (todo o nada). Evita que otros procesos interrumpan y rompan la operación a la mitad ("race condition" o condición de carrera).
*   **Scraping:** El proceso automático de descargar una página web y "raspar" o extraer la información útil de su interior.
*   **XSS (Secuencias de Comandos en Sitios Cruzados):** Una vulnerabilidad en la que un atacante inyecta código malicioso en una página web legítima para robar información de otros usuarios.
*   **Frontend:** La parte visible de un programa; todo lo que el usuario ve, toca y con lo que interactúa en la pantalla.
*   **Local Storage (Almacenamiento Local):** Una pequeña memoria pública que tiene todo navegador web (Chrome, Firefox, etc.) para guardar configuraciones menores. No es un lugar seguro para información confidencial.
*   **Next.js y React:** Herramientas de programación muy populares utilizadas para construir páginas web que se sienten rápidas y responden como si fueran aplicaciones de teléfono móvil.
*   **Asíncrono:** Una forma de trabajar en la que no tienes que quedarte paralizado esperando a que termine una tarea larga para poder empezar otra. Cada trabajador sigue su propio ritmo.
*   **Cola de Mensajes (RabbitMQ):** Un sistema que organiza las tareas pendientes en fila india para que los trabajadores las vayan tomando ordenadamente sin saturarse. En LinkAnvil el exchange central es **`cerebro.procesamiento`** de tipo **fanout** (cada consumer — embedder, notifier — tiene su propia queue ligada), más la DLQ `dlq.url.fallidas` para mensajes fallidos.
*   **Navegador Invisible (Headless Browser):** Un navegador de internet (como Chrome o Edge) que funciona en el fondo sin mostrar ninguna ventana en la pantalla, usado para que los programas interactúen con las webs como si fueran humanos.
*   **SPA (Aplicación de Página Única) / JS-heavy:** Sitios web modernos interactivos que requieren cargar mucho código de fondo para poder mostrar su texto (como una red social o una plataforma de video en línea). No se pueden leer simplemente abriendo el código fuente, requieren un navegador invisible.
*   **Observabilidad (Monitoreo):** Capacidad del sistema de informarnos detalladamente de su salud sin necesidad de mirarlo apagándolo por dentro.
*   **Trazas (Traces):** La huella digital del camino completo que sigue un usuario, medida cronológicamente desde que empuja un botón web hasta el interior de la base de datos.
*   **Métricas:** Estadísticas crudas temporales de "salud" (ej: uso de disco, cuántos megabytes).
*   **Exporter:** Conector que permite cruzar informes de un sistema cerrado (viejo) a un sistema abierto y fácil de supervisar analíticamente.

---

## 📋 Notas del v2 (generado por doc-reviser · 2026-05-19)

**Origen**: `/tmp/linkanvil-mirror/docs/src/11-Glosario.md` (mirror local; sin metadata git en el mirror)
**Review aplicado**: `/tmp/linkanvil-staging/docs/review/2026-05-19/docs/11-Glosario.review.md`

### Cambios aplicados

- **2 CRITICAL · 9 HIGH · 6 MEDIUM · 4 LOW** aplicados (de 22 hallazgos totales).
- **CRIT-1**: redefinida `Tenant` para reflejar el modelo de 2 niveles (persistente + sub-tenant demo) y añadida entrada propia **"Sub-tenant demo"** con TTL 15 min y formato `demo_<8hex>`.
- **CRIT-2**: redefinida `RAG` para incluir la dualidad activo/archivo histórico con el toggle **"Archivo ON"**, los staged embeddings del demo y la colisión global de recursos.
- **HIGH-1 a HIGH-9**: añadidas 9 entradas nuevas — **BYOK**, **audit_policy**, **temporal_class**, **valor_archivistico**, **evento_pasado / referencia_pasada**, **auto_archive_pending**, **DLQ**, **JSONB**, **JWT** (con distinción explícita del Refresh Token opaque).
- **MED-1**: nota histórica sobre **`audit_strictness`** integrada en la entrada `audit_policy` ("reemplazó al antiguo audit_strictness en la migración 0007").
- **MED-2**: `Outbox` enriquecido con la cadena específica `outbox_eventos → RabbitMQ → notifier → Redis → SSE`, productores y consumidores.
- **MED-3**: `Streaming SSE` ahora menciona el canal Redis `resources:{tenant_id}` y los dos usos reales (chat RAG y fan-out de notificaciones).
- **MED-4**: `Bloom Filter` ampliado con contexto LinkAnvil (RedisBloom, key per-tenant, ingesta).
- **MED-5**: `Cola de Mensajes (RabbitMQ)` ampliado con el **fanout exchange `cerebro.procesamiento`** y la DLQ.
- **MED-6**: `Embedding` ahora menciona modelo (`cerebro-embeddings` vía LiteLLM), dimensión (1536) e idempotencia. Qdrant también referenciado en "Base de Datos Vectorial" con colecciones reales.
- **LOW-1**: corregido `nuevosiem`/duplicación en la entrada **Webhook**.
- **LOW-2**: eliminado `web web` duplicado en **Host Header**.
- **LOW-3**: viñetas — se mantienen los dos estilos del original (la mezcla no era un hallazgo bloqueante y unificar arriesgaba a "embellecer" más allá del alcance). *Aplicación parcial.*
- **LOW-4**: **Streaming SSE** ahora expande el acrónimo "Server-Sent Events".

Secciones tocadas: práctica totalidad del primer bloque (líneas 4-12 del original) por las reescrituras de Tenant/RAG/Outbox/SSE/Embedding y las 12 entradas nuevas insertadas en orden alfabético dentro del bloque; del segundo bloque solo se tocaron las entradas afectadas por LOW-1, LOW-2 y el enriquecimiento de Bloom Filter y RabbitMQ.

### Pendientes (no aplicados en este v2)

- **LOW-3 (unificación de viñetas):** aplicado parcialmente. El original tiene dos estilos (`* ` y `*   `) y unificarlos por completo entraba en zona cosmética no estrictamente pedida por el review. **TODO opcional**: si el equipo prefiere un estilo único, basta con un find-replace global de `*   ` → `* `.
- **LOW-5 (entrada explícita "Similitud coseno"):** el review lo clasificó como "MEDIUM si se quiere ser estricto, LOW si se considera implícito". No se añadió entrada propia porque "Embedding" ya menciona distancia Cosine y la dimensión 1536, cubriendo el concepto sin duplicar. **TODO opcional** si se desea entrada dedicada.
- **Términos del gap inventory del review NO añadidos en este v2** (para no inflar el glosario más allá de los HIGH/MEDIUM marcados): `Qdrant` (se menciona dentro de "Base de Datos Vectorial" y "RAG"), `LiteLLM` (se menciona dentro de "BYOK" y "Embedding"), `Redis pub/sub` (cubierto dentro de "Streaming SSE"), `outbox_eventos` (cubierto dentro de "Patrón Outbox"), `fanout exchange` (cubierto dentro de "Cola de Mensajes"), `staged_embeddings` (cubierto dentro de "RAG"), `OpenTelemetry / OTLP`, `routing_key`, `chunk / chunk_idx`, `recursos.estado` (activo/expirado/cuarentena), `Telegram webhook por usuario`. Si en una revisión posterior el equipo decide promocionarlos a entradas propias, son adiciones limpias.

### Bugs de código flaggeados (no son drift de doc, requieren acción aparte)

- *Ninguno.* El review no marcó `CODE-BUG`. Sí dejó constancia (MED-1) de un **comentario stale** en `src/data/audit_cron.py:134` que aún dice "respetando el strictness del tenant" cuando `audit_strictness` ya no existe; eso es deuda menor en código, no drift de doc. Se sugiere abrir issue de housekeeping para limpiar ese comentario y el nombre del archivo de migración 0006 (que mantiene `strictness` por compatibilidad histórica con su id de migración — cambiarlo rompería el historial; aceptable como está).
