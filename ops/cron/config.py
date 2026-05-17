"""
Shared project configuration for linkanvil ops scripts.

Single source of truth for paths and size limits used across
git hooks and cron scripts.
"""
from __future__ import annotations

# Paths monitored by the pre-push hook.
WATCH_PATHS: list[str] = [
    "src/api/",
    "src/data/",
    "src/scraper/",
    "src/ingestion/",
]

# Files included in the weekly security audit.
AUDIT_FILES: list[str] = [
    "src/api/main.py",
    "src/api/auth.py",
    "src/ingestion/main.py",
    "src/scraper/worker.py",
]

# Maximum diff characters sent to the pre-push model.
# Derived from cerebro-lite context budget (~8k chars leaves room for the prompt).
MAX_DIFF_CHARS: int = 8_000

# Maximum characters read per audit file.
# Derived from cerebro-lite context budget (4 files x 4k = 16k chars + prompt).
MAX_CHARS_PER_FILE: int = 4_000
