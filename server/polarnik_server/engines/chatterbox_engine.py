"""Resemble AI Chatterbox Multilingual (MIT) - local GPU engine with voice cloning.

Install: from the extension options page, or scripts/install_engine.py chatterbox (isolated venv)
The model (~2 GB) is downloaded from Hugging Face on first use into models_dir/hf.
Known issue: some users report an English accent in Polish output
(resemble-ai/chatterbox#311) - a Polish reference_audio usually helps.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..audio import pcm16_to_wav
from ..languages import LANGUAGES
from .base import AudioResult, Engine, Voice, cuda_kernel_problem, pick_device


class ChatterboxEngine(Engine):
    id = "chatterbox"
    name = "Chatterbox Multilingual (local GPU, cloning)"
    kind = "local-gpu"
    cloning = True
    licence = "MIT"
    serialize = True
    native_speed = False
    langs = [c for c, m in LANGUAGES.items() if m.get("chatterbox")]

    def __init__(self, cfg, models_dir):
        super().__init__(cfg, models_dir)
        self._model = None
        self._device = "cpu"

    def check(self) -> tuple[bool, str]:
        try:
            import chatterbox  # noqa: F401
        except ImportError:
            return False, "chatterbox-tts not installed (install from the options page or scripts/install_engine.py chatterbox)"
        self._device = pick_device(str(self.cfg.get("device", "auto")))
        if self._device == "cuda":
            problem = cuda_kernel_problem()
            if problem:
                return False, problem
        if self._device == "cpu" and str(self.cfg.get("device", "auto")) == "auto":
            return True, "CUDA not available - running on CPU will be very slow"
        return True, ""

    def _samples(self) -> list[Voice]:
        d = self.cfg.get("_samples_dir")
        if not d or not Path(d).exists():
            return []
        return [Voice(f"sample:{p.name}", f"Sample: {p.stem}") for p in sorted(Path(d).glob("*.wav"))]

    def voices(self) -> list[Voice]:
        return [Voice("default", "Built-in voice")] + self._samples()

    @property
    def default_voice(self) -> str:
        v = str(self.cfg.get("default_voice") or "")
        return v if v else "default"

    def _prompt_path(self, voice: str) -> str | None:
        if voice.startswith("sample:"):
            p = Path(self.cfg.get("_samples_dir", "")) / Path(voice[len("sample:"):]).name
            return str(p) if p.exists() else None
        ref = self.cfg.get("reference_audio")            # legacy config key
        return ref if voice == "reference" and ref and Path(ref).exists() else None

    def load(self) -> None:
        os.environ.setdefault("HF_HOME", str(Path(self.models_dir) / "hf"))
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        self._model = ChatterboxMultilingualTTS.from_pretrained(device=self._device)

    def synthesize_sync(self, text: str, voice: str, speed: float, lang: str = "pl") -> AudioResult:
        import torch

        kwargs = {
            "language_id": LANGUAGES.get(lang, {}).get("chatterbox") or "en",
            "exaggeration": float(self.cfg.get("exaggeration", 0.5)),
            "cfg_weight": float(self.cfg.get("cfg_weight", 0.5)),
        }
        prompt = self._prompt_path(voice or self.default_voice)
        if prompt:
            kwargs["audio_prompt_path"] = prompt
        with torch.inference_mode():
            wav = self._model.generate(text, **kwargs)
        samples = wav.squeeze(0).cpu().numpy()
        sr = int(self._model.sr)
        # Chatterbox has no speed parameter; speed is handled client-side (time-stretch).
        return AudioResult(data=pcm16_to_wav(samples, sr), mime="audio/wav", sample_rate=sr,
                           duration=len(samples) / sr)
