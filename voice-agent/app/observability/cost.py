"""What a call cost in speech and model usage (telephony excluded), measured as it happens.

  speech-to-text   every second of the connected call (all caller audio is streamed)
  text-to-speech   characters actually synthesised (pre-rendered phrases from the cache are free)
  LLM              the provider's own token counts, per bucket: the conversation ("call"), health
                   probes run while the call was live ("probe", shared between concurrent calls)
                   and post-call work such as summary extraction ("post_call")

Prices are settings (COST_*), so a price change needs no code change. Logged once per call as
`call <id> cost: {...}` and kept with the call's details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.llm.base import LLMEvent, Usage

BUCKETS = ("call", "probe", "post_call")


@dataclass
class Prices:
    stt_per_hour: float = 30.0          # Sarvam Saaras v3 streaming
    tts_per_1k_chars: float = 3.0       # Sarvam Bulbul v3
    llm_input_per_m: float = 29.28      # Sarvam 105B (conversations)
    llm_cached_per_m: float = 10.98
    llm_output_per_m: float = 73.20
    currency: str = "INR"


@dataclass
class LlmUsage:
    requests: int = 0
    prompt_tokens: float = 0
    cached_tokens: float = 0
    completion_tokens: float = 0

    def cost(self, p: Prices) -> float:
        uncached = max(0.0, self.prompt_tokens - self.cached_tokens)
        return (uncached * p.llm_input_per_m + self.cached_tokens * p.llm_cached_per_m
                + self.completion_tokens * p.llm_output_per_m) / 1_000_000


@dataclass
class CostMeter:
    stt_seconds: float = 0.0
    tts_chars: int = 0
    llm: dict[str, LlmUsage] = field(default_factory=lambda: {b: LlmUsage() for b in BUCKETS})

    def add_usage(self, bucket: str, usage: Usage, share: float = 1.0) -> None:
        u = self.llm[bucket]
        u.prompt_tokens += usage.prompt_tokens * share
        u.cached_tokens += (usage.cached_tokens or 0) * share
        u.completion_tokens += usage.completion_tokens * share

    def add_request(self, bucket: str, share: float = 1.0) -> None:
        self.llm[bucket].requests += share

    def summary(self, p: Prices) -> dict[str, Any]:
        stt = self.stt_seconds / 3600 * p.stt_per_hour
        tts = self.tts_chars / 1000 * p.tts_per_1k_chars
        llm = {b: self.llm[b].cost(p) for b in BUCKETS}
        during = stt + tts + llm["call"] + llm["probe"]
        minutes = self.stt_seconds / 60
        return {
            "currency": p.currency,
            "total": round(during + llm["post_call"], 4),
            "during_call": round(during, 4),
            "per_minute": round(during / minutes, 4) if minutes > 0 else None,
            "post_call": round(llm["post_call"], 4),
            "stt": {"seconds": round(self.stt_seconds, 1), "cost": round(stt, 4)},
            "tts": {"chars": self.tts_chars, "cost": round(tts, 4)},
            "llm": {b: {"requests": round(self.llm[b].requests, 2),
                        "prompt_tokens": round(self.llm[b].prompt_tokens),
                        "cached_tokens": round(self.llm[b].cached_tokens),
                        "completion_tokens": round(self.llm[b].completion_tokens),
                        "cost": round(llm[b], 4)} for b in BUCKETS},
        }


class MeteredProvider:
    """Wraps an LLM provider so every request and its token usage land in a meter bucket."""

    def __init__(self, provider, meter: CostMeter, bucket: str):
        self.provider, self.meter, self.bucket = provider, meter, bucket
        self.name = getattr(provider, "name", "llm")

    async def stream(self, messages, tools, **kw) -> AsyncIterator[LLMEvent]:
        self.meter.add_request(self.bucket)
        async for event in self.provider.stream(messages, tools, **kw):
            if isinstance(event, Usage):
                self.meter.add_usage(self.bucket, event)
            yield event
