"""Synthetic engine: produces a short tone whose length depends on the text.

Useful for testing the extension/server/cache pipeline without any TTS dependency.
"""

from __future__ import annotations

import numpy as np

from ..audio import pcm16_to_wav
from .base import AudioResult, Engine, Voice

SAMPLE_RATE = 22050


class TestToneEngine(Engine):
    id = "test_tone"
    name = "Test tone (no speech)"
    kind = "local-cpu"
    licence = "MIT"

    def voices(self) -> list[Voice]:
        return [Voice("beep", "Beep 440 Hz"), Voice("low", "Beep 220 Hz")]

    @property
    def default_voice(self) -> str:
        return self.cfg.get("default_voice") or "beep"

    def synthesize_sync(self, text: str, voice: str, speed: float) -> AudioResult:
        # ~ 60 ms per character at speed 1.0, at least 0.3 s
        seconds = max(0.3, len(text) * 0.06 / max(speed, 0.1))
        freq = 220.0 if voice == "low" else 440.0
        t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
        # gentle amplitude envelope so it does not click
        env = np.minimum(1.0, np.minimum(t / 0.02, (seconds - t) / 0.05))
        samples = 0.3 * env * np.sin(2 * np.pi * freq * t)
        return AudioResult(data=pcm16_to_wav(samples.astype(np.float32), SAMPLE_RATE),
                           mime="audio/wav", sample_rate=SAMPLE_RATE, duration=seconds)
