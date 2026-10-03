"""Pre-rendered phrases: rendered once, loaded into memory, never read from disk mid-call."""

import asyncio

from app.tts.cache import PhraseAudioCache
from app.tts.fake import SilenceTTS

from tests.helpers import StubPhrases


def test_warm_then_preload_serves_from_memory(tmp_path):
    cache = PhraseAudioCache(tmp_path, "voice", StubPhrases())
    rendered = asyncio.run(cache.warm(SilenceTTS(), langs=("en",)))
    assert rendered == len(StubPhrases().keys())
    fresh = PhraseAudioCache(tmp_path, "voice", StubPhrases())
    assert asyncio.run(fresh.preload()) == rendered
    assert fresh.get("greeting", "en")
    # Once resident, a miss stays a miss rather than touching the disk.
    assert fresh.get("greeting", "hi") is None
    assert fresh.get("not_a_phrase", "en") is None
