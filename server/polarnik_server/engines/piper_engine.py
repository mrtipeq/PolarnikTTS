"""Piper (rhasspy / OHF-Voice piper1-gpl) - fast CPU engine, one downloadable voice per file.

Install: pip install -e ".[piper]"
Voices:  python scripts/download_models.py piper  (or python -m piper.download_voices ...)
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

from ..languages import LANGUAGES
from .base import AudioResult, Engine, Voice

# voice file stem -> (label, language code), from the per-language catalog
KNOWN_VOICES = {vid: (label, lang) for lang, meta in LANGUAGES.items() for vid, label, _mb in meta["piper"]}


def voice_lang(stem: str) -> str:
    """Language of a Piper voice: catalog entry, else the locale prefix of its name (de_DE-... -> de)."""
    if stem in KNOWN_VOICES:
        return KNOWN_VOICES[stem][1]
    prefix = stem.split("-")[0].split("_")[0].lower()
    return prefix if prefix in LANGUAGES else ""


class PiperEngine(Engine):
    id = "piper"
    name = "Piper (CPU, fast, basic quality)"
    kind = "local-cpu"
    licence = "MIT / GPL (piper1-gpl)"

    def __init__(self, cfg, models_dir):
        super().__init__(cfg, models_dir)
        self._voices: dict[str, object] = {}

    @property
    def voices_dir(self) -> Path:
        v = self.cfg.get("voices_dir")
        return Path(v) if v and Path(v).is_absolute() else (Path(self.models_dir) / "piper")

    def check(self) -> tuple[bool, str]:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "piper-tts not installed (pip install -e \".[piper]\")"
        if not self._available_voice_files():
            return False, f"no *.onnx voices in {self.voices_dir} (run scripts/download_models.py piper)"
        return True, ""

    def _available_voice_files(self) -> list[Path]:
        if not self.voices_dir.exists():
            return []
        return sorted(p for p in self.voices_dir.glob("*.onnx") if p.with_suffix(".onnx.json").exists())

    def voices(self) -> list[Voice]:
        return [Voice(p.stem, KNOWN_VOICES.get(p.stem, (p.stem, ""))[0], voice_lang(p.stem))
                for p in self._available_voice_files()]

    @property
    def default_voice(self) -> str:
        v = self.cfg.get("default_voice")
        if v:
            return v
        files = self._available_voice_files()
        return files[0].stem if files else ""

    def _get_voice(self, voice_id: str):
        if voice_id not in self._voices:
            from piper import PiperVoice

            path = self.voices_dir / f"{voice_id}.onnx"
            if not path.exists():
                raise FileNotFoundError(f"Piper voice not found: {path}")
            self._voices[voice_id] = PiperVoice.load(str(path))
        return self._voices[voice_id]

    def synthesize_sync(self, text: str, voice: str, speed: float, lang: str = "pl") -> AudioResult:
        from piper import SynthesisConfig

        pv = self._get_voice(voice or self.default_voice_for(lang))
        syn = SynthesisConfig(length_scale=1.0 / max(speed, 0.2))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            pv.synthesize_wav(text, wf, syn_config=syn)
        data = buf.getvalue()
        with wave.open(io.BytesIO(data), "rb") as wf:
            duration = wf.getnframes() / float(wf.getframerate())
            sr = wf.getframerate()
        return AudioResult(data=data, mime="audio/wav", sample_rate=sr, duration=duration)
