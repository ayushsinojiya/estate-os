"""A durable retry outbox for side effects that must eventually reach another service.

A call ends whether or not the CRM is reachable at that moment, so the post-call record is written
here first and delivered by a background worker with exponential backoff. Each item has a stable
key: enqueueing the same key twice is a no-op, and the receiving API is expected to be idempotent
on it, so a delivery that timed out after the far side committed can be resent safely.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

PENDING, DELIVERED, DEAD = "PENDING", "DELIVERED", "DEAD"
Handler = Callable[[dict[str, Any]], Awaitable[None]]


class PermanentFailure(Exception):
    """Raised by a handler when retrying cannot help (e.g. the receiver rejected the payload)."""


class Outbox:
    def __init__(self, path: Path, *, base_delay_s: float = 2.0, max_delay_s: float = 300.0,
                 max_attempts: int = 12, clock: Callable[[], float] = time.time,
                 journal_mode: str = "WAL"):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        # See Settings.sqlite_journal_mode: DELETE on a network mount, WAL on a local disk.
        self._db.execute(f"PRAGMA journal_mode={'DELETE' if journal_mode == 'DELETE' else 'WAL'}")
        self._lock = threading.Lock()
        self.base_delay_s = base_delay_s
        self.max_delay_s = max_delay_s
        self.max_attempts = max_attempts
        self.clock = clock
        self.handlers: dict[str, Handler] = {}
        self.wake = asyncio.Event()
        with self._lock:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS outbox (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, key TEXT NOT NULL UNIQUE,
                  payload TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                  next_attempt_at REAL NOT NULL, last_error TEXT, created_at REAL NOT NULL,
                  updated_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox(status, next_attempt_at);
            """)

    def register(self, kind: str, handler: Handler) -> None:
        self.handlers[kind] = handler

    def enqueue(self, kind: str, key: str, payload: dict[str, Any]) -> bool:
        """Store an item for delivery. Returns False when the key was already enqueued."""
        now = self.clock()
        with self._lock:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO outbox(kind,key,payload,status,next_attempt_at,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (kind, key, json.dumps(payload, ensure_ascii=False, default=str), PENDING, now, now, now))
        added = cursor.rowcount == 1
        if added:
            try:
                self.wake.set()
            except RuntimeError:  # no running loop (tests, scripts)
                pass
        return added

    def item(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT kind,payload,status,attempts,last_error FROM outbox WHERE key=?",
                                   (key,)).fetchone()
        if row is None:
            return None
        return {"kind": row[0], "payload": json.loads(row[1]), "status": row[2], "attempts": row[3],
                "last_error": row[4]}

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._db.execute("SELECT status, count(*) FROM outbox GROUP BY status").fetchall()
        return {status: n for status, n in rows}

    def _due(self, limit: int) -> list[tuple[int, str, str, str, int]]:
        with self._lock:
            return self._db.execute(
                "SELECT id,kind,key,payload,attempts FROM outbox WHERE status=? AND next_attempt_at<=?"
                " ORDER BY next_attempt_at, id LIMIT ?", (PENDING, self.clock(), limit)).fetchall()

    def _mark(self, item_id: int, status: str, attempts: int, error: str | None, delay: float = 0) -> None:
        now = self.clock()
        with self._lock:
            self._db.execute("UPDATE outbox SET status=?, attempts=?, last_error=?, next_attempt_at=?,"
                             " updated_at=? WHERE id=?",
                             (status, attempts, (error or "")[:500] or None, now + delay, now, item_id))

    def backoff(self, attempts: int) -> float:
        return min(self.max_delay_s, self.base_delay_s * (2 ** max(0, attempts - 1)))

    async def deliver_due(self, limit: int = 20) -> int:
        delivered = 0
        for item_id, kind, key, payload, attempts in self._due(limit):
            handler = self.handlers.get(kind)
            if handler is None:
                self._mark(item_id, DEAD, attempts, f"no handler for {kind}")
                continue
            try:
                await handler(json.loads(payload))
            except PermanentFailure as exc:
                log.error("outbox %s %s rejected permanently: %s", kind, key, exc)
                self._mark(item_id, DEAD, attempts + 1, str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 - every other failure is retried
                attempts += 1
                if attempts >= self.max_attempts:
                    log.error("outbox %s %s gave up after %d attempts: %r", kind, key, attempts, exc)
                    self._mark(item_id, DEAD, attempts, repr(exc))
                else:
                    delay = self.backoff(attempts)
                    log.warning("outbox %s %s failed (%r); retry in %.0fs", kind, key, exc, delay)
                    self._mark(item_id, PENDING, attempts, repr(exc), delay)
                continue
            self._mark(item_id, DELIVERED, attempts + 1, None)
            delivered += 1
        return delivered

    async def run(self, poll_s: float = 2.0) -> None:
        while True:
            try:
                await self.deliver_due()
            except Exception:  # noqa: BLE001 - the worker must outlive any one bad item
                log.exception("outbox worker error")
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), poll_s)
            except asyncio.TimeoutError:
                pass

    def close(self) -> None:
        with self._lock:
            self._db.close()
