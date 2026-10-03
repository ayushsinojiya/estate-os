"""Durable record of outbound call requests and the local do-not-call suppression cache.

Both live in one SQLite file under RUNTIME_DIR. The registry ties a request (made before the call
exists) to the telephony call that eventually connects, so a request's context is available when
the media socket opens and its outcome can be reported afterwards. SQLite is enough because the
agent runs as a single replica (see deploy/azure); moving to several replicas needs a shared store.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Request lifecycle. QUEUED -> DIALING -> CONNECTED -> COMPLETED, or a terminal failure.
QUEUED, DIALING, CONNECTED, COMPLETED = "QUEUED", "DIALING", "CONNECTED", "COMPLETED"
REFUSED, FAILED, NO_ANSWER, SIMULATED = "REFUSED", "FAILED", "NO_ANSWER", "SIMULATED"
TERMINAL = {COMPLETED, REFUSED, FAILED, NO_ANSWER, SIMULATED}


def phone_tail(phone: str | None) -> str:
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    return digits[-10:]


@dataclass
class OutboundRecord:
    request_id: str
    phone: str
    status: str = QUEUED
    custom: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    attempts: int = 0


class CallRegistry:
    def __init__(self, path: Path, journal_mode: str = "WAL"):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute(f"PRAGMA journal_mode={'DELETE' if journal_mode == 'DELETE' else 'WAL'}")
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS outbound_calls (
                  request_id TEXT PRIMARY KEY, phone TEXT NOT NULL, status TEXT NOT NULL,
                  custom TEXT NOT NULL, call_id TEXT, reason TEXT, details TEXT NOT NULL DEFAULT '{}',
                  attempts INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_outbound_status ON outbound_calls(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_outbound_call ON outbound_calls(call_id);
                CREATE TABLE IF NOT EXISTS suppression (
                  phone_tail TEXT PRIMARY KEY, reason TEXT, created_at REAL NOT NULL);
            """)

    # ---- outbound requests

    def _row(self, row: tuple) -> OutboundRecord:
        (request_id, phone, status, custom, call_id, reason, details, attempts, created, updated) = row
        return OutboundRecord(request_id, phone, status, json.loads(custom), call_id, reason,
                              json.loads(details), created, updated, attempts)

    _COLUMNS = "request_id,phone,status,custom,call_id,reason,details,attempts,created_at,updated_at"

    def add(self, record: OutboundRecord) -> OutboundRecord:
        """Insert a request; an existing request id returns the stored record unchanged."""
        with self._lock:
            self._db.execute(
                f"INSERT OR IGNORE INTO outbound_calls({self._COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (record.request_id, record.phone, record.status, json.dumps(record.custom),
                 record.call_id, record.reason, json.dumps(record.details), record.attempts,
                 record.created_at, record.updated_at))
        return self.get(record.request_id)  # type: ignore[return-value]

    def get(self, request_id: str) -> OutboundRecord | None:
        with self._lock:
            row = self._db.execute(f"SELECT {self._COLUMNS} FROM outbound_calls WHERE request_id=?",
                                   (request_id,)).fetchone()
        return self._row(row) if row else None

    def by_call(self, call_id: str) -> OutboundRecord | None:
        with self._lock:
            row = self._db.execute(f"SELECT {self._COLUMNS} FROM outbound_calls WHERE call_id=?",
                                   (call_id,)).fetchone()
        return self._row(row) if row else None

    def queued(self, limit: int = 10) -> list[OutboundRecord]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {self._COLUMNS} FROM outbound_calls WHERE status=? ORDER BY created_at LIMIT ?",
                (QUEUED, limit)).fetchall()
        return [self._row(r) for r in rows]

    def with_status(self, status: str, older_than: float | None = None) -> list[OutboundRecord]:
        sql = f"SELECT {self._COLUMNS} FROM outbound_calls WHERE status=?"
        args: list[Any] = [status]
        if older_than is not None:
            sql += " AND updated_at < ?"
            args.append(older_than)
        with self._lock:
            rows = self._db.execute(sql + " ORDER BY created_at", args).fetchall()
        return [self._row(r) for r in rows]

    def count(self, status: str) -> int:
        with self._lock:
            return self._db.execute("SELECT count(*) FROM outbound_calls WHERE status=?",
                                    (status,)).fetchone()[0]

    def update(self, request_id: str, *, status: str | None = None, call_id: str | None = None,
               reason: str | None = None, details: dict[str, Any] | None = None,
               attempt: bool = False) -> OutboundRecord | None:
        current = self.get(request_id)
        if current is None:
            return None
        merged = {**current.details, **(details or {})}
        with self._lock:
            self._db.execute(
                "UPDATE outbound_calls SET status=?, call_id=?, reason=?, details=?, attempts=?,"
                " updated_at=? WHERE request_id=?",
                (status or current.status, call_id or current.call_id, reason or current.reason,
                 json.dumps(merged, default=str), current.attempts + (1 if attempt else 0),
                 time.time(), request_id))
        return self.get(request_id)

    # ---- suppression (a local cache; the CRM is the source of truth)

    def suppress(self, phone: str, reason: str = "") -> None:
        tail = phone_tail(phone)
        if not tail:
            return
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO suppression(phone_tail,reason,created_at) VALUES (?,?,?)",
                             (tail, reason, time.time()))

    def is_suppressed(self, phone: str) -> bool:
        tail = phone_tail(phone)
        with self._lock:
            return self._db.execute("SELECT 1 FROM suppression WHERE phone_tail=?",
                                    (tail,)).fetchone() is not None

    def close(self) -> None:
        with self._lock:
            self._db.close()
