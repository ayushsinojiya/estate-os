"""Shared HTTP retry policy for model providers: retry 429 and 5xx with backoff, nothing else."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

log = logging.getLogger(__name__)


# A per-minute rate limit can need most of a minute to clear; never wait longer than this per retry.
MAX_RATE_LIMIT_WAIT_S = 60.0


class ProviderError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, retryable: bool = False,
                 retry_after_s: float | None = None):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.retry_after_s = retry_after_s


def retry_after(response: httpx.Response) -> float | None:
    """The wait a 429 asks for (OpenAI sends retry-after-ms and Retry-After), in seconds."""
    for header, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        value = response.headers.get(header)
        if value:
            try:
                return min(MAX_RATE_LIMIT_WAIT_S, max(0.0, float(value) * scale))
            except ValueError:
                pass
    return None


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
                                  response.status_code, retryable,
                                  retry_after(response) if response.status_code == 429 else None)
        attempt += 1
        if not error.retryable or attempt > retries:
            raise error
        delay = base_delay_s * (2 ** (attempt - 1)) * (0.75 + random.random() / 2)
        if error.status == 429:
            # Rate limited: wait at least as long as the provider asks (or a few seconds when it does
            # not say), so a bulk upload slows down instead of falling back to the text layer.
            delay = max(delay, error.retry_after_s if error.retry_after_s is not None else 5.0 * attempt)
        log.warning("provider call failed (%s); retry %d in %.1fs", error, attempt, delay)
        await asyncio.sleep(delay)
