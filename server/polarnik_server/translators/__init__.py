"""Translator registry."""

from __future__ import annotations

import logging
from typing import Any

from .anthropic_tr import AnthropicTranslator
from .base import Translator, TranslatorInfo  # noqa: F401
from .deepl_tr import DeepLTranslator
from .google_free import GoogleFreeTranslator
from .openai_compat import OpenAICompatTranslator

log = logging.getLogger(__name__)

TRANSLATOR_CLASSES: dict[str, type[Translator]] = {
    cls.type: cls for cls in (OpenAICompatTranslator, AnthropicTranslator, DeepLTranslator, GoogleFreeTranslator)
}


def _catalog_type(tid: str) -> str | None:
    from ..catalog import TRANSLATORS

    return (TRANSLATORS.get(tid) or {}).get("type")


def build_translators(translators_cfg: dict[str, Any]) -> tuple[dict[str, Translator], str]:
    """Instantiate enabled translators. Returns (translators, default_id)."""
    out: dict[str, Translator] = {}
    default = str((translators_cfg or {}).get("default", "youtube"))
    for tid, cfg in (translators_cfg or {}).items():
        if tid == "default" or not isinstance(cfg, dict):
            continue
        if not cfg.get("enabled", False):
            continue
        type_id = str(cfg.get("type") or _catalog_type(tid) or tid)
        cls = TRANSLATOR_CLASSES.get(type_id)
        if cls is None:
            log.warning("Unknown translator type for '%s' - skipped", tid)
            continue
        tr = cls(tid, cfg)
        out[tid] = tr
        ready, reason = tr.info().ready, tr.info().reason
        log.info("Translator %-10s %s%s", tid, "ready" if ready else "NOT ready", f" ({reason})" if reason else "")
    # Built-in free Google Translate: always available (fallback when YouTube's own
    # auto-translation is rate limited) unless explicitly disabled in config.yaml.
    gcfg = (translators_cfg or {}).get("google")
    if "google" not in out and not (isinstance(gcfg, dict) and gcfg.get("enabled") is False):
        out["google"] = GoogleFreeTranslator("google", {})
    return out, default
