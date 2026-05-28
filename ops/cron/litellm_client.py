#!/usr/bin/env python3
"""
Shared LiteLLM HTTP client for linkanvil git hooks and cron scripts.

Usage:
    from litellm_client import send_prompt, parse_findings, has_critical, Severity

send_prompt() returns the model response text, or None if LiteLLM is unavailable.
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

_FINDING_RE = re.compile(
    r"^(CRITICAL|HIGH|MEDIUM|LOW)[:\s]+(.+)",
    re.IGNORECASE,
)


def parse_findings(text: str) -> list[Finding]:
    """
    Parse model output into structured Finding objects.

    Accepts lines like:
        CRITICAL src/api/auth.py:42 JWT missing tenant_id check
        HIGH: some description
        CLEAN  ->  empty list

    Severity keyword must appear at the start of the line (anchored match).
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
        m = _FINDING_RE.match(line)
        if m:
            severity_str = m.group(1).upper()
            try:
                severity = Severity(severity_str)
            except ValueError:
                continue
            desc = m.group(2).strip()
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


# ---------------------------------------------------------------------------
# .env fallback — git hooks run en el shell del usuario, sin variables del
# docker compose. Si no hay LITELLM_KEY/LITELLM_MASTER_KEY exportadas,
# leemos .env del root del repo para que la autenticación funcione sin
# que el usuario tenga que `export` manual.
# ---------------------------------------------------------------------------

_DOTENV_LOADED = False


def _load_dotenv_fallback() -> None:
    """Parse .env del repo y poblar os.environ. Idempotente y silencioso."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    # Subir desde ops/cron/ hasta la raíz del repo.
    candidate = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        env_path = os.path.join(candidate, ".env")
        if os.path.isfile(env_path):
            try:
                with open(env_path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        # No pisamos variables ya exportadas en el shell.
                        os.environ.setdefault(key, value)
            except OSError:
                pass
            return
        parent = os.path.dirname(candidate)
        if parent == candidate:
            return
        candidate = parent


def _resolve_api_key() -> Optional[str]:
    """Prefer LITELLM_KEY; fall back to LITELLM_MASTER_KEY (alias usado en
    docker-compose para LiteLLM)."""
    _load_dotenv_fallback()
    return os.getenv("LITELLM_KEY") or os.getenv("LITELLM_MASTER_KEY")


def send_prompt(
    prompt: str,
    *,
    max_tokens: int = 600,
    timeout: int = 30,
    litellm_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0,
) -> Optional[str]:
    """
    Send a prompt to LiteLLM and return the response text.

    Returns None if LiteLLM is unreachable or returns an error.
    Never raises -- callers should treat None as fail-open.

    temperature: 0 for deterministic audit output; higher values for exploration.
    """
    raw_url = litellm_url or os.getenv("LITELLM_URL", _DEFAULT_URL)
    try:
        base_url = _validate_url(raw_url.rstrip("/"))
    except ValueError as exc:
        print(f"warning  {exc} -- skipping LiteLLM call", flush=True)
        return None

    resolved_model = model or os.getenv("LITELLM_MODEL", _DEFAULT_MODEL)

    payload = json.dumps(
        {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    api_key = _resolve_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            data = json.loads(raw)
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        print(f"warning  LiteLLM HTTP {exc.code} -- push continua sin analisis", flush=True)
        return None
    except urllib.error.URLError as exc:
        print(f"warning  LiteLLM no disponible ({exc.reason}) -- push continua sin analisis", flush=True)
        return None
    except (KeyError, IndexError, json.JSONDecodeError, OSError) as exc:
        print(f"warning  LiteLLM respuesta invalida ({exc}) -- push continua sin analisis", flush=True)
        return None
