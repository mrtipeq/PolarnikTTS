"""Any OpenAI-compatible chat completions endpoint: OpenAI, Gemini (OpenAI mode), Ollama, OpenRouter, LM Studio..."""

from __future__ import annotations

import re

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
        base = str(self.cfg["base_url"]).rstrip("/")
        url = base + "/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=float(self.cfg.get("timeout", 90))) as client:
                r = await client.post(url, headers=headers, json=body)
        except httpx.ConnectError as exc:
            raise RuntimeError(f"cannot connect to {base} ({exc}) - is the service running?") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"no answer from {base} within {self.cfg.get('timeout', 90)} s "
                               f"(model too slow for this machine? try a smaller one)") from exc
        if r.status_code >= 400:
            raise RuntimeError(self._describe_error(r))
        content = r.json()["choices"][0]["message"]["content"]
        return parse_json_array(content, len(sentences))

    def _describe_error(self, r: httpx.Response) -> str:
        """Turn an HTTP error into something a user can act on (the body carries the reason)."""
        model = self.cfg.get("model", "?")
        msg = ""
        try:
            err = r.json().get("error")
            if isinstance(err, dict):
                code = err.get("code") or err.get("type") or err.get("status") or ""
                msg = str(err.get("message") or "")
                if code in ("insufficient_quota", "credit_balance_exhausted"):
                    return f"HTTP 429: no credits on the account - top up billing for this API key"
            elif isinstance(err, str):
                msg = err
        except Exception:  # noqa: BLE001
            msg = r.text[:300]
        low = msg.lower()
        # Ollama: "model 'x' not found" / "model 'x' not found, try pulling it first"
        if "try pulling" in low or re.search(r"model '[^']+' not found", low):
            return f"HTTP 404: model '{model}' is not pulled in Ollama - click 'Pobierz model' or run: ollama pull {model}"
        if r.status_code in (401, 403):
            return f"HTTP {r.status_code}: invalid or missing API key" + (f" ({msg[:160]})" if msg else "")
        if r.status_code == 404:
            return f"HTTP 404: model '{model}' not found at this endpoint" + (f" ({msg[:200]})" if msg else "")
        if r.status_code == 429:
            return "HTTP 429: rate limit or quota exceeded" + (f" ({msg[:200]})" if msg else "")
        return f"HTTP {r.status_code}" + (f": {msg[:300]}" if msg else "")
