"""Shared HTTP retry policy for model providers: retry 429 and 5xx with backoff, nothing else."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


async def post_json(client: httpx.AsyncClient, url: str, *, headers: dict[str, str],
                    payload: dict[str, Any], retries: int = 3, base_delay_s: float = 0.5,
                    timeout_s: float = 60.0) -> dict[str, Any]:
    attempt = 0
    while True:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=timeout_s)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            error = ProviderError(f"transport: {exc!r}", retryable=True)
        else:
            if response.status_code < 400:
                return response.json()
            retryable = response.status_code == 429 or response.status_code >= 500
            error = ProviderError(f"{url} -> {response.status_code}: {response.text[:300]}",
                                  response.status_code, retryable)
        attempt += 1
        if not error.retryable or attempt > retries:
            raise error
        delay = base_delay_s * (2 ** (attempt - 1)) * (0.75 + random.random() / 2)
        log.warning("provider call failed (%s); retry %d in %.1fs", error, attempt, delay)
        await asyncio.sleep(delay)
