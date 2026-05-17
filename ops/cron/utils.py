"""
Shared utilities for linkanvil ops scripts.
"""
from __future__ import annotations

import subprocess
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
            ).decode().strip()
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("No se encontro un repositorio git") from exc
    return root
