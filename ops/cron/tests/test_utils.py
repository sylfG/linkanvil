"""Tests for ops/cron/utils.py"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import find_repo_root


class TestFindRepoRoot(unittest.TestCase):

    def test_returns_path_when_inside_repo(self):
        root = find_repo_root()
        self.assertIsInstance(root, Path)
        self.assertTrue(root.exists())

    def test_raises_runtime_error_outside_repo(self):
        with patch("utils.subprocess.check_output", side_effect=subprocess.CalledProcessError(128, "git")):
            with self.assertRaises(RuntimeError) as ctx:
                find_repo_root()
        self.assertIn("repositorio", str(ctx.exception).lower())

    def test_error_message_is_informative(self):
        with patch("utils.subprocess.check_output", side_effect=subprocess.CalledProcessError(128, "git")):
            try:
                find_repo_root()
            except RuntimeError as exc:
                self.assertTrue(len(str(exc)) > 0)


if __name__ == "__main__":
    unittest.main()
