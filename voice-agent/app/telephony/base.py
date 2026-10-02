"""Telephony boundary (spec section 4). Nothing VoiceLink-specific leaks past this interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol


@dataclass
class CallStart:
    call_id: str
    stream_id: str
    from_number: str | None
    to_number: str | None
    direction: Literal["inbound", "outbound"]
    custom: dict[str, Any] = field(default_factory=dict)


class CallTransport(Protocol):
    start: CallStart

    def audio_frames(self) -> AsyncIterator[bytes]:
        """Inbound caller audio as 8 kHz μ-law. Ends when the caller hangs up."""
        ...

    async def send_audio(self, mulaw_8k: bytes) -> None: ...
    async def clear_audio(self) -> None: ...
    async def hangup(self) -> None: ...


class OutboundQueue(Protocol):
    """Outbound calls are queued with the telephony provider, which dials them."""

    async def add_lead(self, did_number: str, customer_number: str, custom_parameters: dict[str, Any],
                       websocket_url: str | None = None, webhook_url: str | None = None,
                       country_code: str = "91") -> Any: ...
    async def pause_queue(self, client_id: int) -> Any: ...
    async def resume_queue(self, client_id: int) -> Any: ...
