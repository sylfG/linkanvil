#!/usr/bin/env python3
"""
Shared LiteLLM HTTP client for linkanvil git hooks and cron scripts.

Usage:
    from litellm_client import call, parse_findings, has_critical, Severity

call() returns the model response text, or None if LiteLLM is unavailable.
Never raises — fail-open is always respected.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Severity + Finding
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Finding:
    severity: Severity
    description: str

    def __str__(self) -> str:
        return f"{self.severity.value}: {self.description}"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_SEVERITY_RE = re.compile(
    r"\b(CRITICAL|HIGH|MEDIUM|LOW)\b",
    re.IGNORECASE,
)


def parse_findings(text: str) -> list[Finding]:
    """
    Parse model output into structured Finding objects.

    Accepts lines like:
        CRITICAL src/api/auth.py:42 JWT missing tenant_id check
        HIGH: some description
        CLEAN  →  empty list
    """
    if not text:
        return []
    stripped = text.strip()
    if stripped.upper() == "CLEAN":
        return []

    findings: list[Finding] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SEVERITY_RE.search(line)
        if m:
            severity_str = m.group(1).upper()
            try:
                severity = Severity(severity_str)
            except ValueError:
                continue
            # Slice from end of match so description excludes the severity keyword
            desc = line[m.end():].strip().lstrip(":").strip()
            findings.append(Finding(severity=severity, description=desc))
    return findings


def has_critical(findings: list[Finding]) -> bool:
    """Return True only when a CRITICAL finding is present."""
    return any(f.severity == Severity.CRITICAL for f in findings)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

_DEFAULT_URL = "http://localhost:4000"
_DEFAULT_MODEL = "cerebro-lite"


def _validate_url(url: str) -> str:
    """Raise ValueError if url is not http or https."""
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            f"LITELLM_URL must start with http:// or https://, got: {url!r}"
        )
    return url


def call(
    prompt: str,
    *,
    max_tokens: int = 600,
    timeout: int = 30,
    litellm_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Send a prompt to LiteLLM and return the response text.

    Returns None if LiteLLM is unreachable or returns an error.
    Never raises — callers should treat None as fail-open.
    """
    raw_url = litellm_url or os.getenv("LITELLM_URL", _DEFAULT_URL)
    try:
        base_url = _validate_url(raw_url.rstrip("/"))
    except ValueError as exc:
        print(f"⚠️  {exc} — skipping LiteLLM call", flush=True)
        return None

    resolved_model = model or os.getenv("LITELLM_MODEL", _DEFAULT_MODEL)

    payload = json.dumps(
        {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
    ).encode()

    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            data = json.loads(raw)
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        print(f"⚠️  LiteLLM HTTP {exc.code} — push continúa sin análisis", flush=True)
        return None
    except urllib.error.URLError as exc:
        print(f"⚠️  LiteLLM no disponible ({exc.reason}) — push continúa sin análisis", flush=True)
        return None
    except (KeyError, json.JSONDecodeError, OSError) as exc:
        print(f"⚠️  LiteLLM respuesta inválida ({exc}) — push continúa sin análisis", flush=True)
        return None
