"""Tests for ops/cron/utils.py"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import atomic_write, find_repo_root, load_prompt, read_template, render_template


class TestFindRepoRoot(unittest.TestCase):

    def test_returns_path_when_inside_repo(self):
        root = find_repo_root()
        self.assertIsInstance(root, Path)
        self.assertTrue(root.exists())

    def test_returns_path_with_mocked_subprocess(self):
        with patch("utils.subprocess.check_output", return_value=b"/tmp/fake-repo\n"):
            root = find_repo_root()
        self.assertEqual(root, Path("/tmp/fake-repo"))

    def test_raises_runtime_error_outside_repo(self):
        with patch("utils.subprocess.check_output", side_effect=subprocess.CalledProcessError(128, "git")):
            with self.assertRaises(RuntimeError) as ctx:
                find_repo_root()
        self.assertIn("repositorio", str(ctx.exception).lower())

    def test_error_message_is_informative(self):
        with patch("utils.subprocess.check_output", side_effect=subprocess.CalledProcessError(128, "git")):
            with self.assertRaises(RuntimeError) as ctx:
                find_repo_root()
        self.assertIn("git", str(ctx.exception).lower())


class TestLoadPrompt(unittest.TestCase):

    def test_replaces_placeholder(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("Hello {name}! Diff: {diff}")
            f_path = Path(f.name)
        try:
            result = load_prompt(f_path, {"{name}": "world", "{diff}": "..."})
            self.assertEqual(result, "Hello world! Diff: ...")
        finally:
            f_path.unlink()

    def test_raises_file_not_found_with_path_in_message(self):
        missing = Path("/nonexistent/prompt.txt")
        with self.assertRaises(FileNotFoundError) as ctx:
            load_prompt(missing, {})
        self.assertIn(str(missing), str(ctx.exception))

    def test_empty_replacements_returns_template_unchanged(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("no placeholders here")
            f_path = Path(f.name)
        try:
            result = load_prompt(f_path, {})
            self.assertEqual(result, "no placeholders here")
        finally:
            f_path.unlink()

    def test_raises_value_error_when_placeholder_absent_from_template(self):
        """Regression: silently skipped substitution would send literal {diff} to LLM."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("template with no placeholders")
            f_path = Path(f.name)
        try:
            with self.assertRaises(ValueError) as ctx:
                load_prompt(f_path, {"{diff}": "some diff"})
            self.assertIn("{diff}", str(ctx.exception))
        finally:
            f_path.unlink()


class TestReadTemplate(unittest.TestCase):

    def test_returns_file_contents(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("hello {name}")
            p = Path(f.name)
        try:
            self.assertEqual(read_template(p), "hello {name}")
        finally:
            p.unlink(missing_ok=True)

    def test_raises_file_not_found_with_path_in_message(self):
        missing = Path("/nonexistent/template.txt")
        with self.assertRaises(FileNotFoundError) as ctx:
            read_template(missing)
        self.assertIn(str(missing), str(ctx.exception))


class TestRenderTemplate(unittest.TestCase):

    def test_substitutes_placeholder(self):
        result = render_template("hello {name}", {"{name}": "world"})
        self.assertEqual(result, "hello world")

    def test_raises_value_error_when_placeholder_absent(self):
        with self.assertRaises(ValueError):
            render_template("static template", {"{missing}": "x"})

    def test_empty_replacements_returns_template_unchanged(self):
        self.assertEqual(render_template("unchanged", {}), "unchanged")

    def test_no_io_performed(self):
        """render_template must be pure transformation -- no filesystem access."""
        # If it tried to read disk, this nonsense path would crash.
        result = render_template("{a} and {b}", {"{a}": "x", "{b}": "y"})
        self.assertEqual(result, "x and y")


class TestAtomicWrite(unittest.TestCase):

    def test_writes_content_to_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.txt"
            atomic_write(path, "hello")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")

    def test_creates_parent_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deeply" / "out.txt"
            atomic_write(path, "data")
            self.assertTrue(path.exists())

    def test_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.txt"
            path.write_text("old", encoding="utf-8")
            atomic_write(path, "new")
            self.assertEqual(path.read_text(encoding="utf-8"), "new")

    def test_no_temp_file_remains_after_success(self):
        """Atomic write must leave no .tmp residue in parent dir on success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.txt"
            atomic_write(path, "content")
            tmp_files = list(Path(tmpdir).glob("*.tmp"))
            self.assertEqual(tmp_files, [],
                             f"unexpected .tmp residue: {tmp_files}")



if __name__ == "__main__":
    unittest.main()
