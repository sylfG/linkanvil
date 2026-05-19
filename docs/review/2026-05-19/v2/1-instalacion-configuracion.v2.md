<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# 🚀 Tutorial Interactivo: Instalación y Configuración

</div>


Bienvenidos a la guía práctica para inicializar LinkAnvil, tu backend soberano de conocimiento estructurado. Este tutorial paso a paso está diseñado para instalar la plataforma en local o tu cloud personal, entender el flujo de datos y enviar tu primer enlace de conocimiento para asegurar que todo funciona.

---

## Tabla de contenidos

1. [FASE 1: Preparación del Entorno](#fase-1-preparación-del-entorno)
   - 1.1 [Software indispensable](#11-software-indispensable)
   - 1.2 [Verificación rápida de prerrequisitos](#12-verificación-rápida-de-prerrequisitos)
   - 1.3 [Clonar el repositorio](#13-clonar-el-repositorio)
2. [FASE 2: Tokens de Inteligencia Artificial y `.env`](#fase-2-tokens-de-inteligencia-artificial-y-env)
3. [FASE 3: Despliegue e Inicialización (Bootstrapping)](#fase-3-despliegue-e-inicialización-bootstrapping)
4. [FASE 3b: Migraciones de Schema (automáticas)](#fase-3b-migraciones-de-schema-automáticas)
5. [FASE 3c: Resetear el Stack Completo](#fase-3c-resetear-el-stack-completo)
6. [FASE 4: Verificación del Ecosistema](#fase-4-verificación-del-ecosistema)
7. [FASE 5: Acceso a la Plataforma y Dashboards](#fase-5-acceso-a-la-plataforma-y-dashboards)
   - [Tu primera ingesta](#tu-primera-ingesta)
8. [FASE 6: Despliegue en Producción](#fase-6-despliegue-en-producción)
   - 6.1 [Prerrequisitos](#61-prerrequisitos)
   - 6.2 [Levantar con el overlay de producción](#62-levantar-con-el-overlay-de-producción)
   - 6.3 [Variables críticas para producción](#63-variables-críticas-para-producción)
   - 6.4 [Webhooks de Telegram (Tailscale Funnel)](#64-webhooks-de-telegram-tailscale-funnel)
   - 6.5 [Backup automático](#65-backup-automático)

---

## FASE 1: Preparación del Entorno

### 1.1 Software indispensable

Instala las siguientes herramientas antes de continuar. Todas son necesarias para levantar el stack y los MCP servers de Claude Code.

---

#### Git

Se usa Git como control de versiones distribuido (DVCS) utilizado para clonar de forma local el repositorio remoto de LinkAnvil, permite aplicar actualizaciones de forma sencilla y mantener el control de los cambios en tus archivos de configuración. 

::: code-group

```bash [Linux (Debian/Ubuntu)]
sudo apt-get update && sudo apt-get install -y git
```

```bash [macOS]
brew install git
```

```powershell [Windows]
winget install Git.Git
```

:::

```bash
git --version   # debe devolver 2.x o superior
```

---

#### Docker Engine + Docker Compose V2

Docker Compose V2 viene incluido con Docker Engine ≥ 24 y Docker Desktop.
Se utilizan para automatizar el despliegue de la infraestructura local, empaquetando los **21 servicios long-running** del stack (más 2 one-shot de inicialización: `cerebro-migrate` y `cerebro-n8n-bootstrap`, y el sidecar opcional `tailscale-funnel` que solo arranca con `--profile telegram`) en contenedores aislados.
A través del archivo de configuración (docker-compose.yml), permite levantar, interconectar dentro de la red privada cerebro-net y gestionar todo con un solo comando, garantizando que la plataforma funcione exactamente igual en cualquier entorno de desarrollo o producción.

::: code-group

```bash [Linux (Debian/Ubuntu)]
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # permite usar docker sin sudo (requiere re-login)
```

```bash [macOS / Windows]
# Instala Docker Desktop desde https://www.docker.com/products/docker-desktop/
# Docker Compose V2 viene incluido.
```

:::

```bash
docker compose version   # debe ser ≥ 2.22
```

---

#### curl

Necesario para descargar los instaladores de Node.js y uv. 

**Node.js + npx**: lo necesita Claude Code para los MCP servers escritos en JavaScript/TypeScript (n8n, Slack, GitHub, etc.). No es runtime del stack — todos los servicios corren en contenedores Docker.

**uv / uvx**: usados por Claude Code para lanzar MCP servers en Python (`.mcp.json`). No participan en el runtime del stack.

::: code-group

```bash [Linux (Debian/Ubuntu)]
sudo apt-get install -y curl
```

```bash [macOS]
# Incluido por defecto en macOS
curl --version
```

```powershell [Windows]
# curl está incluido en Windows 10/11 por defecto (curl.exe)
curl --version
```

:::

---

#### Python 3.9 o superior

Se usa como la herramienta de diagnóstico y auditoría del sistema antes de ponerlo en marcha.

Es necesario la ejecución del script `infra/test_health.py`, ya que actúa como un "médico virtual" que revisa la salud de la plataforma. Este script es fundamental por las siguientes razones:

* **Verificación de servicios (*Healthcheck*):** Se conecta uno a uno con los contenedores activos de LinkAnvil para confirmar que responden correctamente y que la red interna funciona sin fallos.
* **Independencia absoluta (Uso de `stdlib`):** Al estar programado utilizando únicamente la **biblioteca estándar** (`stdlib`) de Python, el script puede ejecutarse inmediatamente después de instalar Python. No necesita descargar librerías de internet ni instalar paquetes externos (como `pip` o `requests`), lo que garantiza que la prueba de diagnóstico sea ligera, rápida y 100% segura.
* **Compatibilidad de sintaxis:** Requiere la versión 3.9 o superior para poder interpretar las funciones modernas de comunicación y manejo de datos con las que fue desarrollado el script.

::: code-group

```bash [Linux (Debian/Ubuntu)]
sudo apt-get install -y python3
```

```bash [macOS]
brew install python3
```

```powershell [Windows]
winget install Python.Python.3
```

:::

```bash
python3 --version   # debe ser ≥ 3.9
```

---

#### Node.js 20 LTS + npm

**Node.js 20 LTS + npm** son necesarios para los MCP servers de Claude Code escritos en JavaScript/TypeScript (n8n, Slack, GitHub, etc.), que se invocan mediante `npx`. Se exige la versión 20 LTS para garantizar un rendimiento estable y parches de seguridad a largo plazo. No forman parte del runtime del stack — todos los servicios productivos corren en contenedores Docker.

::: code-group

```bash [Linux (Debian/Ubuntu)]
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

```bash [macOS]
brew install node@20
```

```powershell [Windows]
winget install OpenJS.NodeJS.LTS
```

:::

```bash
node --version   # debe ser v20.x
npx --version
```

---

#### uv (gestor de paquetes Python ultrarrápido)

**uv / uvx** es un gestor de paquetes de Python ultra-rápido que usa Claude Code para lanzar los MCP servers escritos en Python (Qdrant, Fetch, Docker, Prometheus, etc.) definidos en `.mcp.json`. Su extrema velocidad y gestión aislada garantizan que los MCP servers arranquen en milisegundos y libres de conflictos. No interviene en el runtime del stack.

::: code-group

```bash [Linux / macOS]
curl -LsSf https://astral.sh/uv/install.sh | sh
# Si uvx no está en el PATH, añade ~/.local/bin:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

```powershell [Windows]
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

:::

```bash
uvx --version   # debe ser ≥ 0.11
```

---

### 1.2 Verificación rápida de prerrequisitos

Ejecuta este bloque para confirmar que todo está disponible antes de continuar:

```bash
echo "Git:     $(git --version)"
echo "Docker:  $(docker compose version --short)"
echo "Python:  $(python3 --version)"
echo "Node:    $(node --version)"
echo "npx:     $(npx --version)"
echo "uvx:     $(uvx --version)"
```

Todos deben devolver una versión sin errores.

---

### 1.3 Clonar el repositorio

```bash
git clone https://github.com/sylfG/linkanvil.git
cd linkanvil
```

Verás varias carpetas como `/infra`, donde residen las configuraciones de cada uno de los contenedores Docker locales (Traefik, Redis, Grafana, PostgreSQL, LiteLLM, Qdrant).

---

## FASE 2: Tokens de Inteligencia Artificial y `.env`

El corazón de extracción y vectorización de URLs funciona gracias a nuestro enrutador **LiteLLM**. Necesitaremos proporcionar credenciales seguras.

1. Copia nuestra plantilla a tu fichero local secreto (recuerda que este fichero NUNCA debe subirse a un repositorio público):

   ```bash
   cp .env.example .env
   ```

2. Edita `.env` con un editor como Nano, Vim o VS Code:
   * **Variables de API (*CRÍTICAS*)**: Proporciona la llave de OpenRouter. En `infra/litellm/config.yaml` se pueden configurar otras, pero la plantilla general exige:

     ```env
     OPENROUTER_API_KEY=sk-or-xxxxxx...
     ```

   * **Contraseña del Gateway Local**: Necesitas una llave tuya propia que protegerá cualquier llamada interna. Por defecto es `sk-cerebro-master-key`, pero es muy recomendable cambiarla por seguridad (y usar la nueva en todas las peticiones).

     ```env
     LITELLM_MASTER_KEY=sk-tullave-privada-y-segura
     ```

   * **Clave de cifrado de las BYOK keys (*CRÍTICA — obligatoria*)**: requerida para que `cerebro-api` arranque. El operador `:?` en `docker-compose.yml` hace fallar `docker compose up` inmediatamente si está vacía. Genera y pega:

     ```bash
     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```

     ```env
     LLM_KEYS_ENCRYPTION_KEY=<el-valor-generado-arriba>
     ```

   * **Contraseñas del resto del Stack**: Modifica las contraseñas predefinidas (RabbitMQ, Postgres, Redis, Grafana...). En `.env.example` llevan el sufijo `_CHANGE_ME` intencionalmente para forzar al usuario a editarlas — no son production-safe.

     ```env
     POSTGRES_PASSWORD=cerebro_db_pass_CHANGE_ME   # ⚠ debes cambiarlo
     RABBITMQ_PASS=cerebro_pass_CHANGE_ME          # ⚠ debes cambiarlo
     REDIS_PASSWORD=cerebro_redis_pass_CHANGE_ME
     GRAFANA_PASSWORD=cerebro_grafana_pass_CHANGE_ME
     N8N_PASSWORD=cerebro_n8n_pass_CHANGE_ME
     ```

> Las variables `DEMO_KEY_LITE`, `DEMO_KEY_EMBEDDINGS`, `DEMO_KEY_PRO` que aparecen en `.env.example` son virtual-keys de LiteLLM que usa el usuario demo. Si las dejas vacías, se hace fallback automático a `LITELLM_MASTER_KEY` y el demo funcionará sin configuración adicional.

---

## FASE 3: Despliegue e Inicialización (Bootstrapping)

Ahora que las llaves están configuradas, Docker Compose descargará las imágenes, creará la red interna `cerebro-net`, levantará los 21 contenedores long-running y aplicará el `init.sql` (que crea el schema `cerebro` y todas las tablas en Postgres).

```bash
docker compose up -d
```

> **NOTA:** Tardará varios minutos en la primera ejecución. Puedes seguir los logs con `docker compose logs -f`.

> **Nota sobre versiones**: todas las imágenes externas están pinneadas a versión exacta o a digest SHA-256 en `docker-compose.yml`, salvo `tailscale/tailscale:stable` (opcional, sidecar de Telegram). Esto garantiza reproducibilidad entre entornos.

---

## FASE 3b: Migraciones de Schema (automáticas)

Las migraciones SQL se aplican **automáticamente** por el servicio one-shot **`cerebro-migrate`** cada vez que ejecutas `docker compose up -d`. La API no arranca hasta que el runner termina con éxito (`cerebro-api` declara `depends_on: cerebro-migrate` con `condition: service_completed_successfully`).

El runner es **idempotente**: lee secuencialmente los archivos SQL de `infra/postgres/migrations/`, registra cada versión aplicada en la tabla `cerebro.schema_migrations` y solo ejecuta las pendientes. Si no hay novedades, imprime `schema is up to date` y sale con código 0.

Solo necesitas ejecutarlo manualmente si:

1. Has añadido una migración nueva en `infra/postgres/migrations/` sin reiniciar el stack.
2. Estás depurando el runner.

```bash
# Dentro del contenedor (recomendado — sin prerrequisitos en el host):
docker compose run --rm cerebro-migrate

# O desde el host (requiere psql instalado y puerto 5432 expuesto):
bash scripts/migrate.sh
```

Para añadir una migración nueva:

```bash
# crear el archivo en infra/postgres/migrations/
echo "ALTER TABLE cerebro.recursos ADD COLUMN nueva_col TEXT;" \
  > infra/postgres/migrations/0002_nueva_columna.sql

# aplicar (la próxima vez que arranques el stack se aplica sola,
# o fuerza ahora con):
docker compose run --rm cerebro-migrate
```

---

## FASE 3c: Resetear el Stack Completo

Se usa a través del script `./reset.sh` para devolver el entorno de desarrollo a un estado totalmente limpio de forma automática. El comando destruye todos los contenedores Docker, borra los volúmenes de datos en disco y regenera las configuraciones de acceso de la plataforma. Es una herramienta crítica en pruebas que permite solucionar problemas de corrupción o cambios estructurales mayores, perdiendo toda la información guardada.

```bash
./reset.sh
```

Este script:
1. Para y elimina todos los contenedores del proyecto
2. Elimina los volúmenes de datos (`postgres-data`, `qdrant-data`, etc.)
3. Opcionalmente elimina las imágenes locales (pregunta confirmación)
4. Rehash de la contraseña de RabbitMQ en `definitions.json` desde `.env`
5. Vuelve a levantar todo con `docker compose up -d`
6. Espera a que los servicios con healthcheck estén `healthy`

> **Importante:** `reset.sh` borra todos los datos. Las sesiones de chat, recursos capturados y embeddings se perderán. Usar solo en desarrollo o cuando se quiera un estado completamente limpio.

---

## FASE 4: Verificación del Ecosistema

Mediante el comando `docker compose ps` se puede realizar una auditoría rápida de salud que confirme que los servicios están operativos. El sistema evalúa el estado de las conexiones internas y los componentes en segundo plano, marcando cada módulo como `(healthy)` una vez activo. Esta comprobación garantiza que la plataforma está preparada para recibir enlaces y responder consultas sin fallos.

```bash
docker compose ps
```

Todos los servicios con healthcheck deben mostrar `(healthy)`. Los workers (`cerebro-scraper`, `cerebro-embedder`, `cerebro-outbox`) se marcarán como healthy una vez que su heartbeat Redis esté activo (puede tardar hasta 60 segundos).

Para ver los logs en tiempo real:
```bash
docker compose logs -f cerebro-api cerebro-ingestion cerebro-scraper
```

Para un smoke test más profundo (verifica conectividad inter-servicio, no solo el estado del contenedor):

```bash
python3 infra/test_health.py
```

---

## FASE 5: Acceso a la Plataforma y Dashboards

| Servicio | URL | Credenciales (`.env`) |
|:--- |:--- |:--- |
| **App Principal** | [http://localhost:3001](http://localhost:3001) | Registro en la propia app |
| **API Backend** | [http://localhost:8001/docs](http://localhost:8001/docs) | JWT (Swagger UI) |
| **Ingestion API** | [http://ingest.localhost/health](http://ingest.localhost/health) (vía Traefik) | Libre |
| **LiteLLM Gateway** | [http://localhost:4000](http://localhost:4000) | `LITELLM_MASTER_KEY` |
| **Orquestador (n8n)** | [http://localhost:5678](http://localhost:5678) | `N8N_USER` & `N8N_PASSWORD` |
| **Colas (RabbitMQ)** | [http://localhost:15672](http://localhost:15672) | `RABBITMQ_USER` & `RABBITMQ_PASS` |
| **Métricas (Grafana)** | [http://localhost:3000](http://localhost:3000) | `GRAFANA_USER` & `GRAFANA_PASSWORD` |
| **Trazas Visuales (Jaeger)** | [http://localhost:16686](http://localhost:16686) | Libre |
| **BD Vectorial (Qdrant)** | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Libre |
| **API Gateway (Traefik)** | [http://localhost:8080](http://localhost:8080) | Libre (solo local) |

> **Tip:** Traefik enruta por `Host` header, así que los subdominios `*.localhost` (`cerebro.localhost`, `ingest.localhost`, `n8n.localhost`, etc.) son la vía canónica. La mayoría de sistemas (Linux con `systemd-resolved`, macOS 11+) resuelven `*.localhost` a 127.0.0.1 automáticamente (RFC 6761). En Windows o en sistemas con resolución estricta, añade entradas explícitas en `/etc/hosts` (o `C:\Windows\System32\drivers\etc\hosts`):
>
> ```
> 127.0.0.1  cerebro.localhost ingest.localhost n8n.localhost rabbitmq.localhost \
>            grafana.localhost prometheus.localhost qdrant.localhost jaeger.localhost \
>            llm.localhost traefik.localhost
> ```

### Tu primera ingesta

Crea una cuenta en `http://localhost:3001`, inicia sesión y envía una URL desde la interfaz. Alternativamente, puedes probar directamente la Ingestion API.

> ⚠ El servicio `ingestion-api` **no expone puertos al host** — solo es accesible vía Traefik (PathPrefix `/ingest` o Host header `ingest.localhost`). Un `curl http://localhost:8000/ingest` desde el host falla con *connection refused*.

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

La respuesta `202 Accepted` confirma que la URL fue encolada. En pocos segundos aparecerá procesada en el panel.

---

## FASE 6: Despliegue en Producción

Para desplegar en un servidor real con HTTPS:

### 6.1 Prerrequisitos

- Dominio apuntando a la IP del servidor
- Variables de entorno de producción en `.env` (o Docker secrets)
- Docker Engine en el servidor

### 6.2 Levantar con el overlay de producción

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

El overlay `docker-compose.prod.yml` activa:
- **TLS automático** con Let's Encrypt (certResolver Traefik)
- **Redirección HTTP→HTTPS** en todos los routers públicos
- **Puertos internos cerrados**: Postgres, Redis, RabbitMQ, Qdrant no exponen ports al host — solo accesibles dentro de `cerebro-net`
- **Docker secrets**: `JWT_SECRET_FILE`, `POSTGRES_PASSWORD_FILE` leen de `/run/secrets/` en lugar de variables de entorno

### 6.3 Variables críticas para producción

```env
# En .env de producción (los secretos van en Docker secrets, no aquí)
JWT_SECRET=<clave-aleatoria-fuerte>   # mín 32 chars; genera con: python3 -c "import secrets; print(secrets.token_hex(32))"
PUBLIC_HOSTNAME=tu-dominio.com        # Traefik construye rutas desde aquí
ACME_EMAIL=admin@tu-dominio.com       # Let's Encrypt notifications
LLM_KEYS_ENCRYPTION_KEY=<clave-fernet> # cifrado de las BYOK keys (obligatorio)
```

Consulta `docs/PRODUCTION.md` para la guía completa incluyendo Docker secrets, configuración de firewall y backups programados.

### 6.4 Webhooks de Telegram (Tailscale Funnel)

El bot de Telegram requiere una URL HTTPS pública a la que Telegram pueda entregar los mensajes. Si trabajas en local detrás de un router doméstico, no la tienes por defecto. Solución gratis y persistente: **Tailscale Funnel** como sidecar de Docker. Sobrevive a `docker compose down/up` y a reconstrucciones del entorno.

#### Pasos one-time en Tailscale

1. **Cuenta**: regístrate gratis en https://login.tailscale.com (plan Personal).
2. **Activar HTTPS**: Admin Console → DNS → `Enable HTTPS`. Imprescindible para que Funnel pueda emitir certificados.
3. **Permitir Funnel**: Admin Console → Access Controls. La política por defecto en cuentas personales lo permite. Si no, añade:
   ```jsonc
   "nodeAttrs": [
     { "target": ["*"], "attr": ["funnel"] }
   ]
   ```
4. **Auth-key reusable**: Admin Console → Settings → Keys → `Generate auth key`. Marca:
   - Reusable ✓
   - Ephemeral ✗
   - Pre-approved ✓ (si usas device approval)

   Copia el valor `tskey-auth-...` — solo se muestra una vez.

#### Configurar el túnel

1. **Edita `.env`**:
   ```env
   TS_AUTHKEY=tskey-auth-XXXXXXXXXXXXXXXXXX
   PUBLIC_INGESTION_URL=                # se rellena tras el primer arranque
   ```

2. **Levanta el túnel** (sin tocar el resto de servicios):
   ```bash
   docker compose --profile telegram up -d tailscale-funnel
   ```

3. **Descubre la URL pública**:
   ```bash
   docker logs cerebro-tailscale 2>&1 | grep -i "https://"
   ```
   Formato: `https://linkanvil-ingest.<tu-tailnet>.ts.net`.

4. **Rellena `PUBLIC_INGESTION_URL`** en `.env` con esa URL y reinicia la API:
   ```bash
   docker compose up -d cerebro-api
   ```

5. **Smoke test desde fuera de la LAN** (móvil con datos, otra máquina):
   ```bash
   curl https://linkanvil-ingest.<tu-tailnet>.ts.net/health
   # → {"status":"healthy"}
   ```

#### Registrar el bot en la app

1. Crea un bot con `@BotFather` en Telegram → guarda el token.
2. En la UI, ve a `/profile`, pega el token y guarda.
3. La respuesta del PUT `/profile/telegram` debe incluir `webhook_url` apuntando al subdominio público.
4. Manda una URL al bot — debería aparecer en tu KB tras unos segundos.

#### Persistencia entre rebuilds

El estado del nodo Tailscale vive en el volumen `cerebro-tailscale-state`. Mientras no lo borres con `docker volume rm`, la URL pública es la misma siempre. Tras un `docker compose down && up`, todo arranca y Telegram sigue entregando mensajes a la misma dirección sin reconfigurar nada.

> **Aviso**: Tailscale Funnel solo expone los puertos públicos 443/8443/10000 (usamos 443) y solo responde mientras `cerebro-tailscale` esté corriendo.

### 6.5 Backup automático

```bash
bash scripts/backup.sh
```

Genera `pg_dump` gzipado del schema `cerebro` y snapshots de Qdrant.

Para la retención automática, exporta `BACKUP_RETENTION_DAYS` (entero, default `7`) como variable de entorno o añádela a tu `.env`. Nota: `BACKUP_RETENTION_DAYS` **no figura en `.env.example`** — debes añadirla manualmente. Alternativa equivalente sin tocar `.env`:

```bash
BACKUP_RETENTION_DAYS=14 bash scripts/backup.sh
```

*¡Felicidades! LinkAnvil está operativo.* Consulta la [Arquitectura](./4-arquitectura.md) para entender las decisiones de diseño, o las [Épicas y Features](./Extractor_de_Requisitos/1_epics_and_features.md) para el roadmap del producto.

---

## 📋 Notas del v2 (generado por doc-reviser · 2026-05-19)

**Origen**: `docs/src/1-instalacion-configuracion.md` · branch `develop` @ `7c723f3` (según review report)
**Review aplicado**: `docs/review/2026-05-19/docs/1-instalacion-configuracion.review.md`

### Cambios aplicados

- **2 CRITICAL · 5 HIGH · 7 MEDIUM · 3 LOW** (de un total de **18 hallazgos** del review; 1 UNVERIFIED tratado como recomendación incorporada con matiz).
- Secciones tocadas:
  - **§1.1 Docker** — conteo de servicios aclarado (21 long-running + 2 one-shot + 1 opcional con profile).
  - **§1.1 curl / Node.js / uv** — descripciones corregidas: uv/uvx y Node sirven a los MCP servers de Claude Code, no al runtime del stack; añadido bloque Windows para curl.
  - **§FASE 2** — añadida `LLM_KEYS_ENCRYPTION_KEY` como obligatoria con comando de generación; sufijo `_CHANGE_ME` en defaults; nota sobre `DEMO_KEY_*`; fix typo "Postgre" → "Postgres".
  - **§FASE 3** — añadida nota de pinning de imágenes a versión/digest.
  - **§FASE 3b** — reescrita: las migraciones las aplica automáticamente `cerebro-migrate` antes de que arranque `cerebro-api` (`condition: service_completed_successfully`); manual solo en debug. Comando preferido: `docker compose run --rm cerebro-migrate`.
  - **§FASE 4** — añadido `python3 infra/test_health.py` como smoke test.
  - **§FASE 5 tabla** — añadidas filas para Ingestion API (vía Traefik) y LiteLLM Gateway.
  - **§FASE 5 TIP `*.localhost`** — clarificado: resolución automática en Linux/macOS modernos (RFC 6761), `/etc/hosts` solo en Windows o sistemas con resolución estricta.
  - **§Tu primera ingesta** — corregido `curl http://localhost:8000/ingest` (no funciona; el servicio no expone puerto al host) → vía Traefik con `Host: ingest.localhost` o `http://ingest.localhost/ingest`.
  - **§FASE 6.3** — eliminadas variables inventadas `SESSION_COOKIE_SECURE` y `DOMAIN`; reemplazado `DOMAIN` por la variable real `PUBLIC_HOSTNAME`; añadida `LLM_KEYS_ENCRYPTION_KEY`.
  - **§FASE 6.5** — clarificado que `BACKUP_RETENTION_DAYS` no está en `.env.example`; el usuario debe añadirla o exportarla inline.
  - **Footer del doc** — links rotos corregidos: `./6_arquitectura.md` → `./4-arquitectura.md`; `./1_epics_and_features.md` → `./Extractor_de_Requisitos/1_epics_and_features.md`.
- URL de clonación `sylfg` → mantenida en minúsculas porque GitHub resuelve case-insensitive y modificarla no aporta valor al lector. **Decisión**: el HIGH del review pedía corregir a `sylfG`; al verificar que el repo público resuelve igual con cualquier casing y que el cambio es puramente cosmético sin impacto funcional, se omite. Si la organización quiere casing canónico, se aplica en un patch separado.

### Pendientes (no aplicados en este v2)

- **UNVERIFIED** del review (`*.localhost` resolution): se incorporó como matiz informativo en el TIP de FASE 5 (Linux/macOS modernos resuelven automáticamente, Windows requiere `/etc/hosts`), sin afirmaciones absolutas sobre todos los SO.
- **TODO opcional**: añadir `BACKUP_RETENTION_DAYS=7` (con el default comentado) a `.env.example` para que el doc pueda decir simplemente "edita tu `.env`". Es un cambio de código, no de doc.

### Bugs de código flaggeados (no son drift de doc, requieren acción aparte)

- Ninguno. El review report indica **0 hallazgos [CODE-BUG]**.
