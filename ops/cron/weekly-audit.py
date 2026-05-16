#!/usr/bin/env python3
"""
weekly-audit.py: auditoría semanal de seguridad vía LiteLLM.

Guarda el resultado en ops/sessions/audit-YYYY-MM-DD.md.
Usa hash cache para saltar la llamada a LiteLLM si los archivos no cambiaron.

Instalar como cron: ver ops/cron/weekly-audit.cron
Ejecutar manualmente: python3 ops/cron/weekly-audit.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# Add ops/cron to path for litellm_client
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
import litellm_client  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum characters read per audit file.
# Derived from cerebro-lite context budget (4 files × 4k = 16k chars + prompt).
MAX_CHARS_PER_FILE = 4_000

AUDIT_FILES = [
    "src/api/main.py",
    "src/api/auth.py",
    "src/ingestion/main.py",
    "src/scraper/worker.py",
]

_PROMPT_FILE_NAME = "weekly-audit.txt"


# ---------------------------------------------------------------------------
# Repo root discovery
# ---------------------------------------------------------------------------

def find_repo_root() -> Path:
    """
    Return the git repository root via git rev-parse.

    Works in both normal repos and git worktrees.
    Raises RuntimeError if not inside a git repo.
    """
    try:
        root = Path(
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("No se encontró un repositorio git") from exc
    return root


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------

def read_audit_files(repo_root: Path) -> dict[str, str]:
    """
    Read AUDIT_FILES and return {relative_path: content}.

    Files exceeding MAX_CHARS_PER_FILE are truncated with a visible marker
    so the model knows it received partial content.
    Missing files are recorded as '*archivo no encontrado*'.
    """
    result: dict[str, str] = {}
    for rel_path in AUDIT_FILES:
        full = repo_root / rel_path
        if full.exists():
            raw = full.read_text(encoding="utf-8", errors="replace")
            if len(raw) > MAX_CHARS_PER_FILE:
                content = raw[:MAX_CHARS_PER_FILE] + "\n... [TRUNCADO]\n"
            else:
                content = raw
            result[rel_path] = content
        else:
            result[rel_path] = "*archivo no encontrado*"
    return result


def format_code_block(files: dict[str, str]) -> str:
    """Format file contents as fenced markdown code blocks."""
    parts = []
    for path, content in files.items():
        if content == "*archivo no encontrado*":
            parts.append(f"### {path}\n*archivo no encontrado*")
        else:
            parts.append(f"### {path}\n```python\n{content}\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Hash cache (skip LiteLLM if files unchanged)
# ---------------------------------------------------------------------------

def _compute_hash(files: dict[str, str]) -> str:
    """SHA-256 of all file paths and contents (sorted for determinism)."""
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode())
        h.update(files[path].encode())
    return h.hexdigest()


def _load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache_path: Path, file_hash: str, report_path: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"hash": file_hash, "last_report": report_path})
    )


def load_cache_if_hit(cache_path: Path, file_hash: str) -> dict | None:
    """
    Return the cache dict if the stored hash matches file_hash (cache hit).
    Returns None on cache miss or read error.

    Single disk read — callers reuse the returned dict directly.
    """
    cache = _load_cache(cache_path)
    if cache.get("hash") == file_hash:
        return cache
    return None


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompt(prompts_dir: Path, code_block: str) -> str:
    """
    Load prompt template from ops/prompts/weekly-audit.txt and inject code.
    Exits with error if the prompt file is missing — no silent fallback.
    """
    prompt_file = prompts_dir / _PROMPT_FILE_NAME
    try:
        template = prompt_file.read_text(encoding="utf-8")
    except OSError:
        print(
            f"❌ Prompt file not found: {prompt_file}\n"
            "   Ensure ops/prompts/weekly-audit.txt exists in the repository.",
            file=sys.stderr,
        )
        sys.exit(1)
    return template.replace("{code}", code_block)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(sessions_dir: Path, content: str) -> Path:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    out_path = sessions_dir / f"audit-{today}.md"
    report = f"# Auditoría semanal — {today}\n\n{content}\n"
    out_path.write_text(report, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        repo_root = find_repo_root()
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)

    sessions_dir = repo_root / "ops" / "sessions"
    cache_path = sessions_dir / ".audit-cache.json"
    prompts_dir = repo_root / "ops" / "prompts"

    # Read source files and compute hash
    files = read_audit_files(repo_root)
    file_hash = _compute_hash(files)

    # Single disk read — reuse cache dict if hit
    cached = load_cache_if_hit(cache_path, file_hash)
    if cached is not None:
        print("⏭️  Sin cambios desde el último análisis — omitiendo LiteLLM")
        print(f"   Último reporte: {cached.get('last_report', 'desconocido')}")
        sys.exit(0)

    # Build prompt and call LiteLLM
    code_block = format_code_block(files)
    prompt = load_prompt(prompts_dir, code_block)

    print("🔍 Llamando a LiteLLM para auditoría semanal...")
    result = litellm_client.call(prompt, max_tokens=1_200, timeout=60)

    if result is None:
        error_msg = "ERROR: LiteLLM no disponible — ver log para detalles"
        out_path = write_report(sessions_dir, error_msg)
        print(f"⚠️  Reporte de error guardado en {out_path}")
        sys.exit(1)

    # Write report and update cache
    out_path = write_report(sessions_dir, result)
    _save_cache(cache_path, file_hash, str(out_path))

    print(f"✅ Reporte guardado en {out_path}")


if __name__ == "__main__":
    main()
