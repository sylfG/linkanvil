# Review · 1-instalacion-configuracion · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `docs/src/1-instalacion-configuracion.md`
**Áreas de código verificadas**:
- `docker-compose.yml`, `docker-compose.prod.yml`
- `infra/` (postgres, tailscale, qdrant, prometheus, n8n, rabbitmq, litellm, grafana)
- `infra/postgres/migrations/` (0001 → 0011)
- `.env.example`
- `scripts/migrate.sh`, `scripts/backup.sh`, `reset.sh`
- `docs/PRODUCTION.md`
**Versión del repo**: `develop` @ `7c723f3`

## Resumen
- **2 CRITICAL**, **5 HIGH**, **7 MEDIUM**, **3 LOW**, **1 UNVERIFIED**
- **0 hallazgos [CODE-BUG]**
- **Veredicto**: **RED** (hay CRITICAL — comandos y env vars del doc que no funcionan tal cual están escritos)

---

## Hallazgos

### [CRITICAL] El curl `http://localhost:8000/ingest` no funciona: la `ingestion-api` no expone puertos al host

- **Ubicación**: línea ~289 (sección "Tu primera ingesta")
- **Lo que dice el doc**:
  > ```bash
  > curl -X POST http://localhost:8000/ingest \
  >   -H "Content-Type: application/json" \
  >   -d '{"url": "https://vitepress.dev/", "tenant_id": "mi-tenant"}'
  > ```
- **Realidad en el código**: El servicio `ingestion-api` (container `cerebro-ingestion`) **no declara `ports:`** en `docker-compose.yml` (`docker-compose.yml:14-49`). Solo es accesible por dos vías:
  1. Vía Traefik en `http://localhost/ingest` (PathPrefix) o `http://ingest.localhost`, según label `traefik.http.routers.ingestion.rule=Host(\`ingest.localhost\`) || PathPrefix(\`/ingest\`)` (`docker-compose.yml:39`).
  2. Dentro de `cerebro-net` como `http://ingestion-api:8000`.

  El comando `curl http://localhost:8000/ingest` desde el host **fallará con connection refused**.
- **Cambio sugerido**:
  ```markdown
  ```bash
  # Vía Traefik (recomendado — pasa por el rate-limiting global):
  curl -X POST http://localhost/ingest \
    -H "Host: ingest.localhost" \
    -H "Content-Type: application/json" \
    -d '{"url": "https://vitepress.dev/", "tenant_id": "mi-tenant"}'

  # O directamente al host header configurado:
  curl -X POST http://ingest.localhost/ingest \
    -H "Content-Type: application/json" \
    -d '{"url": "https://vitepress.dev/", "tenant_id": "mi-tenant"}'
  ```
  ```

---

### [CRITICAL] Variables de entorno de producción inventadas: `SESSION_COOKIE_SECURE` y `DOMAIN` no existen en el código

- **Ubicación**: línea ~331 (FASE 6.3 "Variables críticas para producción")
- **Lo que dice el doc**:
  > ```env
  > SESSION_COOKIE_SECURE=true
  > JWT_SECRET=<clave-aleatoria-fuerte>
  > DOMAIN=tu-dominio.com
  > ACME_EMAIL=admin@tu-dominio.com
  > ```
- **Realidad en el código**:
  - `SESSION_COOKIE_SECURE`: **no aparece** en `docker-compose.yml`, `docker-compose.prod.yml`, ni en `.env.example` (`grep -r SESSION_COOKIE_SECURE` devuelve 0 resultados).
  - `DOMAIN`: tampoco existe. La variable real usada en producción es **`PUBLIC_HOSTNAME`** (`docs/PRODUCTION.md:30`).
  - `JWT_SECRET` (`.env.example:37`) y `ACME_EMAIL` (`docker-compose.prod.yml:45`) sí existen.
- **Cambio sugerido**:
  ```markdown
  ```env
  # En .env de producción (los secretos van en Docker secrets, no aquí)
  JWT_SECRET=<clave-aleatoria-fuerte>   # mín 32 chars; genera con: python3 -c "import secrets; print(secrets.token_hex(32))"
  PUBLIC_HOSTNAME=tu-dominio.com        # Traefik construye rutas desde aquí
  ACME_EMAIL=admin@tu-dominio.com       # Let's Encrypt notifications
  ```
  ```

---

### [HIGH] Link a "Arquitectura" apunta a un archivo inexistente

- **Ubicación**: última línea del doc
- **Lo que dice el doc**:
  > "Consulta la [Arquitectura](./6_arquitectura.md) para entender las decisiones de diseño, o las [Épicas y Features](./1_epics_and_features.md) para el roadmap del producto."
- **Realidad en el código**: el archivo se llama `4-arquitectura.md` (`docs/src/4-arquitectura.md`), no `6_arquitectura.md`. Y `1_epics_and_features.md` **no existe** en `docs/src/` (`ls docs/src/` no lo lista).
- **Cambio sugerido**:
  ```markdown
  Consulta la [Arquitectura](./4-arquitectura.md) para entender las decisiones de diseño.
  ```
  *(eliminar el link a `1_epics_and_features.md` o reemplazarlo por el archivo real correspondiente; no hay sustituto evidente en `docs/src/`).*

---

### [HIGH] La URL de clonación tiene case incorrecto

- **Ubicación**: línea ~159 (sección 1.3)
- **Lo que dice el doc**:
  > ```bash
  > git clone https://github.com/sylfg/linkanvil.git
  > ```
- **Realidad en el código**: el remote real es `https://github.com/sylfG/linkanvil` (G mayúscula) — `git remote -v` desde `/root/linkanvil`. GitHub resuelve case-insensitive, así que técnicamente funciona, pero el doc debe reflejar el casing canónico.
- **Cambio sugerido**:
  ```markdown
  ```bash
  git clone https://github.com/sylfG/linkanvil.git
  cd linkanvil
  ```
  ```

---

### [HIGH] El doc omite `LLM_KEYS_ENCRYPTION_KEY`, que es **obligatoria** y rompe el arranque si está vacía

- **Ubicación**: FASE 2 (línea ~178+)
- **Lo que dice el doc**: La FASE 2 lista `OPENROUTER_API_KEY`, `LITELLM_MASTER_KEY`, `POSTGRES_PASSWORD`, `RABBITMQ_PASS` como "críticas". No menciona `LLM_KEYS_ENCRYPTION_KEY`.
- **Realidad en el código**: en `docker-compose.yml:235`:
  ```
  LLM_KEYS_ENCRYPTION_KEY: ${LLM_KEYS_ENCRYPTION_KEY:?LLM_KEYS_ENCRYPTION_KEY must be set in .env}
  ```
  El operador `:?` hace que `docker compose up` **falle inmediatamente** si esa variable está vacía o ausente. En `.env.example:69` está vacía por defecto. Un usuario que siga el tutorial sin tocar esa línea verá el stack fallar al arrancar.
- **Cambio sugerido**:
  ```markdown
  * **Clave de cifrado de las BYOK keys (*CRÍTICA*)**: requerida para que `cerebro-api` arranque. Genera y pega:
    ```bash
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```
    ```env
    LLM_KEYS_ENCRYPTION_KEY=<el-valor-generado-arriba>
    ```
  ```

---

### [HIGH] El paso "FASE 3b: Aplicar migraciones" es redundante — Compose ya las aplica automáticamente

- **Ubicación**: FASE 3b (línea ~205+)
- **Lo que dice el doc**:
  > "Bash scripts/migrate.sh — Primera ejecución: aplica 0001_baseline.sql … Si el stack acaba de arrancar con `docker compose up -d`, el `init.sql` ya habrá creado las tablas — la migración baseline verifica su existencia y registra la versión."
- **Realidad en el código**: existe un servicio dedicado **`cerebro-migrate`** (`docker-compose.yml:194-213`) que ejecuta `bash /migrate.sh` y del cual `cerebro-api` depende con `condition: service_completed_successfully` (`docker-compose.yml:252-253`). Es decir, **las migraciones se aplican siempre, automáticamente, antes de que la API arranque**. Ejecutar `bash scripts/migrate.sh` desde el host es opcional y, en el caso típico, redundante.

  Además, `bash scripts/migrate.sh` desde el host requiere `psql` instalado localmente y `PGHOST=localhost` (puerto 5432 expuesto) — un prerrequisito que el doc no menciona en la sección 1.1.
- **Cambio sugerido**:
  ```markdown
  ## FASE 3b: Migraciones de Schema (automáticas)

  Las migraciones SQL se aplican **automáticamente** por el servicio `cerebro-migrate`
  cada vez que ejecutas `docker compose up -d`. La API no arranca hasta que el runner
  termina con éxito (`depends_on: service_completed_successfully`).

  Solo necesitas ejecutarlas manualmente si:
  1. Has añadido una migración nueva en `infra/postgres/migrations/` sin reiniciar el stack.
  2. Estás depurando el runner.

  ```bash
  # Manual (requiere psql instalado en el host y puerto 5432 expuesto):
  bash scripts/migrate.sh

  # O dentro del contenedor (más seguro):
  docker compose run --rm cerebro-migrate
  ```
  ```

---

### [HIGH] `BACKUP_RETENTION_DAYS` se menciona como variable de `.env` pero no está en `.env.example`

- **Ubicación**: FASE 6.5 (última línea de la sección)
- **Lo que dice el doc**:
  > "Configura `BACKUP_RETENTION_DAYS` en `.env` para la retención automática."
- **Realidad en el código**: `BACKUP_RETENTION_DAYS` se lee solo en `scripts/backup.sh` (`scripts/backup.sh:` `RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"`). **No aparece** en `.env.example`. Funciona si el usuario la añade, pero el doc da por hecho que está documentada.
- **Cambio sugerido**:
  ```markdown
  Configura `BACKUP_RETENTION_DAYS` (entero, default `7`) como variable de entorno
  o añádela a tu `.env` para personalizar la retención. Alternativa equivalente:
  `BACKUP_RETENTION_DAYS=14 bash scripts/backup.sh`.
  ```

---

### [MEDIUM] La cuenta de "21 servicios distribuidos" es ambigua

- **Ubicación**: línea ~57 (sección Docker) y línea ~189 (FASE 3)
- **Lo que dice el doc**:
  > "empaquetando cada uno de los 21 servicios distribuidos"
  > "levantará los 21 contenedores"
- **Realidad en el código**: `docker-compose.yml` declara **24 servicios** (`container_name:` aparece 24 veces, `docker-compose.yml:18-863`). De ellos:
  - 2 son one-shot (`cerebro-migrate`, `cerebro-n8n-bootstrap`, ambos `restart: "no"`).
  - 1 es opcional vía profile (`tailscale-funnel`, `profiles: ["telegram"]`, `docker-compose.yml:864`).
  - Quedan **21 servicios long-running por defecto** — el número del doc encaja, pero solo por casualidad.

  Es preciso aclarar el matiz para evitar confusión cuando el lector ejecute `docker compose ps` y vea más o menos contenedores según el perfil.
- **Cambio sugerido**:
  ```markdown
  empaquetando los **21 servicios long-running** del stack (más 2 one-shot
  de inicialización: `cerebro-migrate` y `cerebro-n8n-bootstrap`, y el sidecar
  opcional `tailscale-funnel` que solo arranca con `--profile telegram`).
  ```

---

### [MEDIUM] La tabla de FASE 5 no menciona el puerto del Ingestion API

- **Ubicación**: línea ~265 (tabla de URLs de la FASE 5)
- **Lo que dice el doc**: La tabla incluye App Principal (3001), API Backend (8001), n8n, RabbitMQ, Grafana, Jaeger, Qdrant, Traefik — pero **no menciona el endpoint de Ingestion** (que sí se usa en "Tu primera ingesta").
- **Realidad en el código**: `ingestion-api` solo expone `8000` dentro de la red. Desde el host, hay que ir por Traefik (`http://localhost/ingest` o `http://ingest.localhost`).
- **Cambio sugerido**: añadir fila a la tabla:
  ```markdown
  | **Ingestion API** | [http://ingest.localhost/health](http://ingest.localhost/health) (vía Traefik) | Libre |
  ```

---

### [MEDIUM] Falta el endpoint `LiteLLM (4000)` en la tabla de FASE 5

- **Ubicación**: línea ~265 (tabla FASE 5)
- **Lo que dice el doc**: la tabla no lista LiteLLM.
- **Realidad en el código**: `litellm` publica `4000:4000` (`docker-compose.yml:521-522`) y `reset.sh:175` lo lista como endpoint canónico (`LiteLLM → http://localhost:4000`).
- **Cambio sugerido**:
  ```markdown
  | **LiteLLM Gateway** | [http://localhost:4000](http://localhost:4000) | `LITELLM_MASTER_KEY` |
  ```

---

### [MEDIUM] Variables del bloque "Contraseñas del resto del Stack" usan nombres no canónicos

- **Ubicación**: línea ~187 (FASE 2)
- **Lo que dice el doc**:
  > ```env
  > POSTGRES_PASSWORD=cerebro_db_pass
  > RABBITMQ_PASS=cerebro_pass
  > ```
- **Realidad en el código**: los valores **default** en `.env.example` son:
  - `POSTGRES_PASSWORD=cerebro_db_pass_CHANGE_ME` (`.env.example:10`)
  - `RABBITMQ_PASS=cerebro_pass_CHANGE_ME` (`.env.example:18`)

  El sufijo `_CHANGE_ME` es intencional para forzar al usuario a editarlo. El doc lo omite, lo que lleva al usuario a creer que los defaults son "production-safe".
- **Cambio sugerido**:
  ```markdown
  ```env
  POSTGRES_PASSWORD=cerebro_db_pass_CHANGE_ME   # ⚠ debes cambiarlo
  RABBITMQ_PASS=cerebro_pass_CHANGE_ME          # ⚠ debes cambiarlo
  REDIS_PASSWORD=cerebro_redis_pass_CHANGE_ME
  GRAFANA_PASSWORD=cerebro_grafana_pass_CHANGE_ME
  N8N_PASSWORD=cerebro_n8n_pass_CHANGE_ME
  ```
  ```

---

### [MEDIUM] Variables BYOK (`DEMO_KEY_*`) están en `.env.example` pero no se documentan

- **Ubicación**: FASE 2
- **Lo que dice el doc**: no menciona `DEMO_KEY_LITE`, `DEMO_KEY_EMBEDDINGS`, `DEMO_KEY_PRO`.
- **Realidad en el código**: están en `.env.example:76-78` y son leídas por `cerebro-api` (`docker-compose.yml:239-241`). Si están vacías hacen fallback al `LITELLM_MASTER_KEY`. Documentarlas evita confusión al ver `.env.example`.
- **Cambio sugerido**: añadir nota breve en FASE 2:
  ```markdown
  > Las variables `DEMO_KEY_LITE`, `DEMO_KEY_EMBEDDINGS`, `DEMO_KEY_PRO`
  > son virtual-keys de LiteLLM que usa el usuario demo. Si las dejas
  > vacías, se hace fallback automático a `LITELLM_MASTER_KEY` y el
  > demo funcionará sin configuración adicional.
  ```

---

### [MEDIUM] Imágenes Docker con tag `latest` no pinneadas — el doc no lo advierte

- **Ubicación**: implícito en FASE 3 ("descargará las imágenes")
- **Lo que dice el doc**: no menciona estabilidad/reproducibilidad de las imágenes.
- **Realidad en el código**: la mayoría están pinneadas a versión exacta, pero **tres usan `latest`** con SHA-256 digest:
  - `redis/redis-stack-server:latest@sha256:798ab84d...` (`docker-compose.yml:389`)
  - `jaegertracing/all-in-one:latest@sha256:ab6f1a1f...` (`docker-compose.yml:639`)
  - `kbudde/rabbitmq-exporter:latest@sha256:12f27d6d...` (`docker-compose.yml:780`)
  - `tailscale/tailscale:stable` (`docker-compose.yml:862`) — sin digest

  Los digests las hacen reproducibles, pero un lector debería saberlo para evitar sorpresas al cambiar el `compose` file.
- **Cambio sugerido**: añadir nota informativa al final de FASE 3:
  ```markdown
  > **Nota sobre versiones**: todas las imágenes externas están pinneadas a versión
  > o digest SHA-256 en `docker-compose.yml`, salvo `tailscale/tailscale:stable`
  > (opcional, sidecar de Telegram).
  ```

---

### [MEDIUM] FASE 4 omite el smoke test ya existente en el repo

- **Ubicación**: FASE 4 ("Verificación del Ecosistema")
- **Lo que dice el doc**: solo recomienda `docker compose ps`.
- **Realidad en el código**: existe `infra/test_health.py` (mencionado más arriba en el propio doc, sección 1.1), un smoke test sin dependencias externas que verifica conectividad. La FASE 4 sería el sitio natural para usarlo, pero el doc no lo conecta.
- **Cambio sugerido**: añadir al final de FASE 4:
  ```markdown
  Para un smoke test más profundo (verifica conectividad inter-servicio, no solo
  el estado del contenedor):

  ```bash
  python3 infra/test_health.py
  ```
  ```

---

### [LOW] Typo "Postgre" en lugar de "Postgres"

- **Ubicación**: línea ~187 (FASE 2)
- **Lo que dice el doc**:
  > "Modifica a placer las contraseñas predefinidas en el fichero de las bases de datos (RabbitMQ, Postgre, Redis, Grafana...)."
- **Realidad en el código**: el producto se llama `Postgres` / `PostgreSQL`.
- **Cambio sugerido**:
  ```markdown
  Modifica a placer las contraseñas predefinidas (RabbitMQ, Postgres, Redis, Grafana...).
  ```

---

### [LOW] Sección "curl" enumera curl como prerequisito pero el bloque de macOS contiene `curl --version` y no `brew install curl`

- **Ubicación**: línea ~106 (sección curl)
- **Lo que dice el doc**: el code group de macOS dice `# Incluido por defecto en macOS` seguido de `curl --version`. No es un error, pero rompe la simetría con el resto de bloques. Además **no hay bloque para Windows** (existe `winget install` para los demás).
- **Realidad en el código**: N/A.
- **Cambio sugerido**:
  ```markdown
  ```powershell [Windows]
  # curl está incluido en Windows 10/11 por defecto (curl.exe)
  curl --version
  ```
  ```

---

### [LOW] Descripción técnicamente incorrecta de `uv` y Node

- **Ubicación**: sección 1.1 (Node.js, uv)
- **Lo que dice el doc**:
  > "uv es un gestor de paquetes de Python ultra-rápido que se usa para descargar e iniciar el motor de búsqueda conceptual (Qdrant) y los recolectores de texto web"
  > "[Node.js] se encarga de activar de forma distribuida los servidores de mensajería (como el bot de Telegram) y las conexiones con bases de datos relacionales (PostgreSQL y Redis)"
- **Realidad en el código**: ni `uv` "descarga Qdrant" (Qdrant es un contenedor Docker), ni Node abre conexiones a Postgres/Redis. `uv`/`uvx` se usan exclusivamente para los **MCP servers de Claude Code** (`.mcp.json` los invoca), no para el stack runtime. La afirmación es marketing-flavored pero técnicamente errada.
- **Cambio sugerido**:
  ```markdown
  **uv / uvx**: usados por Claude Code para lanzar MCP servers en Python
  (`.mcp.json`). No participan en el runtime del stack — todos los servicios
  corren en contenedores Docker.

  **Node.js + npx**: lo necesita Claude Code para los MCP servers escritos
  en JavaScript/TypeScript (n8n, Slack, GitHub, etc.). No es runtime del stack.
  ```

---

### [UNVERIFIED] El TIP de `*.localhost` requiere /etc/hosts según el doc, pero la mayoría de OS resuelven `*.localhost` automáticamente

- **Ubicación**: línea ~283 (TIP tras tabla FASE 5)
- **Lo que dice el doc**:
  > "Añade las entradas `*.localhost` en tu `/etc/hosts`"
- **Realidad**: en Linux con `systemd-resolved` y en macOS recientes, los subdominios `*.localhost` resuelven a 127.0.0.1 automáticamente (RFC 6761). En Windows depende de la versión. Sin reproducir en cada SO objetivo no puedo confirmar la afirmación universal.
- **Cambio sugerido (si se confirma)**:
  ```markdown
  > **Tip**: La mayoría de sistemas (Linux con systemd-resolved, macOS 11+)
  > resuelven `*.localhost` a 127.0.0.1 automáticamente (RFC 6761). En Windows
  > o en sistemas con resolución estricta, añade entradas explícitas en
  > `/etc/hosts` (o `C:\Windows\System32\drivers\etc\hosts`):
  >
  > ```
  > 127.0.0.1  cerebro.localhost ingest.localhost n8n.localhost rabbitmq.localhost \
  >            grafana.localhost prometheus.localhost qdrant.localhost jaeger.localhost \
  >            llm.localhost traefik.localhost
  > ```
  ```

---

## Aprobado sin cambios

- **§1.1 Versiones mínimas** (`docker compose ≥ 2.22`, `python3 ≥ 3.9`, `node v20`, `uvx ≥ 0.11`) — coherente con los scripts y Dockerfiles.
- **§3c Reset script** — coincide con `reset.sh:1-200`: parar contenedores, eliminar volúmenes con prefijo `linkanvil_`, prune builder cache, rehash de RabbitMQ via `definitions.json` (`reset.sh:107-127`), `docker compose up -d` final con espera de healthchecks (`reset.sh:140-180`).
- **§3b idempotencia del runner de migraciones** — verificado contra `scripts/migrate.sh:34-79`: schema `cerebro.schema_migrations(version, applied_at)`, parsing del prefijo numérico con strip de leading zeros, transacción por archivo con rollback (`psql -1 ON_ERROR_STOP=1`), exit code 0 si no hay pendientes.
- **§6.4 Tailscale Funnel — pasos one-time y volumen persistente** — coherente con `docker-compose.yml:861-887`: imagen `tailscale/tailscale:stable`, profile `telegram`, hostname `linkanvil-ingest`, volumen `tailscale-state` con nombre explícito `cerebro-tailscale-state` (`docker-compose.yml:900-901`).
- **§6.5 Backup script** — coincide con `scripts/backup.sh:1-70`: `pg_dump` gzipado, snapshots de Qdrant vía HTTP API (`/collections/<c>/snapshots`), retención por `BACKUP_RETENTION_DAYS` (default 7).
- **Lista de migraciones** — el repo tiene `0001`-`0011` en `infra/postgres/migrations/` (11 migraciones), todas con prefijo numérico correcto. La afirmación "0001_baseline registra estado inicial" coincide con el contenido del archivo (`0001_baseline.sql:1-50`).
- **Endpoints de la tabla FASE 5** (frontend 3001, API 8001, n8n 5678, RabbitMQ 15672, Grafana 3000, Jaeger 16686, Qdrant 6333, Traefik 8080) — todos pinneados en `docker-compose.yml:228-755`.
- **`init.sql` montado en `/docker-entrypoint-initdb.d/01_init.sql:ro`** — confirmado en `docker-compose.yml:448`. Crea schemas `cerebro` y `n8n` (`infra/postgres/init.sql:17-18`).
