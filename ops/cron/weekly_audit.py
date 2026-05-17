#!/usr/bin/env python3
"""
weekly-audit.py: auditoria semanal de seguridad via LiteLLM.

Guarda el resultado en ops/sessions/audit-YYYY-MM-DD.md.
Cache de dos niveles para evitar I/O y llamadas a LiteLLM cuando nada ha cambiado:
  1. stat_sig (mtime + size): cheap-check, evita leer archivos
  2. content_hash: defensive-check, evita LiteLLM si el contenido es el mismo
     a pesar de un cambio de mtime (e.g., `touch` sin edicion real).

Instalar como cron: ver ops/cron/weekly-audit.cron
Ejecutar manualmente: python3 ops/cron/weekly-audit.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

import litellm_client  # noqa: E402
from audit_config import AUDIT_FILES, MAX_CHARS_PER_FILE  # noqa: E402
from utils import atomic_write, find_repo_root, load_prompt  # noqa: E402
import paths  # noqa: E402

_PROMPT_FILE = paths.weekly_audit_prompt()


def read_audit_files(repo_root: Path) -> dict[str, str | None]:
    """
    Read AUDIT_FILES and return {relative_path: content | None}.

    Files exceeding MAX_CHARS_PER_FILE are truncated with a visible marker.
    Missing files are recorded as None.
    """
    result: dict[str, str | None] = {}
    for rel_path in AUDIT_FILES:
        full = repo_root / rel_path
        if full.exists():
            with full.open(encoding="utf-8", errors="replace") as fh:
                content = fh.read(MAX_CHARS_PER_FILE + 1)
            if len(content) > MAX_CHARS_PER_FILE:
                content = content[:MAX_CHARS_PER_FILE] + "\n... [TRUNCADO]\n"
                print(f"warning  {rel_path} truncado a {MAX_CHARS_PER_FILE} chars", file=sys.stderr)
            result[rel_path] = content
        else:
            result[rel_path] = None
    return result


def format_code_block(files: dict[str, str | None]) -> str:
    """Format file contents as fenced markdown code blocks."""
    parts = []
    for path, content in files.items():
        if content is None:
            parts.append(f"### {path}\n*archivo no encontrado*")
        else:
            parts.append(f"### {path}\n```python\n{content}\n```")
    return "\n\n".join(parts)


def _compute_stat_signature(repo_root: Path, rel_paths: list[str]) -> str:
    """
    Cheap-check hash over (path, mtime_ns, size) for each audit file.

    Computed without reading file contents: only `stat()` calls.
    Missing files contribute a MISSING sentinel so deletion/creation changes
    the signature deterministically.
    """
    h = hashlib.sha256()
    for path in sorted(rel_paths):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        try:
            st = (repo_root / path).stat()
            h.update(str(st.st_mtime_ns).encode("ascii"))
            h.update(b"\x00")
            h.update(str(st.st_size).encode("ascii"))
        except OSError:
            h.update(b"MISSING")
        h.update(b"\x00")
    return h.hexdigest()


def _compute_hash(files: dict[str, str | None]) -> str:
    """
    SHA-256 of all file paths and contents (sorted for determinism).

    Uses null-byte separators and a MISSING sentinel so that a None value
    and an empty string never produce the same hash contribution.
    """
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        content = files[path]
        if content is None:
            h.update(b"\x00MISSING\x00")
        else:
            h.update(content.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def read_cache(cache_path: Path) -> dict | None:
    """Return parsed cache dict, or None if file is missing or corrupted."""
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_cache(
    cache_path: Path,
    stat_sig: str,
    content_hash: str,
    report_path: str,
) -> None:
    """
    Persist the two-tier cache entry atomically.

    Stores stat_sig (cheap-check) and content_hash (defensive-check) together
    so subsequent runs can short-circuit at the appropriate level.
    """
    atomic_write(cache_path, json.dumps({
        "stat_sig": stat_sig,
        "content_hash": content_hash,
        "last_report": report_path,
    }))


def write_report(sessions_dir: Path, content: str) -> Path:
    """Write audit report atomically to avoid partial files on abrupt termination."""
    today = date.today().isoformat()
    out_path = sessions_dir / f"audit-{today}.md"
    report = f"# Auditoria semanal -- {today}\n\n{content}\n"
    atomic_write(out_path, report)
    return out_path


def main() -> None:
    try:
        repo_root = find_repo_root()
    except RuntimeError as exc:
        print(f"error  {exc}", file=sys.stderr)
        sys.exit(1)

    sessions_dir = paths.sessions_dir(repo_root)
    cache_path = paths.audit_cache(repo_root)

    # Tier 1: stat_sig cheap-check (no file reads)
    stat_sig = _compute_stat_signature(repo_root, AUDIT_FILES)
    cache = read_cache(cache_path)

    if cache is not None and cache.get("stat_sig") == stat_sig:
        print("info  Sin cambios de stat -- omitiendo I/O y LiteLLM")
        print(f"   Ultimo reporte: {cache.get('last_report', 'desconocido')}")
        sys.exit(0)

    # Tier 2: read files and check content_hash (mtime changed; was it real?)
    files = read_audit_files(repo_root)
    content_hash = _compute_hash(files)

    if cache is not None and cache.get("content_hash") == content_hash:
        # Stat changed (e.g., touch, checkout) but content is identical:
        # refresh stat_sig in cache so next run skips even the read step.
        save_cache(cache_path, stat_sig, content_hash, cache.get("last_report", ""))
        print("info  Contenido sin cambios reales -- omitiendo LiteLLM")
        sys.exit(0)

    code_block = format_code_block(files)
    try:
        prompt = load_prompt(_PROMPT_FILE, {"{code}": code_block})
    except (FileNotFoundError, ValueError) as exc:
        print(f"error  {exc}\n   Ensure ops/prompts/weekly-audit.txt exists.", file=sys.stderr)
        sys.exit(1)

    print("info  Llamando a LiteLLM para auditoria semanal...")
    result = litellm_client.send_prompt(prompt, max_tokens=1_200, timeout=60)

    if result is None:
        error_msg = "ERROR: LiteLLM no disponible -- ver log para detalles"
        out_path = write_report(sessions_dir, error_msg)
        save_cache(cache_path, stat_sig, content_hash, str(out_path))
        print(f"warning  Reporte de error guardado en {out_path}")
        sys.exit(1)

    out_path = write_report(sessions_dir, result)
    save_cache(cache_path, stat_sig, content_hash, str(out_path))

    print(f"ok  Reporte guardado en {out_path}")


if __name__ == "__main__":
    main()
