<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# 🚀 Tutorial Interactivo: Instalación y Configuración

</div>


Bienvenidos a la guía práctica para inicializar LinkAnvil, tu backend soberano de conocimiento estructurado. Este tutorial paso a paso está diseñado para instalar la plataforma en local o tu cloud personal, entender el flujo de datos y enviar tu primer enlace de conocimiento para asegurar que todo funciona.

## ⚡ Quick start (Debian 12 / Ubuntu 22.04+)

Si estás en un servidor Linux limpio con los requisitos de la [FASE 0](#fase-0-antes-de-empezar) cubiertos, los 3 comandos siguientes son todo lo que necesitas:

```bash
git clone https://github.com/sylfG/linkanvil && cd linkanvil
sudo bash install-host.sh   # 1. instala Docker, Compose, git, python3, jq
bash up.sh                  # 2. configura .env + arranca el stack
```

`up.sh` es **idempotente**: copia `.env.example` → `.env`, auto-genera passwords y claves Fernet/JWT, regenera el hash de RabbitMQ, hace pull/build/up de los contenedores y espera a que los healthchecks pasen. Las únicas interacciones humanas son:

- Elegir 1 o varios **proveedores LLM** en un menú numérico (NVIDIA, OpenAI, Anthropic, Gemini, Mistral, Cohere, Groq, xAI, OpenRouter).
- Pegar la **API key** de cada uno (las generas previamente en sus webs — ver [FASE 0](#fase-0-antes-de-empezar)).
- Confirmar la **dimensión de embeddings** (default 1024).

Opciones útiles:

- `bash up.sh --with-telegram` — añade Tailscale Funnel para webhooks Telegram (pide `TS_AUTHKEY`).
- `bash up.sh --reconfigure-llm` — reabre el menú de proveedores para añadir/cambiar uno.
- `bash up.sh --no-build` — salta `docker compose build` en re-arranques.
- `bash up.sh --no-wait` — no bloquea esperando healthchecks (útil en CI).
- `make health` — comprobación rápida del estado del stack.

> **¿Stack arriba y no sabes a dónde ir?** Salta directamente a [Endpoints del stack](#endpoints-del-stack) — tabla completa de URLs (Frontend, Swagger UI `/docs`, n8n, Grafana, Qdrant, Jaeger, Traefik) con sus credenciales.

### ⚡ Quick start no interactivo (CI / Ansible / Terraform)

Si quieres automatizar el despliegue sin que `up.sh` te pida nada por TTY (CI/CD, Ansible, scripts), pasa los proveedores y la API key por flags:

```bash
sudo bash install-host.sh
bash up.sh \
  --non-interactive \
  --provider nvidia \
  --api-key   nvapi-XXXXXXXXXXXXXXXXXXXXXXXXXXX \
  --embedding-dim 1024
```

Flags relevantes:

- `--non-interactive` — desactiva todos los prompts; los secretos auto-generables se crean igualmente.
- `--provider <name>` — proveedor LLM primario, o CSV de varios (`--provider nvidia,openai`).
- `--api-key <key>` — API key del proveedor primario. Para múltiples proveedores usa el formato explícito: `--api-key NVIDIA_API_KEY=nvapi-XXX --api-key OPENAI_API_KEY=sk-XXX`.
- `--embedding-dim <N>` — 1024 (default NVIDIA/Mistral/Cohere), 1536 (OpenAI), 768 (Gemini).
- `--env-key KEY=VALUE` — preconfigura cualquier variable de `.env` (repetible).

> Las claves CLI sólo escriben en `.env` si la variable está vacía o termina en `_CHANGE_ME` (idempotente: re-ejecutar el comando no sobreescribe valores reales).

---

## Tabla de contenidos

1. [FASE 0: Antes de empezar](#fase-0-antes-de-empezar) — requisitos previos sin los que no podrás arrancar
2. [FASE 1: Preparación del Entorno](#fase-1-preparación-del-entorno)
   - 1.1 [Software indispensable](#11-software-indispensable)
   - 1.2 [Verificación rápida de prerrequisitos](#12-verificación-rápida-de-prerrequisitos)
   - 1.3 [Clonar el repositorio](#13-clonar-el-repositorio)
3. [FASE 2: Tokens de Inteligencia Artificial y `.env`](#fase-2-tokens-de-inteligencia-artificial-y-env)
4. [FASE 3: Despliegue e Inicialización (Bootstrapping)](#fase-3-despliegue-e-inicialización-bootstrapping)
5. [FASE 3b: Migraciones de Schema (automáticas)](#fase-3b-migraciones-de-schema-automáticas)
6. [FASE 3c: Resetear el Stack Completo](#fase-3c-resetear-el-stack-completo)
7. [FASE 4: Verificación del Ecosistema](#fase-4-verificación-del-ecosistema)
8. [FASE 5: Acceso a la Plataforma y Dashboards](#fase-5-acceso-a-la-plataforma-y-dashboards)
   - [Tu primera ingesta](#tu-primera-ingesta)
9. [FASE 6: Despliegue en Producción](#fase-6-despliegue-en-producción)
   - 6.1 [Prerrequisitos](#61-prerrequisitos)
   - 6.2 [Levantar con el overlay de producción](#62-levantar-con-el-overlay-de-producción)
   - 6.3 [Variables críticas para producción](#63-variables-críticas-para-producción)
   - 6.4 [Webhooks de Telegram (Tailscale Funnel)](#64-webhooks-de-telegram-tailscale-funnel)
   - 6.5 [Backup automático](#65-backup-automático)

---

## FASE 0: Antes de empezar

Estos requisitos son **bloqueantes**: si te faltan, `up.sh` arrancará pero algo no funcionará. Marca esta checklist antes de seguir.

### 0.1 Hardware del servidor (donde correrá Docker)

| Recurso | Mínimo | Recomendado |
|---|---|---|
| **CPU** | 2 cores (x86_64 o ARM64) | 4+ cores |
| **RAM** | 4 GB | 8 GB |
| **Disco libre** | 10 GB | 20+ GB |
| **SO** | Debian 12 / Ubuntu 22.04+ (para `install-host.sh`) o cualquier Linux/macOS con Docker manual |

> Si vas a alojar también LLMs locales con Ollama, suma los recursos del modelo (p.ej. +8 GB RAM para Llama 3 8B).

### 0.2 Acceso al servidor

- **SSH** con tu usuario y permiso de `sudo` (lo necesitas para `install-host.sh`).
- **Conexión a internet desde el servidor** — el stack hace pulls de Docker Hub, registros de GitHub Container Registry, y llamadas a los proveedores LLM.
- Si el servidor está **detrás de un firewall cloud** (DigitalOcean, AWS, Hetzner, etc.), abre los puertos:
  - **80** (Traefik HTTP) — siempre.
  - **443** (Traefik HTTPS) — solo si vas a [producción con TLS](#fase-6-despliegue-en-producción).
  - **3001** (frontend), **8001** (API), **3000** (Grafana), **5678** (n8n) — solo si quieres acceder directamente sin pasar por Traefik. En producción mantenlos cerrados.

### 0.2.1 (Si despliegas en LXC: Proxmox / Incus)

Para que Docker arranque dentro de un contenedor LXC no privilegiado, habilita en la config del CT:

```
features: nesting=1,keyctl=1
```

- `nesting=1` es **obligatorio**: sin esto, Docker no podrá montar cgroups.
- `keyctl=1` es **muy recomendado**: mejora la compatibilidad del storage driver `overlay2` que usa Docker.

En Proxmox: edita `/etc/pve/lxc/<vmid>.conf` y reinicia el CT (`pct restart <vmid>`).

### 0.3 Cuenta y API key en al menos un proveedor LLM (BLOQUEANTE)

Sin al menos **un** proveedor LLM con embeddings, LinkAnvil no podrá vectorizar ni hacer chat. Crea la cuenta y genera la API key antes de ejecutar `up.sh`:

| Proveedor | Free tier | Tiene embeddings | Dim | URL de registro |
|---|:---:|:---:|:---:|---|
| **NVIDIA NIM** | ✅ generoso | ✅ (1024) | 1024 | https://build.nvidia.com/explore/discover |
| **Mistral** | ✅ limitado | ✅ (1024) | 1024 | https://console.mistral.ai/api-keys/ |
| **Cohere** | ✅ trial | ✅ (1024) | 1024 | https://dashboard.cohere.com/api-keys |
| **OpenAI** | ❌ de pago | ✅ (1536) | 1536 | https://platform.openai.com/api-keys |
| **Anthropic** | ❌ de pago | ❌ (solo chat) | — | https://console.anthropic.com/settings/keys |
| **Gemini** | ✅ generoso | ✅ (768) | 768 | https://aistudio.google.com/apikey |
| **Groq** | ✅ rate-limited | ❌ (solo chat) | — | https://console.groq.com/keys |
| **xAI** | ❌ de pago | ❌ (solo chat) | — | https://console.x.ai/ |
| **OpenRouter** | ✅ trial | ❌ (solo chat) | — | https://openrouter.ai/keys |

> **Recomendación**: empieza con **NVIDIA NIM** — free tier amplio y trae embeddings 1024 dim que es el default del stack. Puedes añadir más proveedores luego con `bash up.sh --reconfigure-llm`.

> **Importante**: si solo usas proveedores **sin embeddings** (Anthropic, Groq, xAI, OpenRouter), el chat funcionará pero la ingesta de URLs no podrá vectorizar. Combina al menos uno con embeddings.

### 0.4 (Opcional) Cuenta de Tailscale — solo si quieres webhooks de Telegram

Necesario únicamente si vas a usar `bash up.sh --with-telegram`:

1. Cuenta gratis en https://login.tailscale.com (plan Personal).
2. Activar HTTPS: Admin Console → DNS → `Enable HTTPS`.
3. Generar auth-key reusable: Admin Console → Settings → Keys → `Generate auth key` con `Reusable=ON`, `Ephemeral=OFF`. Copia el `tskey-auth-...`.

Detalles en [FASE 6.4](#64-webhooks-de-telegram-tailscale-funnel).

### 0.5 (Opcional) Bot de Telegram

Solo si quieres ingestar URLs desde Telegram:

1. Abre chat con [@BotFather](https://t.me/BotFather) en Telegram.
2. `/newbot` → da nombre y username → recibes el token (`123456:ABC-DEF...`).
3. Guárdalo: lo pegarás en `TELEGRAM_BOT_TOKEN` en el `.env` (o desde la UI tras el primer login).

### 0.6 (Opcional) Dominio público + DNS — solo para producción

Si vas a desplegar accesible desde internet con HTTPS:

- Un dominio con un registro **A** apuntando a la IP pública del servidor (p.ej. `linkanvil.tu-dominio.com → 1.2.3.4`).
- Puertos 80 y 443 accesibles públicamente (Let's Encrypt necesita el 80 para validar).
- Un email para las notificaciones de Let's Encrypt (`ACME_EMAIL` en `.env`).

### 0.7 (Solo Windows / macOS estricto) Resolución de `*.localhost`

La mayoría de Linux (con `systemd-resolved`) y macOS 11+ resuelven `*.localhost → 127.0.0.1` automáticamente. **En Windows o en macOS antiguos**, añade a tu archivo hosts:

- Windows: `C:\Windows\System32\drivers\etc\hosts`
- macOS/Linux: `/etc/hosts`

```
127.0.0.1  cerebro.localhost ingest.localhost n8n.localhost rabbitmq.localhost
127.0.0.1  grafana.localhost prometheus.localhost qdrant.localhost jaeger.localhost
127.0.0.1  llm.localhost traefik.localhost
```

Sin esto, los enlaces `http://<servicio>.localhost` de la [FASE 5](#fase-5-acceso-a-la-plataforma-y-dashboards) no funcionarán.

### Checklist de FASE 0

Antes de seguir, comprueba que tienes:

- [ ] Acceso SSH al servidor con `sudo` (o terminal local).
- [ ] Internet en el servidor + puertos 80 abiertos en el firewall cloud (si aplica).
- [ ] Al menos 1 API key de un proveedor LLM con embeddings compatibles.
- [ ] (Opcional) `tskey-auth-...` de Tailscale si vas a usar Telegram.
- [ ] (Opcional) Token de @BotFather si vas a usar Telegram.
- [ ] (Producción) Dominio con DNS apuntando al servidor + puerto 443 abierto.

Con esto cubierto, sigue a la FASE 1.

---

## FASE 1: Preparación del Entorno

### 1.1 Software indispensable

::: tip ATAJO Debian 12 / Ubuntu 22.04+
**Ejecuta `sudo bash install-host.sh` y salta directamente a la [sección 1.3](#13-clonar-el-repositorio)**. El script instala automáticamente Docker + Compose, git, Python 3, jq, openssl y python3-cryptography. Idempotente: puedes re-ejecutarlo sin riesgo.

```bash
git clone https://github.com/sylfG/linkanvil && cd linkanvil
sudo bash install-host.sh
```

Solo continúa leyendo esta sección si trabajas en **macOS o Windows** (no soportados por `install-host.sh`), o si quieres entender qué se instala y por qué.
:::

Instala las siguientes herramientas antes de continuar. Las **runtime obligatorias** son `git` y Docker. El resto solo son necesarias para los MCP servers de Claude Code (Node.js, uv).

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
Se utilizan para automatizar el despliegue de la infraestructura local, empaquetando los **22 servicios long-running** del stack (más **5 contenedores one-shot de inicialización** — `cerebro-migrate`, `qdrant-init`, `cerebro-seed-demo`, `bootstrap-demo-keys`, `n8n-bootstrap` — y el sidecar opcional `tailscale-funnel`, que solo arranca con el perfil `telegram`) en contenedores aislados.
A través del fichero declarativo de Compose, permite levantar e interconectar todos los servicios dentro de la red privada `cerebro-net` y gestionar el ciclo de vida con un solo comando, garantizando que la plataforma funcione exactamente igual en cualquier entorno de desarrollo o producción.

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

**Node.js + npx**: lo necesita Claude Code para los MCP servers escritos en JavaScript/TypeScript (n8n, Slack, GitHub, etc.). No es runtime del stack — todos los servicios productivos corren en contenedores Docker.

**uv / uvx**: usados por Claude Code para lanzar MCP servers en Python. No participan en el runtime del stack.

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

Se usa como herramienta de diagnóstico y auditoría del sistema antes de ponerlo en marcha.

LinkAnvil incluye un smoke test escrito en Python puro que actúa como un "médico virtual" del stack. Sus propiedades:

* **Verificación de servicios (*Healthcheck*):** se conecta uno a uno con los contenedores activos para confirmar que responden correctamente y que la red interna funciona sin fallos.
* **Independencia absoluta (Uso de `stdlib`):** está programado utilizando únicamente la **biblioteca estándar** de Python, así que puede ejecutarse inmediatamente después de instalar el intérprete. No necesita descargar librerías de internet ni instalar paquetes externos (`pip`, `requests`, etc.), lo que garantiza que la prueba de diagnóstico sea ligera, rápida y 100% segura.
* **Compatibilidad de sintaxis:** requiere la versión 3.9 o superior.

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

**uv / uvx** es un gestor de paquetes de Python ultrarrápido que usa Claude Code para lanzar los MCP servers escritos en Python (Qdrant, Fetch, Docker, Prometheus, etc.). Su velocidad y gestión aislada garantizan que los MCP servers arranquen en milisegundos y libres de conflictos. No interviene en el runtime del stack.

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

El repositorio contiene la configuración declarativa de los contenedores del stack (Traefik, Redis, Grafana, PostgreSQL, LiteLLM, Qdrant, etc.) y los scripts operativos.

---

## FASE 2: Proveedores LLM y `.env`

El núcleo de extracción y vectorización funciona gracias a **LiteLLM**, que actúa de gateway frente a 1 o N proveedores LLM. El bootstrap te deja elegir cuáles activar y en qué orden — el primero es el primario, el resto entra en la cadena de fallback estricta.

### Proveedores soportados de fábrica

| Proveedor | Chat | Embeddings | Dim | Registro |
|---|:---:|:---:|:---:|---|
| **nvidia** | ✅ | ✅ | 1024 | https://build.nvidia.com/explore/discover |
| **openai** | ✅ | ✅ | 1536 | https://platform.openai.com/api-keys |
| **anthropic** | ✅ | ❌ | — | https://console.anthropic.com/settings/keys |
| **gemini** | ✅ | ✅ | 768 | https://aistudio.google.com/apikey |
| **mistral** | ✅ | ✅ | 1024 | https://console.mistral.ai/api-keys/ |
| **cohere** | ✅ | ✅ | 1024 | https://dashboard.cohere.com/api-keys |
| **groq** | ✅ | ❌ | — | https://console.groq.com/keys |
| **xai** | ✅ | ❌ | — | https://console.x.ai/ |
| **openrouter** | ✅ | ❌ | — | https://openrouter.ai/keys |

Catálogo completo (modelos lite/pro por proveedor, endpoint, etc.): [`infra/litellm/providers.yaml`](../../infra/litellm/providers.yaml). Para añadir un proveedor nuevo basta con añadir una entry — `bootstrap-env.sh` y `render-litellm-config.py` la descubren.

### Opción A: dejar que `up.sh` haga el trabajo (recomendado)

`bash up.sh` detecta si falta el `.env` (lo crea desde `.env.example`), auto-genera todos los secretos (passwords, JWT, clave Fernet) y luego te pregunta interactivamente:

1. **Qué proveedores activar** — CSV en orden de prioridad. Ejemplo: `nvidia,anthropic,openai`.
2. **API key de cada uno** — solo para los marcados.
3. **Dimensión de embeddings** — default 1024. Si la cambias y ya existían colecciones en Qdrant, se recrean (destructivo).
4. **Proveedor de embeddings** — `auto` elige el primero de la lista que tenga embeddings con la dim correcta.

El script renderiza `infra/litellm/config.yaml` con el `model_list` y las reglas `router_settings.fallbacks` correctas y reinicia LiteLLM si la config cambió.

Para cambiar la lista de proveedores más tarde: edita `.env` y vuelve a ejecutar `bash up.sh`, o invoca `bash up.sh --reconfigure-llm` para que te abra otra vez el prompt.

### Opción B: edición manual del `.env`

Si prefieres revisar línea a línea o estás en un entorno donde `up.sh` no aplica:

1. Copia la plantilla (este fichero **NUNCA** debe subirse a un repositorio público):

   ```bash
   cp .env.example .env
   ```

2. Edita `.env` y rellena al menos:

   * **Proveedores LLM**. Lista priorizada + API keys correspondientes:
     ```env
     LLM_PROVIDERS_PRIORITY=nvidia,anthropic
     EMBEDDINGS_PROVIDER=auto
     EMBEDDINGS_DIM=1024
     NVIDIA_API_KEY=nvapi-xxxxxx...
     ANTHROPIC_API_KEY=sk-ant-xxxxxx...
     ```

   * **`LLM_KEYS_ENCRYPTION_KEY`** (*CRÍTICA*). Clave Fernet que cifra las BYOK keys en la BD. `cerebro-api` no arranca si está vacía. Genera con:

     ```bash
     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```

   * **`LITELLM_MASTER_KEY`** — token administrativo del gateway. El default `sk-cerebro-master-key-CHANGE_ME` no es production-safe.

   * **Passwords del stack** — placeholders `_CHANGE_ME` (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `RABBITMQ_PASS`, `N8N_PASSWORD`, `GRAFANA_PASSWORD`) deben cambiarse a valores aleatorios.

   * **`JWT_SECRET`** — `python3 -c "import secrets; print(secrets.token_hex(32))"`.

   * **`AUDIT_CRON_TOKEN`** — `openssl rand -hex 32`.

3. Renderiza el config de LiteLLM y arranca:

   ```bash
   python3 scripts/render-litellm-config.py
   docker compose up -d
   ```

> Las variables `DEMO_KEY_LITE`, `DEMO_KEY_EMBEDDINGS` y `DEMO_KEY_PRO` son virtual-keys de LiteLLM para el usuario demo. Si las dejas vacías y `SEED_DEMO=true`, el one-shot `bootstrap-demo-keys` las genera automáticamente contra LiteLLM en el primer arranque y las guarda cifradas con Fernet en la BD del usuario demo.

### Cómo funciona el fallback en LiteLLM

El renderizador genera, por cada proveedor activo, una entrada `model_name: cerebro-lite__<provider>` y `cerebro-pro__<provider>` en `model_list`. El primer proveedor de la lista también recibe el alias canónico `cerebro-lite`/`cerebro-pro` — es lo que el código de la app invoca. En `router_settings.fallbacks` se declara la cadena estricta: si el primario falla más de N veces (config: `allowed_fails`), LiteLLM lo saca temporalmente del pool y prueba el siguiente. Es determinista — no round-robin entre proveedores.

Para embeddings no hay fallback: se elige un solo proveedor compatible con la dimensión configurada. Mezclar dimensiones rompería Qdrant.

---

## FASE 3: Despliegue e Inicialización (Bootstrapping)

Con las llaves configuradas, levanta el stack. Hay dos vías equivalentes:

```bash
# Opción A — recomendada: wrapper idempotente con healthchecks y mensajes claros
bash up.sh

# Opción B — directo con compose (sin completar .env automáticamente y sin esperar healthchecks)
docker compose up -d
```

`up.sh` se encarga de:

1. Validar que Docker está disponible.
2. Completar el `.env` (passwords, JWT, Fernet) si hay placeholders pendientes — invoca [`scripts/bootstrap-env.sh`](../../scripts/bootstrap-env.sh).
3. Sincronizar el hash de RabbitMQ en `infra/rabbitmq/definitions.json` con la nueva `RABBITMQ_PASS`.
4. `docker compose pull` + `build` + `up -d`.
5. Esperar healthchecks de los servicios runtime (timeout 240s) vía [`scripts/wait-healthy.sh`](../../scripts/wait-healthy.sh).
6. Imprimir endpoints y credenciales demo.

El stack arranca **22 contenedores long-running** + **5 one-shot de inicialización** (`cerebro-migrate`, `qdrant-init`, `cerebro-seed-demo`, `bootstrap-demo-keys`, `n8n-bootstrap`). Estos últimos terminan en `Exited (0)` — es lo esperado: son init containers, no fallos.

> **Nota:** la primera ejecución tarda varios minutos (build de las 4 imágenes locales + pull de las 16 externas). Puedes seguir los logs con `docker compose logs -f`.

> **Nota sobre versiones**: todas las imágenes externas están pinneadas a versión exacta o a digest SHA-256, salvo `tailscale/tailscale:stable` (opcional, sidecar de Telegram). Esto garantiza reproducibilidad entre entornos.

---

## FASE 3b: Migraciones de Schema (automáticas)

Las migraciones SQL se aplican **automáticamente** mediante el servicio one-shot **`cerebro-migrate`** cada vez que ejecutas `docker compose up -d`. La API no arranca hasta que el runner termina con éxito: `cerebro-api` declara `depends_on: cerebro-migrate` con `condition: service_completed_successfully`.

El runner es **idempotente**: lee secuencialmente los archivos SQL versionados del proyecto, registra cada versión aplicada en la tabla `cerebro.schema_migrations` y solo ejecuta las pendientes. Si no hay novedades, imprime `schema is up to date` y sale con código 0.

Solo necesitas ejecutarlo manualmente si:

1. Has añadido una migración nueva sin reiniciar el stack.
2. Estás depurando el runner.

```bash
# Dentro del contenedor (recomendado — sin prerrequisitos en el host):
docker compose run --rm cerebro-migrate

# O desde el host (requiere psql instalado y puerto 5432 expuesto):
bash scripts/migrate.sh
```

Para añadir una migración nueva, crea un fichero SQL nuevo en el directorio de migraciones del proyecto siguiendo el patrón de numeración existente (`0002_nueva_columna.sql`, `0003_...`, etc.). En el próximo arranque del stack se aplicará automáticamente, o fuerza la aplicación inmediata con:

```bash
docker compose run --rm cerebro-migrate
```

---

## FASE 3c: Resetear el Stack Completo

El script `bash reset.sh` devuelve el entorno a un estado totalmente limpio. Destruye todos los contenedores, borra los volúmenes de datos en disco y vuelve a construir las imágenes locales desde cero. Útil para solucionar problemas de corrupción o cambios estructurales mayores — **perderás toda la información guardada**.

```bash
bash reset.sh                  # reset completo (borra volúmenes + re-build)
bash reset.sh --keep-images    # omite el pull/rebuild de imágenes externas (más rápido)
```

El script:

1. Para y elimina todos los contenedores del proyecto.
2. Elimina los volúmenes nombrados (`postgres-data`, `qdrant-data`, etc.).
3. Borra las imágenes construidas localmente (`linkanvil-*`).
4. Opcionalmente borra las imágenes externas para forzar pull fresco (salvo `--keep-images`).
5. Regenera el hash de RabbitMQ en `definitions.json` ([`scripts/regen-rabbitmq-hash.sh`](../../scripts/regen-rabbitmq-hash.sh)).
6. `docker compose pull` + `build --no-cache` + `up -d`.
7. Espera healthchecks ([`scripts/wait-healthy.sh`](../../scripts/wait-healthy.sh)).

> **Diferencia con `up.sh`**: `up.sh` es idempotente (se puede correr N veces sin destruir nada). `reset.sh` es destructivo (borra estado para empezar de cero). En el día a día usa `up.sh`; reserva `reset.sh` para problemas serios o cambios mayores en la BD.

---

## FASE 4: Verificación del Ecosistema

Hay tres comandos de verificación, en orden creciente de profundidad.

### a) Healthcheck rápido del stack

```bash
make health
# o bien:
bash scripts/wait-healthy.sh --once
```

Imprime el estado healthcheck de los 19 servicios runtime. Devuelve exit 0 si todos están `healthy`, 1 si alguno está `unhealthy` o `missing`.

### b) Listado completo de contenedores

```bash
docker compose ps        # solo runtime
docker compose ps -a     # incluye los 5 one-shot Exited(0)
make ps-oneshot          # estado de los init containers
```

Los workers (`cerebro-scraper`, `cerebro-embedder`, `cerebro-outbox`, `cerebro-notifier`) se marcan healthy una vez que su heartbeat en Redis está activo (hasta 60s tras arrancar).

### c) Smoke test inter-servicio

```bash
python3 infra/test_health.py
```

Script en Python puro (solo stdlib, sin dependencias) que verifica conectividad real entre servicios — no solo el estado del contenedor. Comprueba endpoints HTTP, colas RabbitMQ, conexiones a Postgres/Redis/Qdrant y targets de Prometheus.

### Logs en tiempo real

```bash
docker compose logs -f cerebro-api cerebro-ingestion cerebro-scraper
```

---

## FASE 5: Acceso a la Plataforma y Dashboards

### Usuario demo pre-cargado

Si `SEED_DEMO=true` (default del bootstrap interactivo), el stack viene con un usuario demo listo para entrar sin registrarte:

- **Email interno**: `demo@linkanvil.io` (gestionado por el sistema)
- **Recursos**: 18 ejemplos pre-cargados (recetas, papers, repos, eventos pasados/futuros) cubriendo todos los estados del ciclo de vida.

::: warning Acceso al demo: usa el botón, no `/auth/login`
El acceso al demo es vía el botón **"Probar demo"** en la landing del frontend ([http://localhost:3001](http://localhost:3001)), que abre una sesión efímera con la virtual-key auto-provisionada por `bootstrap-demo-keys`.

`POST /auth/login` con `demo@linkanvil.io` devuelve **403 `demo_use_dedicated_endpoint`** **por diseño** — no es un fallo de instalación: la cuenta demo no permite login directo para evitar que un usuario público se quede con su sesión.
:::

Si pusiste `SEED_DEMO=false`, regístrate normalmente desde la pantalla de login.

### Endpoints del stack

| Servicio | URL | Credenciales |
|:--- |:--- |:--- |
| **App Principal** | [http://localhost:3001](http://localhost:3001) | demo o registro |
| **API Backend** | [http://localhost:8001/docs](http://localhost:8001/docs) | JWT (Swagger UI) |
| **Ingestion API** | [http://ingest.localhost/health](http://ingest.localhost/health) (vía Traefik) | Libre |
| **LiteLLM Gateway** | [http://localhost:4000](http://localhost:4000) | `LITELLM_MASTER_KEY` en `.env` |
| **Orquestador (n8n)** | [http://localhost:5678](http://localhost:5678) | `N8N_USER` / `N8N_PASSWORD` en `.env` |
| **Colas (RabbitMQ)** | [http://localhost:15672](http://localhost:15672) | `RABBITMQ_USER` / `RABBITMQ_PASS` en `.env` |
| **Métricas (Grafana)** | [http://localhost:3000](http://localhost:3000) | `GRAFANA_USER` / `GRAFANA_PASSWORD` en `.env` |
| **Trazas Visuales (Jaeger)** | [http://localhost:16686](http://localhost:16686) | Libre |
| **BD Vectorial (Qdrant)** | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Libre |
| **API Gateway (Traefik)** | [http://localhost:8080](http://localhost:8080) | Libre (solo local) |

> Para recuperar las credenciales auto-generadas:
> ```bash
> grep -E "^(N8N_PASSWORD|GRAFANA_PASSWORD|RABBITMQ_PASS|LITELLM_MASTER_KEY)=" .env
> ```

### Explorar la API: Swagger UI

La API de LinkAnvil expone documentación interactiva **OpenAPI/Swagger** en [http://localhost:8001/docs](http://localhost:8001/docs). Es la referencia canónica y siempre está sincronizada con el código (se genera automáticamente desde los modelos Pydantic y los handlers FastAPI).

Lo que puedes hacer desde Swagger:

- **Ver todos los endpoints** agrupados por área (`auth`, `recursos`, `chat`, `admin`, etc.) con su método HTTP, ruta, parámetros y respuestas tipadas.
- **Probar endpoints en vivo** ("Try it out" → "Execute") sin escribir un `curl`. Útil para descubrir errores de validación, ver el shape exacto de la respuesta y entender los códigos de estado.
- **Inspeccionar los modelos de datos** (sección "Schemas" al final) — qué campos lleva un `IngestionRequest`, qué devuelve `LoginResponse`, etc.
- **Autenticarte para endpoints protegidos**: pulsa el candado 🔒 arriba a la derecha, pega un JWT obtenido con `POST /auth/login` (usuario registrado, no demo), y Swagger lo añadirá a todas las peticiones posteriores como header `Authorization: Bearer ...`.

> El esquema OpenAPI bruto está en [http://localhost:8001/openapi.json](http://localhost:8001/openapi.json) — útil para generar clientes con `openapi-generator`, importar a Postman/Insomnia, o auditar la superficie pública de la API.

**Para la API de ingestión** (que no expone puertos al host, va por Traefik), no hay Swagger separado: el único endpoint público es `POST /ingest` y está descrito en la sección [Tu primera ingesta](#tu-primera-ingesta) más abajo.

### Primer login en n8n y Grafana

Si es la primera vez que abres estas UIs, **el bootstrap ya creó las credenciales** — no te pide registrar ningún usuario nuevo, solo introducir las del `.env`. Si tras introducirlas Grafana te pide cambiar la contraseña, puedes hacerlo en su UI sin tocar el `.env` (Grafana mantiene su propia BD).

### Tu primera ingesta

Entra en `http://localhost:3001` con el usuario demo y envía una URL desde la interfaz. Alternativamente, puedes probar directamente la Ingestion API.

> ⚠ El servicio `cerebro-ingestion` **no expone puertos al host** — solo es accesible vía Traefik (PathPrefix `/ingest` o Host header `ingest.localhost`). Un `curl http://localhost:8000/ingest` desde el host falla con *connection refused*.

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

- Dominio apuntando a la IP del servidor.
- Variables de entorno de producción en `.env` (o Docker secrets).
- Docker Engine en el servidor.

### 6.2 Levantar con el overlay de producción

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

El overlay de producción activa:

- **TLS automático** con Let's Encrypt (certResolver Traefik).
- **Redirección HTTP→HTTPS** en todos los routers públicos.
- **Puertos internos cerrados**: Postgres, Redis, RabbitMQ y Qdrant no exponen puertos al host — solo accesibles dentro de `cerebro-net`.
- **Docker secrets**: `JWT_SECRET_FILE` y `POSTGRES_PASSWORD_FILE` leen de `/run/secrets/` en lugar de variables de entorno.

### 6.3 Variables críticas para producción

```env
# En .env de producción (los secretos van en Docker secrets, no aquí)
JWT_SECRET=<clave-aleatoria-fuerte>      # mín 32 chars; genera con: python3 -c "import secrets; print(secrets.token_hex(32))"
PUBLIC_HOSTNAME=tu-dominio.com           # Traefik construye rutas desde aquí
ACME_EMAIL=admin@tu-dominio.com          # Let's Encrypt notifications
LLM_KEYS_ENCRYPTION_KEY=<clave-fernet>   # cifrado de las BYOK keys (obligatorio)
```

Consulta la guía de producción del proyecto para Docker secrets, configuración de firewall y backups programados.

### 6.4 Webhooks de Telegram (Tailscale Funnel)

El bot de Telegram requiere una URL HTTPS pública a la que Telegram pueda entregar los mensajes. Si trabajas en local detrás de un router doméstico, no la tienes por defecto. Solución gratis y persistente: **Tailscale Funnel** como sidecar de Docker. Sobrevive a `docker compose down/up` y a reconstrucciones del entorno.

> **Prerrequisitos** (cubiertos en [FASE 0.4](#04-opcional-cuenta-de-tailscale-solo-si-quieres-webhooks-de-telegram) y [FASE 0.5](#05-opcional-bot-de-telegram)): cuenta Tailscale con HTTPS activo + `tskey-auth-...` reusable + token del bot de @BotFather.

#### Atajo automatizado

```bash
bash up.sh --with-telegram
```

El script te pedirá:

1. `TS_AUTHKEY` — el `tskey-auth-...` de Tailscale (generado en FASE 0.4).
2. (Resto del flujo de proveedores LLM como siempre).

Y arrancará el stack con el perfil `telegram` activo. Tras eso solo te quedan los pasos 3-5 de abajo (descubrir URL pública, conectar bot).

#### Variables que entran en `.env`

```env
TS_AUTHKEY=tskey-auth-XXXXXXXXXXXXXXXXXX   # generado en FASE 0.4
PUBLIC_INGESTION_URL=                       # se rellena tras el primer arranque
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...        # token de @BotFather (FASE 0.5)
```

`TELEGRAM_BOT_TOKEN` también puede dejarse vacío en el `.env` y configurarse desde la UI tras el primer login (más cómodo si quieres rotarlo sin tocar archivos).

#### Configuración manual (paso a paso)

Si prefieres no usar `--with-telegram` o necesitas reconfigurar:

1. **Edita `.env`** con las variables de arriba.

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

#### Conectar el bot a la app

Si ya pusiste `TELEGRAM_BOT_TOKEN` en `.env` antes de arrancar, el webhook se registra automáticamente. Si no:

1. En la UI (`http://localhost:3001`), ve a `/profile`, pega el token del bot y guarda.
2. La respuesta del `PUT /profile/telegram` debe incluir `webhook_url` apuntando al subdominio público.
3. Manda una URL al bot desde tu cuenta de Telegram — debería aparecer en tu KB tras unos segundos.

#### Persistencia entre rebuilds

El estado del nodo Tailscale vive en el volumen `cerebro-tailscale-state`. Mientras no lo borres con `docker volume rm`, la URL pública es la misma siempre. Tras un `docker compose down && up`, todo arranca y Telegram sigue entregando mensajes a la misma dirección sin reconfigurar nada.

> **Aviso**: Tailscale Funnel solo expone los puertos públicos 443/8443/10000 (LinkAnvil usa 443) y solo responde mientras `cerebro-tailscale` esté corriendo.

### 6.5 Backup automático

```bash
bash scripts/backup.sh
```

Genera `pg_dump` gzipado del schema `cerebro` y snapshots de Qdrant.

Para la retención automática, exporta `BACKUP_RETENTION_DAYS` (entero, default `7`) como variable de entorno o añádela a tu `.env`. Esta variable no figura en la plantilla `.env.example`, así que debes añadirla manualmente. Alternativa equivalente sin tocar `.env`:

```bash
BACKUP_RETENTION_DAYS=14 bash scripts/backup.sh
```

*¡Felicidades! LinkAnvil está operativo.* Consulta la [Arquitectura](./4-arquitectura.md) para entender las decisiones de diseño, o las [Épicas y Features](./Extractor_de_Requisitos/1_epics_and_features.md) para el roadmap del producto.
