"""Telephony wire audio formats and detection.

Internally the pipeline uses 8 kHz μ-law. VoiceLink's stream announces a media_format
(encoding, sample_rate); when that is ambiguous (e.g. "base64") the codec is detected from the
audio itself: correctly decoded speech or line noise is smooth sample to sample, while bytes
decoded with the wrong codec or byte order look like white noise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from app.audio.codecs import (ALAW_SILENCE, MULAW_SILENCE, alaw_to_pcm16, downsample, mulaw_to_pcm16, pcm16_to_alaw,
                              pcm16_to_mulaw, upsample)

Codec = Literal["mulaw", "alaw", "pcm16le", "pcm16be"]


@dataclass
class WireFormat:
    codec: Codec
    sample_rate: int = 8000
    _in_remainder: bytes = field(default=b"", repr=False)

    def __str__(self) -> str:
        return f"{self.codec}@{self.sample_rate}"

    @classmethod
    def from_bot_setting(cls, name: str) -> "WireFormat":
        return {"alaw": cls("alaw"), "l16": cls("pcm16le"), "l16_16k": cls("pcm16le", 16000)}.get(name, cls("mulaw"))

    @property
    def bytes_per_sample(self) -> int:
        return 2 if self.codec.startswith("pcm16") else 1

    def bytes_for_ms(self, ms: int) -> int:
        return int(self.sample_rate * ms / 1000) * self.bytes_per_sample

    def silence(self, n_bytes: int) -> bytes:
        if self.codec == "mulaw":
            return bytes([MULAW_SILENCE]) * n_bytes
        if self.codec == "alaw":
            return bytes([ALAW_SILENCE]) * n_bytes
        return b"\x00" * n_bytes

    def _pcm(self, raw: bytes) -> np.ndarray:
        if self.codec == "mulaw":
            return mulaw_to_pcm16(raw)
        if self.codec == "alaw":
            return alaw_to_pcm16(raw)
        data = self._in_remainder + raw
        usable = len(data) // 2 * 2
        self._in_remainder = data[usable:]
        return np.frombuffer(data[:usable], dtype="<i2" if self.codec == "pcm16le" else ">i2")

    def to_internal(self, raw: bytes) -> bytes:
        """Wire bytes → 8 kHz μ-law."""
        if self.codec == "mulaw" and self.sample_rate == 8000:
            return raw
        pcm = self._pcm(raw)
        if self.sample_rate != 8000:
            pcm = downsample(pcm, self.sample_rate, 8000)
        return pcm16_to_mulaw(pcm)

    def from_internal(self, mulaw_8k: bytes) -> bytes:
        """8 kHz μ-law → wire bytes."""
        if self.codec == "mulaw" and self.sample_rate == 8000:
            return mulaw_8k
        pcm = mulaw_to_pcm16(mulaw_8k)
        if self.sample_rate != 8000:
            pcm = upsample(pcm, 8000, self.sample_rate)
        if self.codec == "mulaw":
            return pcm16_to_mulaw(pcm)
        if self.codec == "alaw":
            return pcm16_to_alaw(pcm)
        return pcm.astype("<i2" if self.codec == "pcm16le" else ">i2").tobytes()


def _rate(value: object) -> int:
    digits = re.sub(r"\D", "", str(value or ""))
    rate = int(digits) if digits else 8000
    return rate if rate in (8000, 16000, 24000, 48000) else 8000


def format_from_media_format(media_format: dict | None) -> WireFormat | None:
    """Explicit encodings only; returns None when detection is needed."""
    if not isinstance(media_format, dict):
        return None
    encoding = str(media_format.get("encoding", "")).lower()
    rate = _rate(media_format.get("sample_rate"))
    if any(k in encoding for k in ("mulaw", "ulaw", "pcmu", "g711u", "g711_u")):
        return WireFormat("mulaw", rate)
    if any(k in encoding for k in ("alaw", "pcma", "g711a", "g711_a")):
        return WireFormat("alaw", rate)
    if any(k in encoding for k in ("l16", "slin", "linear", "pcm", "s16")):
        return WireFormat("pcm16be" if "be" in encoding.split("_") or "big" in encoding else "pcm16le", rate)
    return None


def roughness(samples: np.ndarray) -> float | None:
    x = samples.astype(np.float64)
    if len(x) < 64 or np.std(x) < 30:
        return None
    centred = x - np.mean(x)
    return float(np.mean(np.abs(np.diff(x))) / (np.mean(np.abs(centred)) + 1e-9))


class CodecDetector:
    def __init__(self, sample_rate: int = 8000, min_bytes: int = 1600):
        self.sample_rate = sample_rate
        self.min_bytes = min_bytes
        self.buffer = b""
        self.reason = ""

    @property
    def bytes_seen(self) -> int:
        return len(self.buffer)

    def feed(self, raw: bytes) -> WireFormat | None:
        self.buffer += raw
        if len(self.buffer) < self.min_bytes:
            return None
        window = self.buffer[-4000:]
        even = window[: len(window) // 2 * 2]
        scores = {
            "pcm16le": roughness(np.frombuffer(even, dtype="<i2")),
            "pcm16be": roughness(np.frombuffer(even, dtype=">i2")),
            "mulaw": roughness(mulaw_to_pcm16(window)),
            "alaw": roughness(alaw_to_pcm16(window)),
        }
        valid = {k: v for k, v in scores.items() if v is not None}
        self.reason = ", ".join(f"{k}={v:.2f}" if v is not None else f"{k}=silent" for k, v in scores.items())
        if valid:
            best = min(valid, key=valid.get)
            others = [v for k, v in valid.items() if k != best]
            if valid[best] < 0.9 and all(v >= valid[best] * 1.5 for v in others):
                return WireFormat(best, self.sample_rate)  # type: ignore[arg-type]
        # Quiet linear PCM decodes to near-zero samples, while the same bytes read as G.711 are loud (the high byte
        # alternates between 0x00 and 0xFF). Real G.711 silence decodes to near zero instead.
        if scores["pcm16le"] is None:
            loud_as_g711 = min(np.std(mulaw_to_pcm16(window).astype(np.float64)),
                               np.std(alaw_to_pcm16(window).astype(np.float64))) > 1000
            if loud_as_g711:
                self.reason += " (quiet linear PCM)"
                return WireFormat("pcm16le", self.sample_rate)
        return None
