"""Pre-rendered audio for static phrases (greeting, fillers, silence prompts, closes).

Rendered once per language and stored on disk, so these turns have no TTS latency or cost.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Callable

from app.domain.base import PhraseBook
from app.lang.languages import LANGS, Lang
from app.tts.base import TTSProvider

log = logging.getLogger(__name__)


class PhraseAudioCache:
    def __init__(self, cache_dir: Path, voice_id: str, phrases: PhraseBook,
                 speak: Callable[[str, Lang], str] = lambda text, _lang: text):
        self.dir = Path(cache_dir) / voice_id
        self.phrases = phrases
        self.speak = speak
        self._memory: dict[tuple[str, str], bytes] = {}
        self._resident = False

    def text(self, key: str, lang: Lang) -> str:
        """Exactly what is synthesised for a phrase: the same text a live call would speak."""
        return self.speak(self.phrases.render(key, lang), lang)

    def _stem(self, key: str, lang: Lang) -> str:
        # The text's fingerprint is part of the name, so editing a phrase re-renders it instead of
        # replaying stale audio.
        return f"{key}-{hashlib.sha1(self.text(key, lang).encode()).hexdigest()[:8]}"

    def _path(self, key: str, lang: Lang) -> Path:
        return self.dir / lang / f"{self._stem(key, lang)}.ulaw"

    def get(self, key: str | None, lang: Lang) -> bytes | None:
        """Look up pre-rendered audio. Never touches the disk once the cache is resident.

        This runs on the speech path of a live call, so a disk read here stalls the event loop and
        chops the outgoing audio — badly so when the cache sits on network storage. After
        `preload()` the answer is always in memory, and a miss is a miss.
        """
        if not key or key not in self.phrases.keys():
            return None
        stem = self._stem(key, lang)
        if (stem, lang) in self._memory:
            return self._memory[(stem, lang)]
        if self._resident:
            return None
        path = self._path(key, lang)
        if path.exists():
            self._memory[(stem, lang)] = path.read_bytes()
            return self._memory[(stem, lang)]
        return None

    async def preload(self) -> int:
        """Read every cached phrase into memory, off the event loop, before answering calls."""
        def read_all() -> dict[tuple[str, str], bytes]:
            found: dict[tuple[str, str], bytes] = {}
            if not self.dir.exists():
                return found
            for lang_dir in self.dir.iterdir():
                if not lang_dir.is_dir():
                    continue
                for audio in lang_dir.glob("*.ulaw"):
                    try:
                        found[(audio.stem, lang_dir.name)] = audio.read_bytes()
                    except OSError as exc:
                        log.warning("could not read cached phrase %s: %r", audio, exc)
            return found

        self._memory.update(await asyncio.to_thread(read_all))
        self._resident = True
        return len(self._memory)

    async def warm(self, tts: TTSProvider, langs: tuple[Lang, ...] = LANGS,
                   concurrency: int = 4) -> int:
        """Pre-render every static phrase that is not cached yet.

        Rendered a few at a time rather than one by one: a cold cache is dozens of TTS round trips,
        and until it is warm every greeting and filler pays full synthesis latency.
        """
        missing = [(key, lang) for key in self.phrases.keys() for lang in langs
                   if self.get(key, lang) is None]
        if not missing:
            return 0
        semaphore = asyncio.Semaphore(concurrency)

        async def render(key: str, lang: Lang) -> bool:
            async with semaphore:
                try:
                    audio = b"".join([chunk async for chunk
                                      in tts.synthesize(self.text(key, lang), lang)])
                except Exception as exc:  # noqa: BLE001 - a missing phrase falls back to live TTS
                    log.warning("could not pre-render %s/%s: %r", key, lang, exc)
                    return False
            path = self._path(key, lang)
            await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_bytes, audio)
            self._memory[(self._stem(key, lang), lang)] = audio
            return True

        results = await asyncio.gather(*(render(k, l) for k, l in missing))
        return sum(results)
