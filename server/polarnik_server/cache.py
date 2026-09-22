"""On-disk cache of synthesized audio keyed by (engine, voice, speed, text)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from .audio import MIME_TO_EXT
from .engines.base import AudioResult

log = logging.getLogger(__name__)


class AudioCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(engine: str, voice: str, speed: float, text: str) -> str:
        payload = f"{engine}\x1f{voice}\x1f{speed:.3f}\x1f{text.strip()}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _paths(self, engine: str, key: str) -> tuple[Path, Path]:
        d = self.root / engine / key[:2]
        return d / f"{key}.json", d

    def get(self, engine: str, key: str) -> AudioResult | None:
        meta_path, _ = self._paths(engine, key)
        if not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            data = (meta_path.parent / meta["file"]).read_bytes()
            return AudioResult(data=data, mime=meta["mime"], sample_rate=meta.get("sample_rate"),
                               duration=meta.get("duration"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Cache entry %s unreadable: %s", key, exc)
            return None

    def put(self, engine: str, key: str, result: AudioResult) -> None:
        meta_path, d = self._paths(engine, key)
        d.mkdir(parents=True, exist_ok=True)
        ext = MIME_TO_EXT.get(result.mime, "bin")
        audio_name = f"{key}.{ext}"
        (d / audio_name).write_bytes(result.data)
        meta_path.write_text(json.dumps({
            "file": audio_name,
            "mime": result.mime,
            "sample_rate": result.sample_rate,
            "duration": result.duration,
        }), encoding="utf-8")
