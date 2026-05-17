"""Integration tests for .githooks/pre-push main() exit codes."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import tempfile
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

from _helpers import run_capture_exit  # noqa: E402


class TestPrePushMain(unittest.TestCase):

    def _run_main(self, diff: str, response) -> int:
        """Run main() and return the exit code."""
        with patch.object(pre_push, "get_diff", return_value=diff), \
             patch.object(pre_push, "build_prompt", return_value="prompt"), \
             patch.object(pre_push.litellm_client, "send_prompt", return_value=response):
            return run_capture_exit(pre_push.main)

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

    def test_missing_prompt_file_exits_one(self):
        """FileNotFoundError from build_prompt must exit 1, not silently continue."""
        with patch.object(pre_push, "get_diff", return_value="some diff"), \
             patch.object(pre_push, "build_prompt", side_effect=FileNotFoundError("template missing")):
            try:
                pre_push.main()
                code = 0
            except SystemExit as exc:
                code = int(exc.code) if exc.code is not None else 0
        self.assertEqual(code, 1)


class TestBuildPromptPrePush(unittest.TestCase):

    def test_raises_file_not_found_when_template_missing(self):
        original = pre_push._PROMPT_FILE
        try:
            pre_push._PROMPT_FILE = Path("/nonexistent/prompt.txt")
            with self.assertRaises(FileNotFoundError):
                pre_push.build_prompt("some diff")
        finally:
            pre_push._PROMPT_FILE = original

    def test_truncation_adds_marker_when_diff_too_long(self):
        from hook_config import MAX_DIFF_CHARS
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("analyze:\n{diff}")
            prompt_path = Path(f.name)
        original = pre_push._PROMPT_FILE
        try:
            pre_push._PROMPT_FILE = prompt_path
            big_diff = "x" * (MAX_DIFF_CHARS + 100)
            result = pre_push.build_prompt(big_diff)
            self.assertIn("TRUNCADO", result)
        finally:
            pre_push._PROMPT_FILE = original
            prompt_path.unlink(missing_ok=True)

    def test_no_truncation_marker_when_diff_within_limit(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("{diff}")
            prompt_path = Path(f.name)
        original = pre_push._PROMPT_FILE
        try:
            pre_push._PROMPT_FILE = prompt_path
            result = pre_push.build_prompt("small diff")
            self.assertNotIn("TRUNCADO", result)
        finally:
            pre_push._PROMPT_FILE = original
            prompt_path.unlink(missing_ok=True)


class TestGetDiff(unittest.TestCase):

    def test_returns_diff_from_head(self):
        mock_result = MagicMock(returncode=0, stdout="diff content\n")
        with patch.object(pre_push.subprocess, "run", return_value=mock_result):
            diff = pre_push.get_diff()
        self.assertEqual(diff, "diff content")

    def test_falls_back_to_cached_when_head_returns_empty(self):
        """Initial commit: HEAD~1 doesn't exist (returncode=1), falls back to --cached."""
        first_call = MagicMock(returncode=1, stdout="")
        second_call = MagicMock(returncode=0, stdout="staged diff\n")
        with patch.object(pre_push.subprocess, "run", side_effect=[first_call, second_call]):
            diff = pre_push.get_diff()
        self.assertEqual(diff, "staged diff")

    def test_returns_empty_string_on_exception(self):
        """Fail-open: subprocess errors must never raise out of get_diff."""
        with patch.object(pre_push.subprocess, "run", side_effect=OSError("not found")):
            diff = pre_push.get_diff()
        self.assertEqual(diff, "")

    def test_returns_empty_when_no_watched_files_changed(self):
        mock_result = MagicMock(returncode=0, stdout="   \n")
        with patch.object(pre_push.subprocess, "run", return_value=mock_result):
            diff = pre_push.get_diff()
        self.assertEqual(diff, "")

    def test_get_diff_with_explicit_empty_stdin_uses_fallback(self):
        """stdin_lines=[] must trigger fallback path, not multi-commit path."""
        mock_result = MagicMock(returncode=0, stdout="fallback diff\n")
        with patch.object(pre_push.subprocess, "run", return_value=mock_result):
            diff = pre_push.get_diff(stdin_lines=[])
        self.assertEqual(diff, "fallback diff")


class TestParsePushRefs(unittest.TestCase):
    """Verifies pre-push stdin protocol parsing for multi-commit pushes."""

    _ZERO = "0" * 40

    def test_parses_normal_branch_update(self):
        lines = ["refs/heads/main abc123 refs/heads/main def456\n"]
        refs = pre_push.parse_push_refs(lines)
        self.assertEqual(refs, [("def456", "abc123")])

    def test_skips_branch_deletion(self):
        """When local_sha is all zeros, that ref is a deletion -- skip it."""
        lines = [f"refs/heads/feat {self._ZERO} refs/heads/feat def456\n"]
        self.assertEqual(pre_push.parse_push_refs(lines), [])

    def test_handles_new_branch_push(self):
        """remote_sha == zeros indicates a new branch; must still be parsed."""
        lines = [f"refs/heads/feat abc123 refs/heads/feat {self._ZERO}\n"]
        refs = pre_push.parse_push_refs(lines)
        self.assertEqual(refs, [(self._ZERO, "abc123")])

    def test_ignores_malformed_lines(self):
        lines = ["only three parts\n", "refs/heads/main abc refs/heads/main def\n"]
        refs = pre_push.parse_push_refs(lines)
        self.assertEqual(refs, [("def", "abc")])

    def test_parses_multiple_refs(self):
        lines = [
            "refs/heads/main aaa refs/heads/main bbb\n",
            "refs/heads/dev  ccc refs/heads/dev  ddd\n",
        ]
        refs = pre_push.parse_push_refs(lines)
        self.assertEqual(refs, [("bbb", "aaa"), ("ddd", "ccc")])


class TestGetDiffMultiCommit(unittest.TestCase):
    """Verifies get_diff aggregates over multiple refs when stdin is provided."""

    def test_aggregates_diff_across_refs(self):
        """Two refs being pushed -> two `git diff` calls, results concatenated."""
        responses = [
            MagicMock(returncode=0, stdout="diff for ref A\n"),
            MagicMock(returncode=0, stdout="diff for ref B\n"),
        ]
        stdin = [
            "refs/heads/main rem_a refs/heads/main loc_a\n",
            "refs/heads/dev  rem_b refs/heads/dev  loc_b\n",
        ]
        with patch.object(pre_push.subprocess, "run", side_effect=responses):
            diff = pre_push.get_diff(stdin_lines=stdin)
        self.assertIn("diff for ref A", diff)
        self.assertIn("diff for ref B", diff)

    def test_falls_back_when_all_refs_are_deletions(self):
        """All-deletion stdin yields no refs -> use fallback path."""
        zero = "0" * 40
        stdin = [f"refs/heads/feat {zero} refs/heads/feat def456\n"]
        mock_result = MagicMock(returncode=0, stdout="fallback content\n")
        with patch.object(pre_push.subprocess, "run", return_value=mock_result):
            diff = pre_push.get_diff(stdin_lines=stdin)
        self.assertEqual(diff, "fallback content")

    def test_skips_failed_ranges_keeps_others(self):
        """If one `git diff` fails (rc!=0), its empty result is dropped but others survive."""
        responses = [
            MagicMock(returncode=1, stdout=""),
            MagicMock(returncode=0, stdout="surviving diff\n"),
        ]
        stdin = [
            "refs/heads/main rem_a refs/heads/main loc_a\n",
            "refs/heads/dev  rem_b refs/heads/dev  loc_b\n",
        ]
        with patch.object(pre_push.subprocess, "run", side_effect=responses):
            diff = pre_push.get_diff(stdin_lines=stdin)
        self.assertEqual(diff, "surviving diff")


class TestDiffRangeNewBranch(unittest.TestCase):
    """Verifies new-branch base resolution (merge-base probing)."""

    _ZERO = "0" * 40

    def test_uses_merge_base_when_found(self):
        """For a new-branch push, _diff_range probes upstream refs; first success short-circuits."""
        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["git", "merge-base"]:
                return MagicMock(returncode=0, stdout="base_sha\n")
            if cmd[:2] == ["git", "diff"]:
                return MagicMock(returncode=0, stdout="new branch diff\n")
            raise AssertionError(f"unexpected git invocation: {cmd}")
        with patch.object(pre_push.subprocess, "run", side_effect=fake_run):
            result = pre_push._diff_range(self._ZERO, "local_sha")
        self.assertEqual(result, "new branch diff")

    def test_falls_back_to_parent_when_no_merge_base(self):
        """When merge-base fails for every candidate ref, falls back to local_sha~1..local_sha.

        Decoupled from len(NEW_BRANCH_BASE_REFS) by dispatching on the git subcommand,
        not on the order of subprocess.run() invocations.
        """
        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["git", "merge-base"]:
                return MagicMock(returncode=1, stdout="")
            if cmd[:2] == ["git", "diff"]:
                return MagicMock(returncode=0, stdout="parent fallback diff\n")
            raise AssertionError(f"unexpected git invocation: {cmd}")
        with patch.object(pre_push.subprocess, "run", side_effect=fake_run):
            result = pre_push._diff_range(self._ZERO, "local_sha")
        self.assertEqual(result, "parent fallback diff")


if __name__ == "__main__":
    unittest.main()
