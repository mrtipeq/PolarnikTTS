"""Engine registry. Add a new engine: create a module with an Engine subclass and list it here."""

from __future__ import annotations

import logging
from typing import Any

from .base import AudioResult, Engine, EngineInfo, Voice  # noqa: F401

log = logging.getLogger(__name__)

# Engine modules are imported lazily: the isolated workers (chatterbox, xtts) import this
# package from a virtualenv that has neither httpx (cloud engines) nor edge-tts/piper, so an
# eager import of every engine here would break them.
_ENGINE_MODULES: dict[str, tuple[str, str]] = {
    "test_tone": ("test_tone", "TestToneEngine"),
    "edge_tts": ("edge_tts_engine", "EdgeTtsEngine"),
    "piper": ("piper_engine", "PiperEngine"),
    "chatterbox": ("chatterbox_engine", "ChatterboxEngine"),
    "xtts": ("xtts_engine", "XttsEngine"),
    "elevenlabs": ("elevenlabs_engine", "ElevenLabsEngine"),
    "openai_tts": ("openai_tts_engine", "OpenAITtsEngine"),
    "gemini_tts": ("gemini_tts_engine", "GeminiTtsEngine"),
}

# Engines that run in their own virtualenv/process (see isolated_engine.py).
ISOLATED_IDS = ("chatterbox", "xtts")


def engine_class(type_id: str) -> type[Engine] | None:
    """Import and return the Engine subclass for a catalog id (None when unknown)."""
    entry = _ENGINE_MODULES.get(type_id)
    if entry is None:
        return None
    import importlib

    module = importlib.import_module(f".{entry[0]}", __name__)
    return getattr(module, entry[1])


# Cloud TTS engines that may reuse the API key of the translator of the same provider.
KEY_FROM_TRANSLATOR = {"openai_tts": "openai", "gemini_tts": "gemini"}


def build_engines(engines_cfg: dict[str, dict[str, Any]], models_dir, server_dir=None,
                  translators_cfg: dict[str, Any] | None = None) -> dict[str, Engine]:
    """Instantiate every enabled engine from the config."""
    from pathlib import Path

    server_dir = Path(server_dir) if server_dir else Path(models_dir).parent
    out: dict[str, Engine] = {}
    for engine_id, cfg in (engines_cfg or {}).items():
        cfg = cfg or {}
        if not cfg.get("enabled", False):
            continue
        type_id = cfg.get("type", engine_id)
        if type_id in KEY_FROM_TRANSLATOR and not cfg.get("api_key"):
            tcfg = (translators_cfg or {}).get(KEY_FROM_TRANSLATOR[type_id]) or {}
            if tcfg.get("api_key"):
                cfg = {**cfg, "api_key": tcfg["api_key"]}
        if type_id in ISOLATED_IDS:
            from .isolated_engine import IsolatedEngine

            cfg = {**cfg, "_samples_dir": str(server_dir / "voices")}
            direct = engine_class(type_id)
            assert direct is not None
            engine: Engine = IsolatedEngine(engine_id, cfg, Path(models_dir), server_dir,
                                            name=direct.name, licence=direct.licence,
                                            native_speed=getattr(direct, "native_speed", True))
            engine.langs = list(getattr(direct, "langs", []))
        else:
            cls = engine_class(type_id)
            if cls is None:
                log.warning("Unknown engine '%s' in config - skipped", engine_id)
                continue
            engine = cls(cfg, models_dir)
        engine.id = engine_id
        out[engine_id] = engine
        ready, reason = engine.ensure_ready()
        log.info("Engine %-12s %s%s", engine_id, "ready" if ready else "NOT ready", f" ({reason})" if reason else "")
    return out
