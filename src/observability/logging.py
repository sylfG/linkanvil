"""
Structured JSON logging for cerebro services.

Produces one JSON object per log line so they can be parsed without regexes
by Loki/ELK/Datadog/CloudWatch:

  {"ts":"2026-04-26T10:00:00.123Z","level":"info","service":"cerebro-api",
   "logger":"src.api.main","message":"Cerebro started","trace_id":"...",
   "tenant_id":"..."}

Usage:
    from src.observability.logging import configure_json_logging
    configure_json_logging("cerebro-api")  # call once at startup

Plain `logger = logging.getLogger(...)` then works as usual; extras passed
via `logger.info("msg", extra={"trace_id": "...", "tenant_id": "..."})`
become first-class JSON fields.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

_RESERVED_LOGRECORD_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                 + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Promote known correlation attrs and any other extras to top-level.
        for k, v in record.__dict__.items():
            if k in _RESERVED_LOGRECORD_ATTRS or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging(service: str, level: str | None = None) -> None:
    """Replace any existing handlers on the root logger with one JSON handler."""
    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(service=service))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    # Quieten the noisy third-party libs we don't own.
    for noisy in ("uvicorn.access", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
