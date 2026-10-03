"""Structured logging. JSON lines in production (LOG_FORMAT=json), plain text locally."""

from __future__ import annotations

import json
import logging
import re
import time

# Query parameters that carry credentials (VoiceLink calls the webhook with ?token=...). uvicorn's
# access log prints the full request path, so they are masked before any line is written.
_SECRET_PARAM = re.compile(r"(?i)([?&](?:token|access_token|api_key|apikey|key|password|secret)=)[^&\s\"']+")


def redact(text: str) -> str:
    return _SECRET_PARAM.sub(r"\1***", text)


class RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
                 "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        for key in ("call_id", "prompt_version", "event"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure(level: str = "INFO", fmt: str = "text") -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if fmt == "json"
                         else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactSecrets())
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn's access logger has its own handler and does not propagate to the root.
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactSecrets) for f in logger.filters):
            logger.addFilter(RedactSecrets())
