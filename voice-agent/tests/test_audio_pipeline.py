"""Codecs, VAD, wire-format detection, end-of-turn and barge-in: the speech path's building blocks."""

import asyncio
import math

import numpy as np

from app.audio.codecs import (MULAW_SILENCE, apply_gain_mulaw, mulaw_to_pcm16, pcm16_to_mulaw,
                              downsample, upsample)
from app.audio.vad import EnergyVAD
from app.conversation.interruption import BargeIn, BargeInDetector, is_backchannel
from app.conversation.turn_detection import TurnConfig, TurnDetector, looks_incomplete
from app.telephony.wire_format import CodecDetector, WireFormat, format_from_media_format


def _tone(seconds=0.2, freq=440, amp=8000, rate=8000):
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * math.pi * freq * t)).astype(np.int16)


def test_mulaw_round_trip_is_close():
    pcm = _tone()
    back = mulaw_to_pcm16(pcm16_to_mulaw(pcm))
    assert np.max(np.abs(back.astype(int) - pcm.astype(int))) < 600


def test_gain_clips_instead_of_wrapping():
    loud = pcm16_to_mulaw(_tone(amp=30000))
    boosted = mulaw_to_pcm16(apply_gain_mulaw(loud, 2.0))
    assert boosted.max() <= 32767 and boosted.min() >= -32768
    assert apply_gain_mulaw(loud, 1.0) is loud


def test_resampling_preserves_length_ratio():
    pcm = _tone(rate=16000)
    assert abs(len(downsample(pcm, 16000, 8000)) - len(pcm) // 2) <= 1
    assert abs(len(upsample(pcm, 8000, 16000)) - len(pcm) * 2) <= 2


def test_vad_detects_speech_after_calibration():
    vad = EnergyVAD()
    silence = bytes([MULAW_SILENCE]) * 160
    events = []
    for _ in range(20):
        events += vad.process(silence)
    speech = pcm16_to_mulaw(_tone(seconds=0.5))
    events += vad.process(speech)
    for _ in range(20):
        events += vad.process(silence)
    assert events == ["start", "end"]


def test_wire_format_from_media_format_and_detection():
    assert str(format_from_media_format({"encoding": "audio/x-mulaw", "sample_rate": 8000})) == "mulaw@8000"
    assert format_from_media_format({"encoding": "base64"}) is None
    detector = CodecDetector()
    pcm = _tone(seconds=0.5, amp=4000)
    assert detector.feed(pcm.astype("<i2").tobytes()).codec == "pcm16le"
    wire = WireFormat("pcm16le", 16000)
    assert len(wire.from_internal(bytes([MULAW_SILENCE]) * 160)) == 640


def test_incomplete_utterances_wait_longer():
    assert looks_incomplete("मला दोन बीएचके आणि")
    assert not looks_incomplete("I want a two bedroom flat")
    detector = TurnDetector(TurnConfig())
    detector.on_final("I want a flat and")
    assert detector.required_silence_ms() == TurnConfig().incomplete_silence_ms


def test_a_turn_is_committed_after_silence():
    async def scenario():
        detector = TurnDetector(TurnConfig(base_silence_ms=10, final_wait_ms=50))
        detector.on_speech_start()
        detector.on_final("two bedroom in Baner", "en")
        detector.on_speech_end()
        return await asyncio.wait_for(detector.turns.get(), 1)

    turn = asyncio.run(scenario())
    assert turn.text == "two bedroom in Baner" and turn.language == "en"


def test_backchannels_do_not_interrupt_but_real_speech_does():
    assert is_backchannel("haan ji")
    barge = BargeInDetector(min_speech_ms=300)
    barge.on_onset(0.0)
    barge.on_text("hmm")
    assert barge.evaluate(0.2) == BargeIn.PENDING
    barge.on_text("wait, what about parking")
    assert barge.evaluate(0.25) == BargeIn.INTERRUPT
