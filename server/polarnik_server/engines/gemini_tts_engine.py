"""Google Gemini text-to-speech (gemini-*-tts) through generateContent - cloud, paid/free tier.

The response is raw 16-bit PCM at 24 kHz which we wrap into WAV. Polish is supported;
a short style hint in front of the text asks for a natural Polish narrator.
Uses the same API key as the Gemini translator when the engine has no key of its own.
"""

from __future__ import annotations

import base64

import httpx

from ..audio import raw_pcm16_to_wav
from .base import AudioResult, Engine, Voice

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VOICES = ["Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe",
          "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
          "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
          "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"]
DEFAULT_STYLE = "Read naturally in Polish, calm and clear, like a professional voice-over narrator: "


class GeminiTtsEngine(Engine):
    id = "gemini_tts"
    name = "Google Gemini TTS (cloud)"
    kind = "cloud"
    licence = "commercial API"
    native_speed = False

    def check(self) -> tuple[bool, str]:
        if not self.cfg.get("api_key"):
            return False, "api_key not set (or enter it for the Gemini translator)"
        return True, ""

    def voices(self) -> list[Voice]:
        return [Voice(v, v) for v in VOICES]

    @property
    def default_voice(self) -> str:
        return str(self.cfg.get("default_voice") or "Kore")

    async def synthesize(self, text: str, voice: str, speed: float = 1.0) -> AudioResult:
        model = str(self.cfg.get("model_id") or "gemini-3.1-flash-tts-preview")
        style = str(self.cfg.get("style") or DEFAULT_STYLE)   # speed is applied client-side (native_speed=False)
        body = {
            "contents": [{"parts": [{"text": f"{style}{text}"}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice or self.default_voice}}},
            },
        }
        headers = {"x-goog-api-key": str(self.cfg["api_key"]), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(API.format(model=model), headers=headers, json=body)
            if r.status_code >= 400:
                detail = r.text[:300]
                try:
                    msg = r.json().get("error", {}).get("message", "")
                    if msg:
                        detail = msg[:200]
                except Exception:  # noqa: BLE001
                    pass
                raise RuntimeError(f"Gemini TTS HTTP {r.status_code}: {detail}")
        try:
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Gemini TTS: unexpected response {r.text[:200]}") from exc
        raw = base64.b64decode(part["data"])
        rate = 24000
        mime = str(part.get("mimeType", ""))
        if "rate=" in mime:
            try:
                rate = int(mime.split("rate=")[1].split(";")[0])
            except ValueError:
                pass
        data = raw_pcm16_to_wav(raw, rate)
        return AudioResult(data=data, mime="audio/wav", sample_rate=rate, duration=len(raw) / 2 / rate)
