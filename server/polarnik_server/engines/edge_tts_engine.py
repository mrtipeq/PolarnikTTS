"""Microsoft Edge neural voices through the unofficial edge-tts library (cloud, free).

Very good Polish prosody (pl-PL-ZofiaNeural, pl-PL-MarekNeural). Unofficial API:
it may break without notice, keep another engine configured as fallback.
Install: pip install -e ".[edge]"
"""

from __future__ import annotations

from ..audio import probe_duration
from .base import AudioResult, Engine, Voice

POLISH_VOICES = [
    Voice("pl-PL-ZofiaNeural", "Zofia (female)"),
    Voice("pl-PL-MarekNeural", "Marek (male)"),
]


class EdgeTtsEngine(Engine):
    id = "edge_tts"
    name = "Microsoft Edge neural (cloud, unofficial)"
    kind = "cloud"
    streaming = True
    licence = "unofficial API"

    def check(self) -> tuple[bool, str]:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False, "edge-tts not installed (pip install -e \".[edge]\")"
        return True, ""

    def voices(self) -> list[Voice]:
        return list(POLISH_VOICES)

    @property
    def default_voice(self) -> str:
        return self.cfg.get("default_voice") or "pl-PL-ZofiaNeural"

    @staticmethod
    def _rate_from_speed(speed: float, base: str) -> str:
        base_pct = int(str(base).replace("%", "").replace("+", "") or 0)
        pct = int(round((speed - 1.0) * 100)) + base_pct
        return f"{'+' if pct >= 0 else ''}{pct}%"

    async def synthesize(self, text: str, voice: str, speed: float = 1.0) -> AudioResult:
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice or self.default_voice,
            rate=self._rate_from_speed(speed, self.cfg.get("rate", "+0%")),
            pitch=str(self.cfg.get("pitch", "+0Hz")),
        )
        chunks: list[bytes] = []
        last_end_ms = 0.0
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                # offsets are in 100 ns units
                last_end_ms = max(last_end_ms, (chunk["offset"] + chunk["duration"]) / 10_000)
        data = b"".join(chunks)
        duration = probe_duration(data, "audio/mpeg")
        if duration is None and last_end_ms:
            duration = last_end_ms / 1000.0 + 0.3
        return AudioResult(data=data, mime="audio/mpeg", sample_rate=24000, duration=duration)
