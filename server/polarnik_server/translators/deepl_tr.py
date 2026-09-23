"""DeepL API translator (free or pro endpoint). Does not restore punctuation."""

from __future__ import annotations

import httpx

from ..languages import LANGUAGES
from .base import Translator


class DeepLTranslator(Translator):
    type = "deepl"
    name = "DeepL"
    restores_punctuation = False

    def check(self) -> tuple[bool, str]:
        if not self.cfg.get("api_key"):
            return False, "api_key not set"
        return True, ""

    async def translate(self, sentences, source_lang, context_before, context_after, target_lang="pl"):
        if not sentences:
            return []
        deepl_target = LANGUAGES.get(target_lang, {}).get("deepl")
        if not deepl_target:
            raise RuntimeError(f"DeepL does not support the target language '{target_lang}' - pick an LLM translator")
        url = str(self.cfg.get("base_url", "https://api-free.deepl.com")).rstrip("/") + "/v2/translate"
        body = {
            "text": sentences,
            "target_lang": deepl_target,
            "context": " ".join(context_before[-5:] + context_after[:5]) or None,
            "split_sentences": "nonewlines",
        }
        if source_lang and source_lang != "auto":
            body["source_lang"] = source_lang.upper()[:2]
        body = {k: v for k, v in body.items() if v is not None}
        headers = {"Authorization": f"DeepL-Auth-Key {self.cfg['api_key']}"}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
        out = [t["text"] for t in r.json().get("translations", [])]
        if len(out) != len(sentences):
            raise ValueError(f"DeepL returned {len(out)} translations for {len(sentences)} inputs")
        return out
