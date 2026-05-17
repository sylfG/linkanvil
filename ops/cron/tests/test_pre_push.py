"""Integration tests for .githooks/pre-push main() exit codes."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Load the pre-push hook as a module despite lacking .py extension
_HOOK_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".githooks" / "pre-push"


def _load_hook():
    loader = importlib.machinery.SourceFileLoader("pre_push", str(_HOOK_PATH))
    spec = importlib.util.spec_from_loader("pre_push", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


pre_push = _load_hook()


class TestPrePushMain(unittest.TestCase):

    def _run_main(self, diff: str, response) -> int:
        """Run main() and return the exit code."""
        with patch.object(pre_push, "get_diff", return_value=diff), \
             patch.object(pre_push, "load_prompt", return_value="prompt"), \
             patch("litellm_client.call", return_value=response):
            try:
                pre_push.main()
                return 0
            except SystemExit as exc:
                return int(exc.code) if exc.code is not None else 0

    def test_no_diff_exits_zero(self):
        code = self._run_main("", None)
        self.assertEqual(code, 0)

    def test_clean_response_exits_zero(self):
        code = self._run_main("diff content", "CLEAN")
        self.assertEqual(code, 0)

    def test_critical_finding_exits_one(self):
        code = self._run_main("diff content", "CRITICAL src/api/auth.py:42 JWT missing tenant_id")
        self.assertEqual(code, 1)

    def test_litellm_unavailable_exits_zero(self):
        """Fail-open: LiteLLM None should never block the push."""
        code = self._run_main("diff content", None)
        self.assertEqual(code, 0)

    def test_high_finding_exits_zero(self):
        code = self._run_main("diff content", "HIGH src/api/main.py:10 missing rate limit")
        self.assertEqual(code, 0)

    def test_mixed_findings_with_critical_exits_one(self):
        response = "HIGH src/api/main.py:10 issue\nCRITICAL src/api/auth.py:5 bad auth"
        code = self._run_main("diff content", response)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
