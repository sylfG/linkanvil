"""
Centralized filesystem paths for linkanvil cron + hooks.

All "knowledge of where things are" lives here, so individual scripts
do not duplicate `ops/prompts/...` or `ops/sessions/...` path construction.
"""
from __future__ import annotations

from pathlib import Path

_CRON_DIR = Path(__file__).resolve().parent  # ops/cron/
_OPS_DIR = _CRON_DIR.parent                  # ops/
_STATIC_REPO_ROOT = _OPS_DIR.parent          # repo root (resolved at import)


def prompts_dir() -> Path:
    """Directory holding prompt templates: <repo>/ops/prompts/"""
    return _OPS_DIR / "prompts"


def weekly_audit_prompt() -> Path:
    return prompts_dir() / "weekly-audit.txt"


def pre_push_prompt() -> Path:
    return prompts_dir() / "pre-push.txt"


def sessions_dir(repo_root: Path | None = None) -> Path:
    """
    Directory holding audit reports: <repo_root>/ops/sessions/

    repo_root defaults to the statically resolved repo root (suitable for
    invocation under git worktree where Path(__file__) is stable). Pass an
    explicit repo_root when running under cron with an arbitrary CWD.
    """
    return (repo_root or _STATIC_REPO_ROOT) / "ops" / "sessions"


def audit_cache(repo_root: Path | None = None) -> Path:
    """Path to the two-tier cache file used by weekly_audit.py."""
    return sessions_dir(repo_root) / ".audit-cache.json"
