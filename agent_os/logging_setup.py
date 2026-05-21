"""
logging_setup — structured (JSON) logging for the platform.

One line per event, machine-parseable, with a timestamp, level, logger name, and
any extra fields passed via `extra={"...": ...}`. Standard library only.

    from agent_os.logging_setup import configure, get_logger
    configure()                      # JSON to stdout (+ optional file)
    log = get_logger("supervisor")
    log.info("restart", extra={"attempt": 3, "job_id": "job-1"})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render each log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        # Merge any structured extras the caller attached.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure(level: str = "INFO", logfile: str | Path | None = None) -> None:
    """Configure root logging with the JSON formatter (idempotent)."""
    root = logging.getLogger("agent_os")
    root.setLevel(level)
    root.handlers.clear()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonFormatter())
    root.addHandler(stream)

    if logfile:
        path = Path(logfile)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path)
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)

    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"agent_os.{name}")
