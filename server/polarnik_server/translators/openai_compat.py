"""Any OpenAI-compatible chat completions endpoint: OpenAI, Gemini (OpenAI mode), Ollama, OpenRouter, LM Studio..."""

from __future__ import annotations

import httpx

from .base import Translator
from .prompt import SYSTEM_PROMPT, build_user_prompt, parse_json_array


class OpenAICompatTranslator(Translator):
    type = "openai_compat"
    restores_punctuation = True

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"LLM {self.cfg.get('model', '?')} @ {self.cfg.get('base_url', '?')}"

    def check(self) -> tuple[bool, str]:
        if not self.cfg.get("base_url"):
            return False, "base_url not set"
        if not self.cfg.get("model"):
            return False, "model not set"
        return True, ""

    async def translate(self, sentences, source_lang, context_before, context_after):
        if not sentences:
            return []
        headers = {"Content-Type": "application/json"}
        if self.cfg.get("api_key"):
            headers["Authorization"] = f"Bearer {self.cfg['api_key']}"
        body = {
            "model": self.cfg["model"],
            "temperature": float(self.cfg.get("temperature", 0.2)),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(sentences, source_lang, context_before, context_after)},
            ],
        }
        url = str(self.cfg["base_url"]).rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=float(self.cfg.get("timeout", 90))) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return parse_json_array(content, len(sentences))
