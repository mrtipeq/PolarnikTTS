"""Coqui XTTS-v2 through the maintained `coqui-tts` fork - local GPU, voice cloning.

Model licence: Coqui Public Model License (non-commercial). Fine for personal use.
Install: from the extension options page, or scripts/install_engine.py xtts (isolated venv)
The model (~1.8 GB) downloads on first use into models_dir/tts.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..audio import pcm16_to_wav
from .base import AudioResult, Engine, Voice, cuda_kernel_problem, pick_device

XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
# A few of the built-in studio speakers that sound acceptable in Polish.
BUILTIN_SPEAKERS = ["Ana Florence", "Claribel Dervla", "Daisy Studious", "Andrew Chipper",
                    "Damien Black", "Viktor Eka"]


class XttsEngine(Engine):
    id = "xtts"
    name = "XTTS-v2 (local GPU, cloning)"
    kind = "local-gpu"
    cloning = True
    licence = "CPML (non-commercial)"
    serialize = True

    def __init__(self, cfg, models_dir):
        super().__init__(cfg, models_dir)
        self._tts = None
        self._device = "cpu"

    def check(self) -> tuple[bool, str]:
        try:
            import TTS  # noqa: F401
        except ImportError:
            return False, "coqui-tts not installed (install from the options page or scripts/install_engine.py xtts)"
        self._device = pick_device(str(self.cfg.get("device", "auto")))
        if self._device == "cuda":
            problem = cuda_kernel_problem()
            if problem:
                return False, problem
        if self._device == "cpu":
            return True, "CUDA not available - XTTS on CPU is slow"
        return True, ""

    def _samples(self) -> list[Voice]:
        d = self.cfg.get("_samples_dir")
        if not d or not Path(d).exists():
            return []
        return [Voice(f"sample:{p.name}", f"Sample: {p.stem}") for p in sorted(Path(d).glob("*.wav"))]

    def voices(self) -> list[Voice]:
        return self._samples() + [Voice(s, s) for s in BUILTIN_SPEAKERS]

    @property
    def default_voice(self) -> str:
        return str(self.cfg.get("default_voice") or BUILTIN_SPEAKERS[0])

    def load(self) -> None:
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        os.environ.setdefault("TTS_HOME", str(Path(self.models_dir) / "tts"))
        from TTS.api import TTS

        self._tts = TTS(XTTS_MODEL).to(self._device)

    def synthesize_sync(self, text: str, voice: str, speed: float) -> AudioResult:
        kwargs = {"text": text, "language": "pl", "speed": float(speed)}
        voice = voice or self.default_voice
        if voice.startswith("sample:"):
            kwargs["speaker_wav"] = str(Path(self.cfg.get("_samples_dir", "")) / Path(voice[len("sample:"):]).name)
        elif voice == "speaker_wav" and self.cfg.get("speaker_wav"):   # legacy config key
            kwargs["speaker_wav"] = self.cfg["speaker_wav"]
        else:
            kwargs["speaker"] = voice
        samples = np.asarray(self._tts.tts(**kwargs), dtype=np.float32)
        sr = int(self._tts.synthesizer.output_sample_rate)
        return AudioResult(data=pcm16_to_wav(samples, sr), mime="audio/wav", sample_rate=sr,
                           duration=len(samples) / sr)
