"""Tests for ops/cron/litellm_client.py"""
from __future__ import annotations

import json
import sys
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

# Allow running from repo root or ops/cron/
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from litellm_client import (
    Finding,
    Severity,
    _validate_url,
    call,
    has_critical,
    parse_findings,
)


# ---------------------------------------------------------------------------
# parse_findings
# ---------------------------------------------------------------------------

class TestParseFindings(unittest.TestCase):

    def test_clean_returns_empty(self):
        self.assertEqual(parse_findings("CLEAN"), [])

    def test_clean_case_insensitive(self):
        self.assertEqual(parse_findings("clean"), [])

    def test_empty_string_returns_empty(self):
        self.assertEqual(parse_findings(""), [])

    def test_single_critical(self):
        findings = parse_findings("CRITICAL src/api/auth.py:42 JWT missing tenant_id")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, Severity.CRITICAL)

    def test_multiple_severities(self):
        text = (
            "CRITICAL src/api/auth.py:42 JWT issue\n"
            "HIGH src/data/db.py:10 SQL injection risk\n"
            "MEDIUM src/scraper/worker.py:5 missing rate limit\n"
        )
        findings = parse_findings(text)
        self.assertEqual(len(findings), 3)
        self.assertEqual(findings[0].severity, Severity.CRITICAL)
        self.assertEqual(findings[1].severity, Severity.HIGH)
        self.assertEqual(findings[2].severity, Severity.MEDIUM)

    def test_colon_suffix_on_severity(self):
        findings = parse_findings("HIGH: some description here")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, Severity.HIGH)

    def test_no_severity_lines_skipped(self):
        text = "This line has no severity\nCRITICAL real finding here"
        findings = parse_findings(text)
        self.assertEqual(len(findings), 1)

    def test_blank_lines_skipped(self):
        text = "\n\nCRITICAL real finding\n\n"
        findings = parse_findings(text)
        self.assertEqual(len(findings), 1)


# ---------------------------------------------------------------------------
# has_critical
# ---------------------------------------------------------------------------

class TestHasCritical(unittest.TestCase):

    def test_empty_list_is_false(self):
        self.assertFalse(has_critical([]))

    def test_only_high_is_false(self):
        findings = [Finding(Severity.HIGH, "some issue")]
        self.assertFalse(has_critical(findings))

    def test_critical_in_list_is_true(self):
        findings = [
            Finding(Severity.HIGH, "some issue"),
            Finding(Severity.CRITICAL, "bad thing"),
        ]
        self.assertTrue(has_critical(findings))


# ---------------------------------------------------------------------------
# _validate_url
# ---------------------------------------------------------------------------

class TestValidateUrl(unittest.TestCase):

    def test_http_is_valid(self):
        self.assertEqual(_validate_url("http://localhost:4000"), "http://localhost:4000")

    def test_https_is_valid(self):
        self.assertEqual(_validate_url("https://litellm.example.com"), "https://litellm.example.com")

    def test_ftp_raises(self):
        with self.assertRaises(ValueError):
            _validate_url("ftp://evil.com")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            _validate_url("")

    def test_relative_path_raises(self):
        with self.assertRaises(ValueError):
            _validate_url("/var/run/litellm.sock")


# ---------------------------------------------------------------------------
# call()
# ---------------------------------------------------------------------------

def _make_response(content: str, status: int = 200) -> MagicMock:
    """Return a mock object that behaves like urllib urlopen context manager."""
    payload = json.dumps({
        "choices": [{"message": {"content": content}}]
    }).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestCallLitellm(unittest.TestCase):

    @patch("litellm_client.urllib.request.urlopen")
    def test_returns_content_on_success(self, mock_urlopen):
        mock_urlopen.return_value = _make_response("CLEAN")
        result = call("test prompt", litellm_url="http://localhost:4000")
        self.assertEqual(result, "CLEAN")

    @patch("litellm_client.urllib.request.urlopen")
    def test_strips_whitespace(self, mock_urlopen):
        mock_urlopen.return_value = _make_response("  CLEAN  \n")
        result = call("test prompt", litellm_url="http://localhost:4000")
        self.assertEqual(result, "CLEAN")

    @patch("litellm_client.urllib.request.urlopen", side_effect=OSError("connection refused"))
    def test_returns_none_on_connection_error(self, _):
        result = call("test prompt", litellm_url="http://localhost:4000")
        self.assertIsNone(result)

    def test_returns_none_on_invalid_url_scheme(self):
        result = call("test prompt", litellm_url="ftp://bad-scheme.com")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
