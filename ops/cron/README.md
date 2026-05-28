# ops/cron — git hooks + auditoría semanal

Sistema de análisis de código basado en LiteLLM, sin dependencia de
GitHub Actions ni claves de Anthropic. Toda la IA se enruta a través
del LiteLLM gateway local (`http://localhost:4000`, modelo `cerebro-lite`
por defecto).

Dos puntos de entrada:

| Componente | Cuándo corre | Qué hace |
|---|---|---|
| `.githooks/pre-push` | Antes de cada `git push` | Analiza el diff multi-commit, bloquea si hay findings CRITICAL |
| `ops/cron/weekly_audit.py` | Cron semanal (lunes 09:00 UTC) | Audita archivos críticos, escribe reporte en `ops/sessions/audit-YYYY-MM-DD.md` |

## Setup (una vez por clone)

```bash
# 1. Activar los git hooks
git config core.hooksPath .githooks

# 2. Instalar el cron de auditoría semanal
crontab ops/cron/weekly-audit.cron
```

Variables de entorno opcionales (defaults sensatos):

```bash
export LITELLM_URL=http://localhost:4000
export LITELLM_MODEL=cerebro-lite
```

## Comportamiento del pre-push

- **Multi-commit**: parsea stdin del protocolo `<local-ref> <local-sha> <remote-ref> <remote-sha>`
  e itera **todos** los refs del push, agregando los diffs por rango
  `<remote-sha>..<local-sha>`. Pushes de nuevas branches resuelven base
  vía `merge-base` contra `origin/main`, `origin/master`, etc.
- **Fail-open**: si LiteLLM no responde, el push **NO se bloquea**.
  La política es no convertir un fallo de infraestructura en un fallo
  de deploy.
- **Bypass explícito**: `git push --no-verify` para saltarlo.

## Comportamiento del weekly audit

Caché de dos niveles para evitar trabajo redundante:

1. **Tier 1 (cheap-check)** — `stat_sig` hashea `(path, mtime_ns, size)`
   sin leer contenidos. Si coincide con la última corrida, salida `0`
   sin ningún `read()` ni llamada a LiteLLM.
2. **Tier 2 (defensive-check)** — si el stat cambió, lee contenidos y
   verifica `content_hash`. Si el contenido es idéntico (ej. `touch`
   sin edit real), refresca el `stat_sig` en caché y salta LiteLLM.

El cache vive en `ops/sessions/.audit-cache.json`. Si LiteLLM falla,
el cache **también se actualiza** para evitar que el cron martillee
el endpoint en cada tick.

## Tests

```bash
python3 -m pytest ops/cron/tests/ -v
```

Cobertura: parsing, fail-open en todos los modos de fallo de red,
serialización del cache, hashing determinista, protocolo pre-push y
flujo end-to-end de `main()`.
