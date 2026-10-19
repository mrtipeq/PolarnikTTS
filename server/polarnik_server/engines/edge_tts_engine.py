"""Microsoft Edge neural voices through the unofficial edge-tts library (cloud, free).

Very good prosody in every language listed in languages.py (Polish: pl-PL-ZofiaNeural,
pl-PL-MarekNeural). Unofficial API: it may break without notice, keep another engine
configured as fallback.
Install: pip install -e ".[edge]"
"""

from __future__ import annotations

import sys

from ..audio import probe_duration
from ..languages import LANGUAGES
from .base import AudioResult, Engine, Voice

ALL_VOICES = [Voice(vid, label, lang) for lang, meta in LANGUAGES.items() for vid, label in meta["edge"]]


def edge_tts_version() -> str:
    try:
        from importlib.metadata import version

        return version("edge-tts")
    except Exception:  # noqa: BLE001
        return "?"


def describe_error(exc: Exception) -> str:
    """Readable message for the usual failures of the unofficial Edge service."""
    text = f"{type(exc).__name__}: {exc}"
    if "403" in text and ("Handshake" in text or "Invalid response status" in text):
        return (f"Microsoft rejected the connection (HTTP 403). edge-tts {edge_tts_version()} is out of date "
                "for the current Edge service - update it (Options > Engines > Microsoft Edge > Update) "
                f"or run: \"{sys.executable}\" -m pip install -U edge-tts, then restart the server. "
                "If it is already the newest version, check that the system clock is correct.")
    if "Cannot connect" in text or "ClientConnector" in text or "TimeoutError" in text:
        return f"cannot reach speech.platform.bing.com (no internet or blocked by a firewall/proxy): {text}"
    return text


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
        return list(ALL_VOICES)

    @property
    def default_voice(self) -> str:
        return self.cfg.get("default_voice") or "pl-PL-ZofiaNeural"

    @staticmethod
    def _rate_from_speed(speed: float, base: str) -> str:
        base_pct = int(str(base).replace("%", "").replace("+", "") or 0)
        pct = int(round((speed - 1.0) * 100)) + base_pct
        return f"{'+' if pct >= 0 else ''}{pct}%"

    async def synthesize(self, text: str, voice: str, speed: float = 1.0, lang: str = "pl") -> AudioResult:
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice or self.default_voice_for(lang),
            rate=self._rate_from_speed(speed, self.cfg.get("rate", "+0%")),
            pitch=str(self.cfg.get("pitch", "+0Hz")),
        )
        chunks: list[bytes] = []
        last_end_ms = 0.0
        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    # offsets are in 100 ns units
                    last_end_ms = max(last_end_ms, (chunk["offset"] + chunk["duration"]) / 10_000)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(describe_error(exc)) from exc
        data = b"".join(chunks)
        duration = probe_duration(data, "audio/mpeg")
        if duration is None and last_end_ms:
            duration = last_end_ms / 1000.0 + 0.3
        return AudioResult(data=data, mime="audio/mpeg", sample_rate=24000, duration=duration)
