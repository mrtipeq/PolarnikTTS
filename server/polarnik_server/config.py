"""Configuration loading for the PolarnikTTS server."""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "server": {
        "host": "127.0.0.1",
        "port": 8765,
        "token": "",
        "cache_dir": "cache",
        "models_dir": "models",
        "log_level": "info",
    },
    "engines": {
        "test_tone": {"enabled": True},
    },
    "translators": {
        "default": "youtube",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Typed-ish access to the YAML configuration."""

    def __init__(self, data: dict[str, Any], base_dir: Path):
        self.data = data
        self.base_dir = base_dir

    @classmethod
    def load(cls, path: str | os.PathLike | None) -> "Config":
        """Load config.yaml (falls back to defaults when the file is missing)."""
        if path is None:
            candidates = [Path("config.yaml"), Path(__file__).resolve().parent.parent / "config.yaml"]
            path = next((c for c in candidates if c.exists()), None)
        data: dict[str, Any] = {}
        base_dir = Path.cwd()
        if path is not None and Path(path).exists():
            base_dir = Path(path).resolve().parent
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            log.info("Loaded configuration from %s", path)
        else:
            log.warning("No config.yaml found, using built-in defaults (test_tone engine only)")
        return cls(_deep_merge(DEFAULTS, data), base_dir)

    # -- helpers ---------------------------------------------------------

    @property
    def server(self) -> dict[str, Any]:
        return self.data["server"]

    @property
    def engines(self) -> dict[str, dict[str, Any]]:
        return self.data.get("engines") or {}

    @property
    def translators(self) -> dict[str, Any]:
        return self.data.get("translators") or {}

    def resolve(self, rel: str | os.PathLike) -> Path:
        """Resolve a path from the config relative to the config file directory."""
        p = Path(rel)
        return p if p.is_absolute() else (self.base_dir / p)

    @property
    def cache_dir(self) -> Path:
        return self.resolve(self.server.get("cache_dir", "cache"))

    @property
    def models_dir(self) -> Path:
        return self.resolve(self.server.get("models_dir", "models"))
