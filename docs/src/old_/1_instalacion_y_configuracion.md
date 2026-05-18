<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# 🚀 Tutorial Interactivo: Instalación y Configuración

</div>


Bienvenidos a la guía práctica para inicializar LinkAnvil, tu backend soberano de conocimiento estructurado. Este tutorial paso a paso está diseñado para instalar la plataforma en local o tu cloud personal, entender el flujo de datos y enviar tu primer enlace de conocimiento para asegurar que todo funciona.

---

## FASE 1: Preparación del Entorno

### 1.1 Software indispensable

Instala las siguientes herramientas antes de continuar. Todas son necesarias para levantar el stack y los MCP servers de Claude Code.

---

#### Git

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

::: code-group

```bash [Linux (Debian/Ubuntu)]
sudo apt-get install -y curl
```

```bash [macOS]
# Incluido por defecto en macOS
curl --version
```

:::

---

#### Python 3.9 o superior

Necesario para ejecutar `infra/test_health.py`. No requiere paquetes externos (solo stdlib).

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

Necesario para los MCP servers distribuidos via `npx` (PostgreSQL, n8n, Redis, GitHub, Brave Search, Sequential Thinking, Telegram).

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

Necesario para los MCP servers distribuidos via `uvx` (Qdrant, Fetch, Docker, Prometheus).

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
git clone https://github.com/sylfg/linkanvil.git
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

   * **Contraseñas del resto del Stack**: Modifica a placer las contraseñas predefinidas en el fichero de las bases de datos (RabbitMQ, Postgre, Redis, Grafana...).

     ```env
     POSTGRES_PASSWORD=cerebro_db_pass
     RABBITMQ_PASS=cerebro_pass
     # ...
     ```

---

## FASE 3: Despliegue e Inicialización (Bootstrapping)

Ahora que las llaves están configuradas, Docker Compose descargará las imágenes, creará la red interna `cerebro-net`, levantará los 21 contenedores y aplicará el `init.sql` (que crea el schema `cerebro` y todas las tablas en Postgres).

```bash
docker compose up -d
```

> **NOTA:** Tardará varios minutos en la primera ejecución. Puedes seguir los logs con `docker compose logs -f`.

---

## FASE 3b: Aplicar Migraciones de Schema

El sistema incluye un runner de migraciones shell para mantener el schema `cerebro` actualizado sin necesidad de Alembic ni dependencias Python adicionales.

```bash
bash scripts/migrate.sh
```

**Primera ejecución:** aplica `0001_baseline.sql` que registra el estado inicial del schema. Si el stack acaba de arrancar con `docker compose up -d`, el `init.sql` ya habrá creado las tablas — la migración baseline verifica su existencia y registra la versión.

**Ejecuciones posteriores:** idempotente — detecta las versiones ya aplicadas y solo ejecuta las nuevas. Si no hay migraciones pendientes, imprime `schema is up to date` y sale con código 0.

Para añadir una migración nueva:
```bash
# crear el archivo en infra/postgres/migrations/
echo "ALTER TABLE cerebro.recursos ADD COLUMN nueva_col TEXT;" \
  > infra/postgres/migrations/0002_nueva_columna.sql

# aplicar
bash scripts/migrate.sh
```

---

## FASE 3c: Resetear el Stack Completo

Para volver a un estado completamente limpio (útil en desarrollo o tras un cambio de configuración mayor), usa el script `reset.sh`:

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

Verifica que todos los contenedores están sanos:

```bash
docker compose ps
```

Todos los servicios con healthcheck deben mostrar `(healthy)`. Los workers (`cerebro-scraper`, `cerebro-embedder`, `cerebro-outbox`) se marcarán como healthy una vez que su heartbeat Redis esté activo (puede tardar hasta 60 segundos).

Para ver los logs en tiempo real:
```bash
docker compose logs -f cerebro-api cerebro-ingestion cerebro-scraper
```

---

## FASE 5: Acceso a la Plataforma y Dashboards

| Servicio | URL | Credenciales (`.env`) |
|:--- |:--- |:--- |
| **App Principal** | [http://localhost:3001](http://localhost:3001) | Registro en la propia app |
| **API Backend** | [http://localhost:8001/docs](http://localhost:8001/docs) | JWT (Swagger UI) |
| **Orquestador (n8n)** | [http://localhost:5678](http://localhost:5678) | `N8N_USER` & `N8N_PASSWORD` |
| **Colas (RabbitMQ)** | [http://localhost:15672](http://localhost:15672) | `RABBITMQ_USER` & `RABBITMQ_PASS` |
| **Métricas (Grafana)** | [http://localhost:3000](http://localhost:3000) | `GRAFANA_USER` & `GRAFANA_PASSWORD` |
| **Trazas Visuales (Jaeger)** | [http://localhost:16686](http://localhost:16686) | Libre |
| **BD Vectorial (Qdrant)** | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Libre |
| **API Gateway (Traefik)** | [http://localhost:8080](http://localhost:8080) | Libre (solo local) |

> **Tip:** Añade las entradas `*.localhost` en tu `/etc/hosts` para acceder mediante subdominios: `cerebro.localhost`, `ingest.localhost`, `n8n.localhost`, etc. Traefik enruta automáticamente según el `Host` header.

### Tu primera ingesta

Crea una cuenta en `http://localhost:3001`, inicia sesión y envía una URL desde la interfaz. Alternativamente, puedes probar directamente la Ingestion API:

```bash
curl -X POST http://localhost:8000/ingest \
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
# En .env o como Docker secrets
SESSION_COOKIE_SECURE=true          # requiere HTTPS para la cookie de sesión
JWT_SECRET=<clave-aleatoria-fuerte> # mínimo 32 caracteres, sin predeterminados
DOMAIN=tu-dominio.com               # Traefik construye rutas desde aquí
ACME_EMAIL=admin@tu-dominio.com     # Let's Encrypt notifications
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

Genera `pg_dump` gzipado del schema `cerebro` y snapshots de Qdrant. Configura `BACKUP_RETENTION_DAYS` en `.env` para la retención automática.

*¡Felicidades! LinkAnvil está operativo.* Consulta la [Arquitectura](./6_arquitectura.md) para entender las decisiones de diseño, o las [Épicas y Features](./1_epics_and_features.md) para el roadmap del producto.
