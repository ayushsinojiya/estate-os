"""Structured logging. JSON lines in production (LOG_FORMAT=json), plain text locally."""

from __future__ import annotations

import json
import logging
import time


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
    root.handlers[:] = [handler]
    root.setLevel(level)
