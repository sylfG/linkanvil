"""
pytest configuration -- consolidates sys.path setup so individual test
modules can import production code via `from utils import ...` without
manipulating sys.path themselves. Also exposes _helpers.py to tests.
"""
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_CRON_DIR = _TESTS_DIR.parent

sys.path.insert(0, str(_CRON_DIR))   # production modules
sys.path.insert(0, str(_TESTS_DIR))  # _helpers.py
