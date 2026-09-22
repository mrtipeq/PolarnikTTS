"""Voice samples for cloning engines: uploaded WAV/MP3 files stored as mono WAV in server/voices."""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_PREFIX = "sample:"
MAX_SECONDS = 30.0


def samples_dir(server_dir: Path) -> Path:
    d = server_dir / "voices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^\w\-. ]+", "_", stem, flags=re.UNICODE).strip(" .") or "sample"
    return stem[:60] + ".wav"


def list_samples(server_dir: Path) -> list[dict]:
    out = []
    for p in sorted(samples_dir(server_dir).glob("*.wav")):
        try:
            info = sf.info(str(p))
            seconds = round(info.frames / float(info.samplerate), 1)
        except Exception:  # noqa: BLE001
            seconds = None
        out.append({"name": p.name, "path": str(p), "seconds": seconds, "voice_id": SAMPLE_PREFIX + p.name})
    return out


def store_sample(server_dir: Path, name: str, data: bytes) -> dict:
    """Decode any format soundfile understands, mix down to mono, save as 16-bit WAV."""
    audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    seconds = len(mono) / float(sr)
    if seconds > MAX_SECONDS:
        mono = mono[: int(MAX_SECONDS * sr)]
        seconds = MAX_SECONDS
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    if peak > 0:
        mono = mono / peak * 0.9
    target = samples_dir(server_dir) / safe_name(name)
    sf.write(str(target), mono, sr, subtype="PCM_16")
    return {"name": target.name, "path": str(target), "seconds": round(seconds, 1), "voice_id": SAMPLE_PREFIX + target.name}


def sample_path(server_dir: Path, voice_id_or_name: str) -> Path | None:
    name = voice_id_or_name[len(SAMPLE_PREFIX):] if voice_id_or_name.startswith(SAMPLE_PREFIX) else voice_id_or_name
    p = samples_dir(server_dir) / Path(name).name
    return p if p.exists() else None
