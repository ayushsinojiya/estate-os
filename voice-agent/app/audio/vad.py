"""Local energy VAD on 8 kHz μ-law frames (fast barge-in onset, spec section 23).

Adaptive noise floor with a calibration window. While Riya is speaking the threshold is raised
to reduce false barge-ins from echo. Swap for Silero behind the same interface once the
turn-detection benchmark (C6) decides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.audio.codecs import mulaw_to_pcm16

FRAME_BYTES = 160  # 20 ms at 8 kHz


@dataclass
class VADConfig:
    frame_ms: int = 20
    onset_frames: int = 3
    hangover_frames: int = 6
    margin_db: float = 10.0
    min_db: float = -45.0
    agent_margin_db: float = 6.0
    noise_alpha: float = 0.05
    calibration_frames: int = 10
    # The noise floor never adapts above this: otherwise quiet speech and echo slowly raise it
    # until the caller is no longer detected.
    max_noise_db: float = -50.0


class EnergyVAD:
    def __init__(self, config: VADConfig | None = None):
        self.cfg = config or VADConfig()
        self.noise_db = -60.0
        self.speaking = False
        self.agent_speaking = False
        self._run = 0
        self._silence = 0
        self._frames = 0
        self._buffer = b""

    @staticmethod
    def frame_db(frame: bytes) -> float:
        pcm = mulaw_to_pcm16(frame).astype(np.float32)
        rms = math.sqrt(float(np.mean(pcm * pcm))) if len(pcm) else 0.0
        return 20 * math.log10(rms / 32768 + 1e-9)

    def process(self, mulaw: bytes) -> list[str]:
        """Feed audio; returns 'start' / 'end' events for completed frames."""
        self._buffer += mulaw
        events: list[str] = []
        cfg = self.cfg
        while len(self._buffer) >= FRAME_BYTES:
            frame, self._buffer = self._buffer[:FRAME_BYTES], self._buffer[FRAME_BYTES:]
            db = self.frame_db(frame)
            self._frames += 1
            if self._frames <= cfg.calibration_frames:
                self.noise_db = db if self._frames == 1 else 0.7 * self.noise_db + 0.3 * db
                self.noise_db = min(self.noise_db, cfg.max_noise_db)
                continue
            threshold = max(cfg.min_db, self.noise_db + cfg.margin_db + (cfg.agent_margin_db if self.agent_speaking else 0))
            is_speech = db > threshold
            if not self.speaking:
                if is_speech:
                    self._run += 1
                else:
                    self._run = 0
                    if not self.agent_speaking:  # Riya's echo is not line noise
                        self.noise_db = min(cfg.max_noise_db,
                                            (1 - cfg.noise_alpha) * self.noise_db + cfg.noise_alpha * db)
                if self._run >= cfg.onset_frames:
                    self.speaking, self._silence = True, 0
                    events.append("start")
            else:
                self._silence = 0 if is_speech else self._silence + 1
                if self._silence >= cfg.hangover_frames:
                    self.speaking, self._run = False, 0
                    events.append("end")
        return events
