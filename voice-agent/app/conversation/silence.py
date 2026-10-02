"""Silence handling (spec section 29): three prompts, five seconds apart, then end the call."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


class SilenceWatchdog:
    def __init__(self, first_prompt_s: float, interval_s: float,
                 on_prompt: Callable[[int], Awaitable[None]], on_timeout: Callable[[], Awaitable[None]],
                 prompts: int = 3):
        self.first_prompt_s = first_prompt_s
        self.interval_s = interval_s
        self.on_prompt = on_prompt
        self.on_timeout = on_timeout
        self.prompts = prompts
        self._task: asyncio.Task | None = None

    @property
    def armed(self) -> bool:
        return self._task is not None and not self._task.done()

    def arm(self) -> None:
        self.disarm()
        self._task = asyncio.create_task(self._run())

    def disarm(self) -> None:
        if self._task and not self._task.done() and self._task is not asyncio.current_task():
            self._task.cancel()
        self._task = None

    async def _run(self) -> None:
        await asyncio.sleep(self.first_prompt_s)
        for n in range(1, self.prompts + 1):
            await self.on_prompt(n)
            await asyncio.sleep(self.interval_s)
        await self.on_timeout()
