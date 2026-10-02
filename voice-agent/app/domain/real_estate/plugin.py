"""The real-estate domain plugin: Riya, calling on behalf of a builder."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.domain.base import CallInfo
from app.llm.base import Message

from .conversation import RealEstateConversation
from .phrases import RealEstatePhrases
from .prompt import PROMPT_VERSION, system_prompt

if TYPE_CHECKING:
    from app.wiring import EngineServices


class RealEstatePlugin:
    name = "real_estate"

    def __init__(self, services: "EngineServices"):
        self.services = services
        self.settings = services.settings
        s = self.settings
        self.phrases = RealEstatePhrases(s.builder_name, s.disclose_ai, s.disclose_recording)

    def conversation(self, info: CallInfo) -> RealEstateConversation:
        return RealEstateConversation(self, info)

    def probe_messages(self) -> list[Message]:
        return [Message("system", system_prompt(self.phrases.builder_name, "mr")),
                Message("user", "नमस्कार, बाणेरमध्ये दोन BHK फ्लॅट बद्दल माहिती हवी आहे.")]

    def is_sensitive(self, text: str) -> bool:
        return False

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"prompt_version": PROMPT_VERSION}
