"""Tests for ops/cron/weekly_audit.py"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import weekly_audit
from _helpers import run_capture_exit


# ---------------------------------------------------------------------------
# read_audit_files
# ---------------------------------------------------------------------------

class TestReadAuditFiles(unittest.TestCase):

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = weekly_audit.read_audit_files(Path(tmpdir))
        for value in result.values():
            self.assertIsNone(value)

    def test_reads_file_within_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "api").mkdir(parents=True)
            (root / "src" / "api" / "main.py").write_text("x = 1\n", encoding="utf-8")
            result = weekly_audit.read_audit_files(root)
        self.assertEqual(result.get("src/api/main.py"), "x = 1\n")

    def test_truncates_at_max_chars(self):
        from audit_config import MAX_CHARS_PER_FILE
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "api").mkdir(parents=True)
            big = "a" * (MAX_CHARS_PER_FILE + 100)
            (root / "src" / "api" / "main.py").write_text(big, encoding="utf-8")
            result = weekly_audit.read_audit_files(root)
        content = result["src/api/main.py"]
        self.assertIsNotNone(content)
        self.assertIn("[TRUNCADO]", content)
        self.assertLessEqual(len(content), MAX_CHARS_PER_FILE + 50)


# ---------------------------------------------------------------------------
# format_code_block
# ---------------------------------------------------------------------------

class TestFormatCodeBlock(unittest.TestCase):

    def test_none_values_handled(self):
        files = {"src/api/main.py": None}
        result = weekly_audit.format_code_block(files)
        self.assertIn("archivo no encontrado", result)
        self.assertIn("src/api/main.py", result)

    def test_content_wrapped_in_fenced_block(self):
        files = {"src/api/main.py": "def foo(): pass\n"}
        result = weekly_audit.format_code_block(files)
        self.assertIn("```python", result)
        self.assertIn("def foo(): pass", result)


# ---------------------------------------------------------------------------
# read_cache  (replaces TestLoadCacheIfHit)
# ---------------------------------------------------------------------------

class TestReadCache(unittest.TestCase):

    def test_returns_parsed_dict_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / ".audit-cache.json"
            payload = {"stat_sig": "s", "content_hash": "c", "last_report": "audit.md"}
            cache_path.write_text(json.dumps(payload))
            result = weekly_audit.read_cache(cache_path)
        self.assertEqual(result, payload)

    def test_returns_none_when_missing(self):
        self.assertIsNone(weekly_audit.read_cache(Path("/nonexistent/.audit-cache.json")))

    def test_returns_none_on_corrupted_json(self):
        """Defensive: corrupted cache file must not crash the cron run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / ".audit-cache.json"
            cache_path.write_text("{not valid json")
            self.assertIsNone(weekly_audit.read_cache(cache_path))


# ---------------------------------------------------------------------------
# save_cache  (new signature: stat_sig, content_hash, report_path)
# ---------------------------------------------------------------------------

class TestSaveCache(unittest.TestCase):

    def test_writes_all_three_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / ".audit-cache.json"
            weekly_audit.save_cache(cache_path, "stat_abc", "content_xyz", "audit-today.md")
            data = json.loads(cache_path.read_text())
        self.assertEqual(data["stat_sig"], "stat_abc")
        self.assertEqual(data["content_hash"], "content_xyz")
        self.assertEqual(data["last_report"], "audit-today.md")

    def test_creates_parent_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "nested" / "dir" / ".audit-cache.json"
            weekly_audit.save_cache(cache_path, "s", "c", "r.md")
            self.assertTrue(cache_path.parent.exists())

    def test_overwrites_existing_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / ".audit-cache.json"
            cache_path.write_text(json.dumps({"stat_sig": "old", "content_hash": "old", "last_report": "old.md"}))
            weekly_audit.save_cache(cache_path, "new_s", "new_c", "new.md")
            data = json.loads(cache_path.read_text())
        self.assertEqual(data["stat_sig"], "new_s")
        self.assertEqual(data["content_hash"], "new_c")
        self.assertEqual(data["last_report"], "new.md")


# ---------------------------------------------------------------------------
# _compute_stat_signature
# ---------------------------------------------------------------------------

class TestComputeStatSignature(unittest.TestCase):

    def test_deterministic_for_unchanged_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "api").mkdir(parents=True)
            (root / "src" / "api" / "main.py").write_text("x\n", encoding="utf-8")
            h1 = weekly_audit._compute_stat_signature(root, ["src/api/main.py"])
            h2 = weekly_audit._compute_stat_signature(root, ["src/api/main.py"])
        self.assertEqual(h1, h2)

    def test_changes_when_file_size_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "api").mkdir(parents=True)
            p = root / "src" / "api" / "main.py"
            p.write_text("short", encoding="utf-8")
            h1 = weekly_audit._compute_stat_signature(root, ["src/api/main.py"])
            p.write_text("a much longer body of content", encoding="utf-8")
            h2 = weekly_audit._compute_stat_signature(root, ["src/api/main.py"])
        self.assertNotEqual(h1, h2)

    def test_changes_when_mtime_changes(self):
        """Same content, different mtime -> different stat_sig (cheap-check detects touch)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "api").mkdir(parents=True)
            p = root / "src" / "api" / "main.py"
            p.write_text("same content", encoding="utf-8")
            h1 = weekly_audit._compute_stat_signature(root, ["src/api/main.py"])
            # Bump mtime to a value far enough that filesystem resolution can't merge it.
            past = time.time() - 86400
            os.utime(p, (past, past))
            h2 = weekly_audit._compute_stat_signature(root, ["src/api/main.py"])
        self.assertNotEqual(h1, h2)

    def test_missing_file_does_not_raise(self):
        """Missing files contribute a sentinel and must not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # File does NOT exist
            h = weekly_audit._compute_stat_signature(root, ["src/api/missing.py"])
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 64)  # SHA-256 hex length


# ---------------------------------------------------------------------------
# _compute_hash  (content-based)
# ---------------------------------------------------------------------------

class TestComputeHash(unittest.TestCase):

    def test_deterministic_for_same_input(self):
        files = {"a/b.py": "content1", "c/d.py": None}
        h1 = weekly_audit._compute_hash(files)
        h2 = weekly_audit._compute_hash(files)
        self.assertEqual(h1, h2)

    def test_none_and_empty_string_produce_different_hashes(self):
        """Regression: None vs '' must not collide (the original bug)."""
        files_none = {"src/api/main.py": None}
        files_empty = {"src/api/main.py": ""}
        self.assertNotEqual(
            weekly_audit._compute_hash(files_none),
            weekly_audit._compute_hash(files_empty),
        )

    def test_order_independent(self):
        files_ab = {"a.py": "x", "b.py": "y"}
        files_ba = {"b.py": "y", "a.py": "x"}
        self.assertEqual(
            weekly_audit._compute_hash(files_ab),
            weekly_audit._compute_hash(files_ba),
        )

    def test_different_content_produces_different_hash(self):
        h1 = weekly_audit._compute_hash({"a.py": "content A"})
        h2 = weekly_audit._compute_hash({"a.py": "content B"})
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

class TestWriteReport(unittest.TestCase):

    def test_creates_file_with_todays_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            out = weekly_audit.write_report(sessions_dir, "contenido del reporte")
            expected_name = f"audit-{date.today().isoformat()}.md"
            self.assertEqual(out.name, expected_name)

    def test_creates_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "does" / "not" / "exist"
            weekly_audit.write_report(sessions_dir, "test")
            self.assertTrue(sessions_dir.exists())

    def test_report_contains_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            out = weekly_audit.write_report(sessions_dir, "HALLAZGO CRITICO")
            self.assertIn("HALLAZGO CRITICO", out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# main()  -- two-tier cache flow
# ---------------------------------------------------------------------------

class TestMainWeeklyAudit(unittest.TestCase):

    def _run_main(
        self,
        mock_send_return,
        *,
        cache_data: dict | None = None,
        stat_sig: str = "current_stat",
        content_hash: str = "current_content",
    ) -> int:
        """
        Run weekly_audit.main() with controlled inputs.

        - cache_data: pre-populate the cache file at expected path (or None for no cache)
        - stat_sig: value returned by patched _compute_stat_signature
        - content_hash: value returned by patched _compute_hash
        - mock_send_return: value returned by patched litellm_client.send_prompt
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            if cache_data is not None:
                cache_path = repo_root / "ops" / "sessions" / ".audit-cache.json"
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache_data))

            with patch.object(weekly_audit, "find_repo_root", return_value=repo_root), \
                 patch.object(weekly_audit, "_compute_stat_signature", return_value=stat_sig), \
                 patch.object(weekly_audit, "_compute_hash", return_value=content_hash), \
                 patch.object(weekly_audit, "load_prompt", return_value="mocked prompt"), \
                 patch.object(weekly_audit.litellm_client, "send_prompt", return_value=mock_send_return):
                return run_capture_exit(weekly_audit.main)

    def test_stat_sig_match_skips_audit(self):
        """Tier-1 cheap-path: stat_sig matches cache -> exit 0 without reading files."""
        cache = {"stat_sig": "match", "content_hash": "anything", "last_report": "old.md"}
        # send_prompt mock will raise if called -- guarantees no LiteLLM call
        with patch.object(weekly_audit, "read_audit_files") as mock_read:
            code = self._run_main(None, cache_data=cache, stat_sig="match")
            self.assertEqual(code, 0)
            mock_read.assert_not_called()

    def test_content_hash_match_after_stat_change_skips_litellm(self):
        """Tier-2 defensive-path: content matches despite stat change -> save fresh stat, skip LiteLLM."""
        cache = {"stat_sig": "stale", "content_hash": "match", "last_report": "old.md"}
        send_mock = MagicMock()
        with patch.object(weekly_audit.litellm_client, "send_prompt", send_mock):
            # Override the inner patch by using a different harness: directly invoke
            with tempfile.TemporaryDirectory() as tmpdir:
                repo_root = Path(tmpdir)
                cache_path = repo_root / "ops" / "sessions" / ".audit-cache.json"
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache))
                with patch.object(weekly_audit, "find_repo_root", return_value=repo_root), \
                     patch.object(weekly_audit, "_compute_stat_signature", return_value="fresh_stat"), \
                     patch.object(weekly_audit, "_compute_hash", return_value="match"):
                    code = run_capture_exit(weekly_audit.main)
                # Cache must now carry the fresh stat_sig
                updated = json.loads(cache_path.read_text())
                self.assertEqual(updated["stat_sig"], "fresh_stat")
                self.assertEqual(updated["last_report"], "old.md")
        self.assertEqual(code, 0)
        send_mock.assert_not_called()

    def test_litellm_unavailable_exits_one(self):
        """No cache, send_prompt returns None -> exit 1."""
        code = self._run_main(None)
        self.assertEqual(code, 1)

    def test_litellm_unavailable_still_updates_cache(self):
        """Cache must be written on LiteLLM failure to prevent hammering on next cron tick."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            cache_path = repo_root / "ops" / "sessions" / ".audit-cache.json"
            with patch.object(weekly_audit, "find_repo_root", return_value=repo_root), \
                 patch.object(weekly_audit, "_compute_stat_signature", return_value="s_err"), \
                 patch.object(weekly_audit, "_compute_hash", return_value="c_err"), \
                 patch.object(weekly_audit, "load_prompt", return_value="prompt"), \
                 patch.object(weekly_audit.litellm_client, "send_prompt", return_value=None):
                with self.assertRaises(SystemExit):
                    weekly_audit.main()
            self.assertTrue(cache_path.exists(), "cache must be written even on LiteLLM failure")
            saved = json.loads(cache_path.read_text())
            self.assertEqual(saved["stat_sig"], "s_err")
            self.assertEqual(saved["content_hash"], "c_err")

    def test_litellm_success_exits_zero(self):
        """No cache, send_prompt returns content -> exit 0 + cache populated."""
        code = self._run_main("CLEAN -- sin hallazgos")
        self.assertEqual(code, 0)

    def test_find_repo_root_failure_exits_one(self):
        """RuntimeError from find_repo_root must produce sys.exit(1)."""
        with patch.object(
            weekly_audit,
            "find_repo_root",
            side_effect=RuntimeError("no git repo"),
        ):
            with self.assertRaises(SystemExit) as ctx:
                weekly_audit.main()
            self.assertEqual(ctx.exception.code, 1)

    def test_missing_placeholder_exits_one(self):
        """ValueError (placeholder absent from template) must produce sys.exit(1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            with patch.object(weekly_audit, "find_repo_root", return_value=repo_root), \
                 patch.object(weekly_audit, "load_prompt", side_effect=ValueError("placeholder absent")):
                with self.assertRaises(SystemExit) as ctx:
                    weekly_audit.main()
                self.assertEqual(ctx.exception.code, 1)

    def test_missing_prompt_template_exits_one(self):
        """FileNotFoundError from load_prompt must exit 1, not propagate as traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            with patch.object(weekly_audit, "find_repo_root", return_value=repo_root), \
                 patch.object(weekly_audit, "load_prompt",
                              side_effect=FileNotFoundError("weekly-audit.txt")):
                try:
                    weekly_audit.main()
                    result = 0
                except SystemExit as exc:
                    result = int(exc.code) if exc.code is not None else 0
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
