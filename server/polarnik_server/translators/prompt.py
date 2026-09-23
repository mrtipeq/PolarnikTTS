"""Shared LLM prompt for subtitle translation into spoken text of the target language."""

from __future__ import annotations

import json
import re

SYSTEM_PROMPT_TEMPLATE = """You translate YouTube subtitle segments into natural spoken {language} for a voice-over narration (the "lektor" style: one calm narrator reading over the original audio).

Rules:
- Translate each numbered segment into fluent, natural {language} as a speaker would say it - natural word order, no literal calques, idioms rendered by {language} equivalents.
- The source is often auto-generated captions without punctuation or casing. Restore proper {language} punctuation and sentence boundaries inside each segment so a text-to-speech engine can intonate it.
- Numbers, units, abbreviations and symbols: write them the way they are read aloud in {language} where it helps TTS (e.g. in Polish "5 km/h" -> "pięć kilometrów na godzinę"; "USB-C" stays "USB-C").
- Keep names, product names and code identifiers unchanged.
- Keep the segment count and order EXACTLY. Never merge or split segments. If a segment is empty or music/noise tags like [Music], return an empty string for it.
- Keep each translation roughly as long as the original so it fits the same time slot; prefer concise phrasing.
- Context segments (before/after) are given only for reference - do NOT translate them, do NOT include them in the output.
- Output ONLY a JSON array of strings, one per segment, nothing else."""


def system_prompt(target_lang: str = "pl") -> str:
    from ..languages import language_name

    return SYSTEM_PROMPT_TEMPLATE.replace("{language}", language_name(target_lang))


SYSTEM_PROMPT = system_prompt("pl")   # backwards compatibility


def build_user_prompt(sentences: list[str], source_lang: str,
                      context_before: list[str], context_after: list[str], target_lang: str = "pl") -> str:
    from ..languages import language_name

    parts = [f"Source language: {source_lang or 'auto'}. Target language: {language_name(target_lang)} ({target_lang})."]
    if context_before:
        parts.append("Context before (do not translate):\n" + "\n".join(context_before[-5:]))
    parts.append("Segments to translate:\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences)))
    if context_after:
        parts.append("Context after (do not translate):\n" + "\n".join(context_after[:5]))
    parts.append(f"Return a JSON array with exactly {len(sentences)} strings.")
    return "\n\n".join(parts)


def parse_json_array(text: str, expected: int) -> list[str]:
    """Extract a JSON array of strings from an LLM reply; tolerate code fences and chatter."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array in model reply")
    arr = json.loads(text[start:end + 1])
    if not isinstance(arr, list):
        raise ValueError("reply is not a JSON array")
    arr = [("" if x is None else str(x)) for x in arr]
    if len(arr) != expected:
        raise ValueError(f"expected {expected} translations, got {len(arr)}")
    return arr
