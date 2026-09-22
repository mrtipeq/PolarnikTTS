"""Shared LLM prompt for subtitle translation into spoken Polish."""

from __future__ import annotations

import json
import re

SYSTEM_PROMPT = """You translate YouTube subtitle segments into natural spoken Polish for a voice-over (Polish "lektor" style).

Rules:
- Translate each numbered segment into fluent, natural Polish as a speaker would say it - natural word order, no literal calques, idioms rendered by Polish equivalents.
- The source is often auto-generated captions without punctuation or casing. Restore proper Polish punctuation and sentence boundaries inside each segment so a text-to-speech engine can intonate it.
- Numbers, units, abbreviations and symbols: write them the way they are read aloud in Polish where it helps TTS (e.g. "5 km/h" -> "pięć kilometrów na godzinę", "USB-C" stays "USB-C").
- Keep names, product names and code identifiers unchanged.
- Keep the segment count and order EXACTLY. Never merge or split segments. If a segment is empty or music/noise tags like [Music], return an empty string for it.
- Keep each translation roughly as long as the original so it fits the same time slot; prefer concise phrasing.
- Context segments (before/after) are given only for reference - do NOT translate them, do NOT include them in the output.
- Output ONLY a JSON array of strings, one per segment, nothing else."""


def build_user_prompt(sentences: list[str], source_lang: str,
                      context_before: list[str], context_after: list[str]) -> str:
    parts = [f"Source language: {source_lang or 'auto'}"]
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
