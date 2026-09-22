"""Base classes for TTS engine plugins."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Voice:
    id: str
    name: str


@dataclass
class AudioResult:
    data: bytes
    mime: str
    sample_rate: int | None = None
    duration: float | None = None


@dataclass
class EngineInfo:
    id: str
    name: str
    kind: str                    # "local-cpu" | "local-gpu" | "cloud"
    ready: bool
    reason: str = ""             # why not ready (empty when ready)
    streaming: bool = False
    cloning: bool = False
    native_speed: bool = True    # False: the engine ignores `speed`, the client time-stretches instead
    default_voice: str = ""
    voices: list[Voice] = field(default_factory=list)
    licence: str = ""


class Engine:
    """A TTS backend. Subclasses implement check(), voices() and synthesize()."""

    id: str = "base"
    name: str = "Base engine"
    kind: str = "local-cpu"
    streaming: bool = False
    cloning: bool = False
    licence: str = ""
    native_speed: bool = True
    # Engines that must not run concurrently (GPU models) set this to True.
    serialize: bool = False

    def __init__(self, cfg: dict[str, Any], models_dir):
        self.cfg = cfg or {}
        self.models_dir = models_dir
        self._lock = asyncio.Lock()
        self._ready: bool | None = None
        self._reason = ""

    # -- lifecycle -------------------------------------------------------

    def check(self) -> tuple[bool, str]:
        """Return (ready, reason). Must be cheap; do not load models here."""
        return True, ""

    def ensure_ready(self) -> tuple[bool, str]:
        if self._ready is None:
            try:
                self._ready, self._reason = self.check()
            except Exception as exc:  # noqa: BLE001
                self._ready, self._reason = False, f"{type(exc).__name__}: {exc}"
        return self._ready, self._reason

    def load(self) -> None:
        """Load heavy resources (models). Called lazily before the first synthesis."""

    # -- description -----------------------------------------------------

    def voices(self) -> list[Voice]:
        return []

    @property
    def default_voice(self) -> str:
        return str(self.cfg.get("default_voice") or "")

    def info(self) -> EngineInfo:
        ready, reason = self.ensure_ready()
        voices: list[Voice] = []
        if ready:
            try:
                voices = self.voices()
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: voices() failed: %s", self.id, exc)
        return EngineInfo(id=self.id, name=self.name, kind=self.kind, ready=ready, reason=reason,
                          streaming=self.streaming, cloning=self.cloning, native_speed=self.native_speed,
                          default_voice=self.default_voice, voices=voices, licence=self.licence)

    # -- synthesis -------------------------------------------------------

    def synthesize_sync(self, text: str, voice: str, speed: float) -> AudioResult:
        raise NotImplementedError

    async def synthesize(self, text: str, voice: str, speed: float = 1.0) -> AudioResult:
        """Default: run the blocking synthesize_sync in a worker thread."""
        if self.serialize:
            async with self._lock:
                return await asyncio.to_thread(self._load_and_run, text, voice, speed)
        return await asyncio.to_thread(self._load_and_run, text, voice, speed)

    _loaded = False

    def _load_and_run(self, text: str, voice: str, speed: float) -> AudioResult:
        if not self._loaded:
            self.load()
            self._loaded = True
        return self.synthesize_sync(text, voice, speed)


def pick_device(requested: str) -> str:
    """Resolve "auto" | "cuda" | "cpu" into a torch device string."""
    if requested in ("cuda", "cpu"):
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"
