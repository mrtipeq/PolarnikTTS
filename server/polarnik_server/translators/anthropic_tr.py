"""Anthropic Messages API translator (Claude Haiku / Sonnet)."""

from __future__ import annotations

import httpx

from .base import Translator
from .prompt import build_user_prompt, parse_json_array, system_prompt

API = "https://api.anthropic.com/v1/messages"


class AnthropicTranslator(Translator):
    type = "anthropic"
    restores_punctuation = True

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"Anthropic {self.cfg.get('model', '?')}"

    def check(self) -> tuple[bool, str]:
        if not self.cfg.get("api_key"):
            return False, "api_key not set"
        if not self.cfg.get("model"):
            return False, "model not set"
        return True, ""

    async def translate(self, sentences, source_lang, context_before, context_after, target_lang="pl"):
        if not sentences:
            return []
        headers = {
            "x-api-key": str(self.cfg["api_key"]),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.cfg["model"],
            "max_tokens": int(self.cfg.get("max_tokens", 4096)),
            "temperature": float(self.cfg.get("temperature", 0.2)),
            "system": system_prompt(target_lang),
            "messages": [{"role": "user",
                          "content": build_user_prompt(sentences, source_lang, context_before, context_after, target_lang)}],
        }
        async with httpx.AsyncClient(timeout=float(self.cfg.get("timeout", 90))) as client:
            r = await client.post(API, headers=headers, json=body)
            r.raise_for_status()
        content = "".join(block.get("text", "") for block in r.json().get("content", []))
        return parse_json_array(content, len(sentences))
