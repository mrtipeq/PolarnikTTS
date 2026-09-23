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
    lang: str = ""               # LANGUAGES code the voice speaks; "" = any language (multilingual / cloned)


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
    langs: list[str] = field(default_factory=list)   # target languages the engine can speak; [] = any


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
    # Target languages this engine can speak ([] = anything the voice supports).
    langs: list[str] = []

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

    def default_voice_for(self, lang: str) -> str:
        """Default voice for a target language: the configured one when it speaks that language
        (or is language-neutral), else the first voice of that language, else the plain default."""
        try:
            voices = self.voices()
        except Exception:  # noqa: BLE001
            voices = []
        by_id = {v.id: v for v in voices}
        configured = self.default_voice
        if configured and (configured not in by_id or not by_id[configured].lang or by_id[configured].lang == lang):
            return configured
        for v in voices:
            if v.lang == lang:
                return v.id
        return configured

    def supports_lang(self, lang: str) -> bool:
        return not self.langs or lang in self.langs

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
                          default_voice=self.default_voice, voices=voices, licence=self.licence,
                          langs=list(self.langs))

    # -- synthesis -------------------------------------------------------

    def synthesize_sync(self, text: str, voice: str, speed: float, lang: str = "pl") -> AudioResult:
        raise NotImplementedError

    async def synthesize(self, text: str, voice: str, speed: float = 1.0, lang: str = "pl") -> AudioResult:
        """Default: run the blocking synthesize_sync in a worker thread."""
        if self.serialize:
            async with self._lock:
                return await asyncio.to_thread(self._load_and_run, text, voice, speed, lang)
        return await asyncio.to_thread(self._load_and_run, text, voice, speed, lang)

    _loaded = False

    def _load_and_run(self, text: str, voice: str, speed: float, lang: str = "pl") -> AudioResult:
        if not self._loaded:
            self.load()
            self._loaded = True
        return self.synthesize_sync(text, voice, speed, lang)


def pick_device(requested: str) -> str:
    """Resolve "auto" | "cuda" | "cpu" into a torch device string."""
    if requested in ("cuda", "cpu"):
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


def cuda_kernel_problem() -> str:
    """Return a reason string when the installed torch build has no kernels for GPU 0.

    A CUDA wheel is compiled for a fixed list of architectures (torch.cuda.get_arch_list()).
    Running on a newer GPU - e.g. torch 2.6/cu126 on an RTX 50xx (sm_120, Blackwell) - fails at
    the first kernel launch with "no kernel image is available for execution on the device",
    so detect the mismatch up front and tell the user to reinstall the engine (the installer
    picks a matching build). Empty string = fine (or not applicable).
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return ""
        major, minor = torch.cuda.get_device_capability(0)
        sm = f"sm_{major}{minor}"
        archs = torch.cuda.get_arch_list()
        if not archs or sm in archs:
            return ""
        # A PTX target of the same major version can be JIT-compiled for the device.
        if any(a == f"compute_{major}{minor}" or a.startswith(f"compute_{major}") for a in archs):
            return ""
        name = torch.cuda.get_device_name(0)
        return (f"PyTorch {torch.__version__} has no CUDA kernels for {name} ({sm}; build supports "
                f"{', '.join(a for a in archs if a.startswith('sm_'))}) - reinstall the engine from the "
                f"options page to get a matching PyTorch build")
    except Exception:  # noqa: BLE001
        return ""
