"""ElevenLabs (cloud, paid) through the plain REST API - no SDK dependency."""

from __future__ import annotations

import httpx

from ..audio import probe_duration
from .base import AudioResult, Engine, Voice

API = "https://api.elevenlabs.io/v1"


class ElevenLabsEngine(Engine):
    id = "elevenlabs"
    name = "ElevenLabs (cloud, paid)"
    kind = "cloud"
    streaming = True
    cloning = True
    licence = "commercial API"

    def __init__(self, cfg, models_dir):
        super().__init__(cfg, models_dir)
        self._voices_cache: list[Voice] | None = None

    def check(self) -> tuple[bool, str]:
        if not self.cfg.get("api_key"):
            return False, "api_key not set"
        return True, ""

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": str(self.cfg["api_key"])}

    def voices(self) -> list[Voice]:
        if self._voices_cache is None:
            try:
                r = httpx.get(f"{API}/voices", headers=self._headers(), timeout=15)
                r.raise_for_status()
                self._voices_cache = [Voice(v["voice_id"], v["name"]) for v in r.json().get("voices", [])]
            except Exception as exc:  # noqa: BLE001
                self._voices_cache = []
                self._reason = f"voices: {exc}"
        return self._voices_cache

    @property
    def default_voice(self) -> str:
        v = self.cfg.get("default_voice")
        if v:
            return v
        voices = self.voices()
        return voices[0].id if voices else ""

    async def synthesize(self, text: str, voice: str, speed: float = 1.0, lang: str = "pl") -> AudioResult:
        voice_id = voice or self.default_voice
        fmt = self.cfg.get("output_format", "mp3_44100_128")
        body = {
            "text": text,
            "model_id": self.cfg.get("model_id", "eleven_flash_v2_5"),
            # ISO 639-1 code; ElevenLabs has no separate Cantonese code
            "language_code": "zh" if lang in ("zh", "yue") else (lang if len(lang) == 2 else None),
            "voice_settings": {"speed": float(min(max(speed, 0.7), 1.2))},
        }
        body = {k: v for k, v in body.items() if v is not None}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{API}/text-to-speech/{voice_id}", params={"output_format": fmt},
                                  headers=self._headers(), json=body)
            r.raise_for_status()
        mime = "audio/mpeg" if fmt.startswith("mp3") else "application/octet-stream"
        return AudioResult(data=r.content, mime=mime, duration=probe_duration(r.content, mime))
