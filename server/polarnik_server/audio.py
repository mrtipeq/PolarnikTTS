"""Small audio helpers shared by engines, cache and bench."""

from __future__ import annotations

import io
import wave

import numpy as np

MIME_TO_EXT = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
}


def pcm16_to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode a mono float32/-1..1 or int16 numpy array into a WAV container."""
    if samples.dtype != np.int16:
        clipped = np.clip(samples.astype(np.float32), -1.0, 1.0)
        samples = (clipped * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def raw_pcm16_to_wav(raw: bytes, sample_rate: int) -> bytes:
    """Wrap raw little-endian 16-bit mono PCM bytes into a WAV container."""
    return pcm16_to_wav(np.frombuffer(raw, dtype=np.int16), sample_rate)


def probe_duration(data: bytes, mime: str) -> float | None:
    """Return the duration in seconds, or None when the format cannot be decoded."""
    try:
        if mime in ("audio/wav", "audio/x-wav"):
            with wave.open(io.BytesIO(data), "rb") as wf:
                return wf.getnframes() / float(wf.getframerate())
        import soundfile as sf  # libsndfile >= 1.1 decodes MP3/OGG too

        info = sf.info(io.BytesIO(data))
        return float(info.frames) / float(info.samplerate)
    except Exception:  # noqa: BLE001 - probing is best effort
        return None
