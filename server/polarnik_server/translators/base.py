"""Base class for translation providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TranslatorInfo:
    id: str
    name: str
    type: str
    ready: bool
    reason: str = ""
    restores_punctuation: bool = False


class Translator:
    type: str = "base"
    name: str = "Base translator"
    restores_punctuation: bool = False

    def __init__(self, translator_id: str, cfg: dict[str, Any]):
        self.id = translator_id
        self.cfg = cfg or {}

    def check(self) -> tuple[bool, str]:
        return True, ""

    def info(self) -> TranslatorInfo:
        try:
            ready, reason = self.check()
        except Exception as exc:  # noqa: BLE001
            ready, reason = False, f"{type(exc).__name__}: {exc}"
        return TranslatorInfo(id=self.id, name=self.name, type=self.type, ready=ready, reason=reason,
                              restores_punctuation=self.restores_punctuation)

    async def translate(self, sentences: list[str], source_lang: str,
                        context_before: list[str], context_after: list[str]) -> list[str]:
        """Translate `sentences` into Polish; must return a list of the same length."""
        raise NotImplementedError
