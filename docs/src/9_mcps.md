<div align="center">
  <img src="../public/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="../public/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


## 🔌 MCPs para Claude Code

</div>


Los 11 MCP servers del proyecto están configurados en .mcp.json (versionado en el repo). Claude Code los carga automáticamente en modo project gracias a .claude/settings.json.

### Prerrequisitos de runtime (host)

# Node.js 20 LTS (para MCPs npx)

curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -

sudo apt-get install -y nodejs

# uv (para MCPs uvx: Qdrant, Fetch, Docker, Prometheus)

curl -LsSf https://astral.sh/uv/install.sh | sh
### Arrancar Claude con el entorno del proyecto

Para que Claude vea las credenciales del .env:


cd ~/linkanvil
set -a && source .env && set +a
claude
Dentro de Claude: /mcp muestra el estado de cada servidor.



### MCPs incluidos



| Servidor | Propósito | Runtime | Credencial necesaria |
|---|---|---|---|
| **postgres** | Consultar schema, outbox, RLS | npx | — (usa POSTGRES_* del .env) |
| **qdrant** | Colecciones vectoriales, búsqueda RAG | uvx | — |
| **n8n** | Workflows, ejecuciones, credenciales | npx | N8N_API_KEY |
| **redis** | Sesiones, caché LiteLLM, TTLs | npx | — (usa REDIS_PASSWORD) |
| **github** | Issues, PRs, workflows CI | npx | GITHUB_TOKEN |
| **fetch** | Scraping de URLs, validar ingesta | uvx | — |
| **brave-search** | Búsqueda web desde Claude | npx | BRAVE_API_KEY (free) |
| **sequential-thinking** | Razonamiento estructurado | npx | — |
| **docker** | ps, logs, inspect de cerebro-* | uvx | — |
| **telegram** | Bot (pendiente roadmap paso 2) | npx | TELEGRAM_BOT_TOKEN |
| **prometheus** | Consultar métricas, alertas DLQ | uvx | — |

Las claves vacías (N8N_API_KEY, GITHUB_TOKEN, etc.) se añaden al .env local; ver .env.example para las instrucciones de obtención.