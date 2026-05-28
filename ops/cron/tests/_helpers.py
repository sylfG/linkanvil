"""
Shared test helpers for cron/hook tests.

Keeps the SystemExit-to-int translation in one place so future changes to
how scripts signal failure only ripple through this single function.
"""
from __future__ import annotations

from typing import Callable


def run_capture_exit(main_fn: Callable[[], None]) -> int:
    """
    Invoke a main() callable and return the exit code.

    Returns 0 if main() completes without raising SystemExit.
    """
    try:
        main_fn()
        return 0
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
