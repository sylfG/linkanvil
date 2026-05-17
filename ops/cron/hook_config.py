"""Configuration constants for the pre-push git hook."""
from __future__ import annotations

WATCH_PATHS: list[str] = [
    "src/api/",
    "src/data/",
    "src/scraper/",
    "src/ingestion/",
]

# Derived from cerebro-lite context budget (~8k chars leaves room for the prompt).
MAX_DIFF_CHARS: int = 8_000

# Refs probed (in order) to find a merge-base for new-branch pushes.
# Override here if your org uses `trunk`, `develop`, etc.
NEW_BRANCH_BASE_REFS: tuple[str, ...] = ("origin/main", "origin/master", "main", "master")
