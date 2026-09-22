"""OpenAI text-to-speech (gpt-4o-mini-tts / tts-1) through the REST API - cloud, paid.

The voices are multilingual: any of them reads Polish text. `instructions` (gpt-4o-mini-tts
only) steer the delivery; the default asks for a natural Polish voice-over narrator.
Uses the same API key as the OpenAI translator when the engine has no key of its own.
"""

from __future__ import annotations

import httpx

from ..audio import probe_duration
from .base import AudioResult, Engine, Voice

API = "https://api.openai.com/v1/audio/speech"
VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse", "marin", "cedar"]
DEFAULT_INSTRUCTIONS = ("Read the text in natural, fluent Polish with native pronunciation, calm and clear, "
                        "like a professional Polish voice-over narrator (lektor). Do not translate or add anything.")


class OpenAITtsEngine(Engine):
    id = "openai_tts"
    name = "OpenAI TTS (cloud, paid)"
    kind = "cloud"
    streaming = True
    licence = "commercial API"

    def check(self) -> tuple[bool, str]:
        if not self.cfg.get("api_key"):
            return False, "api_key not set (or enter it for the OpenAI translator)"
        return True, ""

    def voices(self) -> list[Voice]:
        return [Voice(v, v) for v in VOICES]

    @property
    def default_voice(self) -> str:
        return str(self.cfg.get("default_voice") or "marin")

    async def synthesize(self, text: str, voice: str, speed: float = 1.0) -> AudioResult:
        model = str(self.cfg.get("model_id") or "gpt-4o-mini-tts")
        body: dict = {
            "model": model,
            "voice": voice or self.default_voice,
            "input": text,
            "response_format": "mp3",
            "speed": float(min(max(speed, 0.25), 4.0)),
        }
        if not model.startswith("tts-1"):
            body["instructions"] = str(self.cfg.get("instructions") or DEFAULT_INSTRUCTIONS)
        headers = {"Authorization": f"Bearer {self.cfg['api_key']}", "Content-Type": "application/json"}
        base = str(self.cfg.get("base_url") or "").rstrip("/")
        url = f"{base}/audio/speech" if base else API
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(url, headers=headers, json=body)
            if r.status_code >= 400:
                detail = r.text[:300]
                try:
                    err = r.json().get("error", {})
                    code = err.get("code") or err.get("type") or ""
                    if code in ("insufficient_quota", "credit_balance_exhausted"):
                        detail = "no credits on the OpenAI account - top up at platform.openai.com/settings/organization/billing"
                    elif r.status_code == 401:
                        detail = "invalid API key"
                    elif err.get("message"):
                        detail = err["message"][:200]
                except Exception:  # noqa: BLE001
                    pass
                raise RuntimeError(f"OpenAI TTS HTTP {r.status_code}: {detail}")
        return AudioResult(data=r.content, mime="audio/mpeg", duration=probe_duration(r.content, "audio/mpeg"))
