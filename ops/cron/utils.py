"""
Shared utilities for linkanvil ops scripts.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path


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
                timeout=5,
            ).decode().strip()
        )
    except subprocess.SubprocessError as exc:
        raise RuntimeError("No se encontro un repositorio git") from exc
    return root


def read_template(template_path: Path) -> str:
    """Read a template file as text. Raises FileNotFoundError if missing."""
    try:
        return template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Prompt file not found: {template_path}") from exc


def render_template(template: str, replacements: dict[str, str]) -> str:
    """
    Substitute placeholders in a template string in a single pass.

    Uses a compiled regex with alternation so the template is scanned exactly
    once regardless of placeholder count: O(N+M) versus the chained-replace
    O(N*M) pattern. Raises ValueError if any declared placeholder never appears.
    Pure transformation -- no I/O, separable from read_template for testing.
    """
    if not replacements:
        return template
    pattern = re.compile("|".join(re.escape(k) for k in replacements))
    seen: set[str] = set()

    def _sub(match: re.Match[str]) -> str:
        key = match.group(0)
        seen.add(key)
        return replacements[key]

    result = pattern.sub(_sub, template)
    missing = set(replacements) - seen
    if missing:
        raise ValueError(f"Placeholder(s) {sorted(missing)!r} not found in template")
    return result


def load_prompt(template_path: Path, replacements: dict[str, str]) -> str:
    """Convenience: read_template + render_template in one call."""
    return render_template(read_template(template_path), replacements)


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content to path atomically via tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding=encoding, dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    os.replace(tmp_path, path)
