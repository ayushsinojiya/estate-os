"""G.711 μ-law and small audio helpers (telephony is 8 kHz μ-law)."""

from __future__ import annotations

import struct

import numpy as np

BIAS = 0x84
CLIP = 32635
MULAW_SILENCE = 0xFF
_EXP_LUT = np.array([0, 0, 1, 1, 2, 2, 2, 2] + [3] * 8 + [4] * 16 + [5] * 32 + [6] * 64 + [7] * 128, dtype=np.int32)


def _decode_table() -> np.ndarray:
    table = np.zeros(256, dtype=np.int16)
    for code in range(256):
        u = ~code & 0xFF
        exponent = (u >> 4) & 0x07
        mantissa = u & 0x0F
        sample = (((mantissa << 3) + BIAS) << exponent) - BIAS
        table[code] = -sample if u & 0x80 else sample
    return table


def _encode_table() -> np.ndarray:
    samples = np.arange(-32768, 32768, dtype=np.int32)
    sign = np.where(samples < 0, 0x80, 0)
    magnitude = np.minimum(np.abs(samples), CLIP) + BIAS
    exponent = _EXP_LUT[(magnitude >> 7) & 0xFF]
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8)


_DECODE = _decode_table()
_ENCODE = _encode_table()

ALAW_SILENCE = 0xD5
_ALAW_SEG_END = np.array([0x1F, 0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF], dtype=np.int32)


def _alaw_decode_table() -> np.ndarray:
    table = np.zeros(256, dtype=np.int16)
    for code in range(256):
        a = code ^ 0x55
        t = (a & 0x0F) << 4
        seg = (a & 0x70) >> 4
        if seg == 0:
            t += 8
        else:
            t = (t + 0x108) << (seg - 1)
        table[code] = t if a & 0x80 else -t
    return table


def _alaw_encode_table() -> np.ndarray:
    samples = np.arange(-32768, 32768, dtype=np.int32) >> 3
    mask = np.where(samples >= 0, 0xD5, 0x55)
    magnitude = np.where(samples >= 0, samples, -samples - 1)
    seg = np.searchsorted(_ALAW_SEG_END, magnitude, side="left")
    shift = np.where(seg < 2, 1, seg)
    aval = (np.minimum(seg, 7) << 4) | ((magnitude >> shift) & 0x0F)
    aval = np.where(seg >= 8, 0x7F, aval)
    return ((aval ^ mask) & 0xFF).astype(np.uint8)


_ALAW_DECODE = _alaw_decode_table()
_ALAW_ENCODE = _alaw_encode_table()


def alaw_to_pcm16(data: bytes) -> np.ndarray:
    return _ALAW_DECODE[np.frombuffer(data, dtype=np.uint8)]


def pcm16_to_alaw(samples: np.ndarray) -> bytes:
    return _ALAW_ENCODE[samples.astype(np.int32) + 32768].tobytes()


def upsample(samples: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate or len(samples) == 0:
        return samples.astype(np.int16)
    positions = np.arange(0, len(samples), from_rate / to_rate)
    return np.interp(positions, np.arange(len(samples)), samples.astype(np.float32)).astype(np.int16)


def mulaw_to_pcm16(data: bytes) -> np.ndarray:
    return _DECODE[np.frombuffer(data, dtype=np.uint8)]


def pcm16_to_mulaw(samples: np.ndarray | bytes) -> bytes:
    if isinstance(samples, (bytes, bytearray)):
        samples = np.frombuffer(samples, dtype="<i2")
    return _ENCODE[samples.astype(np.int32) + 32768].tobytes()


def apply_gain_mulaw(data: bytes, gain: float) -> bytes:
    """Scale μ-law audio by a linear gain, clipping rather than wrapping.

    Telephony carriers give no headroom back, so a quiet TTS voice stays quiet on the line. The
    scaling happens in the PCM domain because μ-law is logarithmic and cannot be scaled directly.
    """
    if gain == 1.0 or not data:
        return data
    pcm = mulaw_to_pcm16(data).astype(np.float32) * gain
    np.clip(pcm, -32768.0, 32767.0, out=pcm)
    return pcm16_to_mulaw(pcm.astype(np.int16))


def downsample(samples: np.ndarray, from_rate: int, to_rate: int = 8000) -> np.ndarray:
    if from_rate == to_rate:
        return samples.astype(np.int16)
    x = samples.astype(np.float32)
    if from_rate % to_rate == 0:
        factor = from_rate // to_rate
        usable = len(x) // factor * factor
        return x[:usable].reshape(-1, factor).mean(axis=1).astype(np.int16)
    positions = np.arange(0, len(x), from_rate / to_rate)
    return np.interp(positions, np.arange(len(x)), x).astype(np.int16)


def parse_wav(data: bytes) -> tuple[int, int, int, bytes]:
    """Return (audio_format, sample_rate, bits_per_sample, data). audio_format 1=PCM, 7=μ-law."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, payload = 12, None, None
    while pos + 8 <= len(data):
        chunk_id, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if chunk_id == b"fmt ":
            audio_format, _channels, sample_rate, _byte_rate, _align, bits = struct.unpack("<HHIIHH", body[:16])
            fmt = (audio_format, sample_rate, bits)
        elif chunk_id == b"data":
            payload = body
        pos += 8 + size + (size & 1)
    if fmt is None or payload is None:
        raise ValueError("incomplete WAV file")
    return fmt[0], fmt[1], fmt[2], payload


def to_mulaw_8k(audio: bytes) -> bytes:
    """Accept raw μ-law or a WAV container (μ-law or PCM16) and return raw 8 kHz μ-law."""
    if audio[:4] != b"RIFF":
        return audio
    audio_format, rate, bits, payload = parse_wav(audio)
    if audio_format == 7 and rate == 8000:
        return payload
    if audio_format == 1 and bits == 16:
        return pcm16_to_mulaw(downsample(np.frombuffer(payload, dtype="<i2"), rate))
    raise ValueError(f"unsupported WAV encoding format={audio_format} rate={rate} bits={bits}")
