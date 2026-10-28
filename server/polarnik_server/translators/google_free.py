"""Google Translate through its free web endpoint (no API key, unofficial).

Built in and enabled by default: it is the fallback when YouTube refuses its own
auto-translation (HTTP 429 "too many requests") and the user has no other translator.
Quality is that of translate.google.com; it does not restore punctuation of auto captions.
Disable with `translators: {google: {enabled: false}}` in config.yaml.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ..languages import LANGUAGES
from .base import Translator

log = logging.getLogger(__name__)

URL = "https://translate.googleapis.com/translate_a/single"
# YouTube tlang codes are Google codes except for these
GOOGLE_CODES = {"zh-Hans": "zh-CN", "zh-Hant": "zh-TW"}


def google_code(lang: str) -> str:
    code = (LANGUAGES.get(lang) or {}).get("youtube") or lang
    return GOOGLE_CODES.get(code, code)


BLOCK_COOLDOWN_S = 15 * 60


class GoogleBlocked(RuntimeError):
    """Google answered with its "unusual traffic" check (redirect to /sorry) or HTTP 429."""


class GoogleFreeTranslator(Translator):
    type = "google_free"
    name = "Google Translate (free, no key)"
    restores_punctuation = False
    # When Google starts asking for a captcha we respect it: no requests for a while, the
    # user gets a clear message and can switch to a translator with its own key or a local one.
    blocked_until = 0.0

    def check(self) -> tuple[bool, str]:
        left = GoogleFreeTranslator.blocked_until - time.time()
        if left > 0:
            return False, f"blocked by Google for this network (captcha), retry in {int(left // 60) + 1} min"
        return True, ""

    def _blocked(self, why: str) -> GoogleBlocked:
        GoogleFreeTranslator.blocked_until = time.time() + BLOCK_COOLDOWN_S
        log.warning("google: %s - pausing the free Google translator for %d min", why, BLOCK_COOLDOWN_S // 60)
        return GoogleBlocked(
            f"Google Translate blocked requests from this network ({why}). It asks for a captcha, which "
            "PolarnikTTS does not bypass. Use a translator with your own key (DeepL free tier, Gemini, "
            "OpenAI) or a local one (Ollama/Bielik), or try again later.")

    async def _one(self, client: httpx.AsyncClient, text: str, source: str, target: str) -> str:
        if GoogleFreeTranslator.blocked_until > time.time():
            raise GoogleBlocked(self.check()[1])
        r = await client.post(URL, data={"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text})
        if r.status_code == 429:
            raise self._blocked("HTTP 429 too many requests")
        if r.is_redirect and "/sorry" in r.headers.get("location", ""):
            raise self._blocked("redirect to google.com/sorry")
        r.raise_for_status()
        data = r.json()
        return "".join(part[0] for part in (data[0] or []) if part and part[0])

    async def translate(self, sentences, source_lang, context_before, context_after, target_lang="pl"):
        if not sentences:
            return []
        source = "auto" if not source_lang or source_lang == "auto" else source_lang.split("-")[0]
        target = google_code(target_lang)
        clean = [" ".join(s.split()) for s in sentences]
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            # one request for the whole batch: lines stay lines
            joined = await self._one(client, "\n".join(clean), source, target)
            out = [x.strip() for x in joined.split("\n")]
            if len(out) == len(sentences):
                return out
            log.info("google: %d lines back for %d sentences - translating one by one", len(out), len(sentences))
            sem = asyncio.Semaphore(4)

            async def single(text: str) -> str:
                async with sem:
                    return (await self._one(client, text, source, target)).strip()

            return list(await asyncio.gather(*(single(s) for s in clean)))
