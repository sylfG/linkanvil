#!/usr/bin/env python3
"""
weekly-audit.py: auditoría semanal de seguridad vía LiteLLM.
Lee los archivos críticos del repo y envía el contexto al modelo.
Guarda el resultado en ops/sessions/audit-YYYY-MM-DD.md

Instalar como cron: ver ops/cron/weekly-audit.cron
Ejecutar manualmente: python3 ops/cron/weekly-audit.py
"""
import json, os, sys, urllib.request
from datetime import date
from pathlib import Path

# ops/cron/weekly-audit.py → repo root es tres niveles arriba
REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000")
MODEL       = os.getenv("LITELLM_MODEL", "cerebro-lite")

AUDIT_FILES = [
    "src/api/main.py",
    "src/api/auth.py",
    "src/ingestion/worker.py",
    "src/scraper/worker.py",
]


def read_files() -> str:
    parts = []
    for rel_path in AUDIT_FILES:
        full = REPO_ROOT / rel_path
        if not full.exists():
            parts.append(f"### {rel_path}\n*archivo no encontrado*")
            continue
        content = full.read_text(encoding="utf-8", errors="replace")[:4000]
        parts.append(f"### {rel_path}\n```python\n{content}\n```")
    return "\n\n".join(parts)


def call_litellm(prompt: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1200,
        "temperature": 0,
    }).encode()

    req = urllib.request.Request(
        f"{LITELLM_URL}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
        return data["choices"][0]["message"]["content"].strip()


def main() -> None:
    today     = date.today().isoformat()
    out_dir   = REPO_ROOT / "ops" / "sessions"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path  = out_dir / f"audit-{today}.md"

    print(f"📂 Leyendo archivos desde {REPO_ROOT}...")
    code = read_files()

    prompt = (
        "Eres el security-reviewer de linkanvil (FastAPI multi-tenant RAG).\n"
        "Audita estos archivos críticos:\n\n"
        f"{code}\n\n"
        "Busca:\n"
        "1. JWT: ¿se valida tenant_id en todos los endpoints? ¿endpoints sin auth?\n"
        "2. asyncpg: ¿todas las queries usan $1, $2...? ¿f-strings con datos de usuario?\n"
        "3. SSRF: ¿URLs de usuario pasan validación antes de ser scrapeadas?\n"
        "4. Pydantic: ¿campos sin validación que llegan a la DB?\n"
        "5. Rate limiting: ¿endpoints POST sin rate limit?\n"
        "6. Outbox: ¿notificaciones directas que saltan outbox_eventos?\n\n"
        "Formato: markdown con ## Resumen Ejecutivo, ## Hallazgos (CRITICAL/HIGH/MEDIUM), "
        "## Acciones recomendadas.\n"
        "Solo hallazgos reales con >80% confianza."
    )

    print("🤖 Llamando a LiteLLM...")
    try:
        result = call_litellm(prompt)
    except Exception as e:
        result = f"ERROR: LiteLLM no disponible — {e}"
        print(f"⚠️  {result}", file=sys.stderr)

    report = f"# Auditoría semanal — {today}\n\n{result}\n"
    out_path.write_text(report, encoding="utf-8")
    print(f"✅ Reporte guardado en {out_path}")


if __name__ == "__main__":
    main()
