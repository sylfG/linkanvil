"""Configuration constants for the weekly audit cron."""
from __future__ import annotations

AUDIT_FILES: list[str] = [
    "src/api/main.py",
    "src/api/auth.py",
    "src/ingestion/main.py",
    "src/scraper/worker.py",
]

# Derived from cerebro-lite context budget (4 files x 4k = 16k chars + prompt).
MAX_CHARS_PER_FILE: int = 4_000
