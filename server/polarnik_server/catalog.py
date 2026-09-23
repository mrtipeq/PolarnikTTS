"""Catalog of installable engines, models and translators for the management API.

The extension renders this (with its own Polish labels); the server only exposes
technical facts: which pip extra installs an engine, which models it needs, which
config fields it has, and whether it wants a GPU.
"""

from __future__ import annotations

from typing import Any

# Piper voices for Polish published in rhasspy/piper-voices.
from .languages import LANGUAGES

# Downloadable Piper voices, one entry per voice, tagged with the language they speak.
PIPER_VOICES = [{"id": vid, "label": label, "size_mb": mb, "lang": lang}
                for lang, meta in LANGUAGES.items() for vid, label, mb in meta["piper"]]
PIPER_PL_VOICES = [v for v in PIPER_VOICES if v["lang"] == "pl"]   # backwards compatibility

ENGINES: dict[str, dict[str, Any]] = {
    "edge_tts": {
        "name": "Microsoft Edge neural (all languages)",
        "extra": "edge",
        "kind": "cloud",
        "gpu": False,
        "models": None,
        "fields": [],
        "download_mb": 1,
        "recommended": True,
    },
    "piper": {
        "name": "Piper (CPU)",
        "extra": "piper",
        "kind": "local-cpu",
        "gpu": False,
        "models": "piper",
        "voices": PIPER_VOICES,
        "fields": [],
        "download_mb": 30,
    },
    "chatterbox": {
        "name": "Chatterbox Multilingual (GPU, cloning)",
        "extra": None,
        # chatterbox-tts pins torch==2.6.0, numpy<2, transformers==5.x - it gets its own venv.
        # On Blackwell GPUs (RTX 50xx) the installer overrides the pin with torch 2.7.1+cu128,
        # the oldest build that has sm_120 kernels (see installer.resolve_torch_spec).
        "isolated": True,
        "packages": ["chatterbox-tts"],
        "torch": {"version": "2.6.0", "cuda": "cu126"},
        "kind": "local-gpu",
        "gpu": True,
        "models": "chatterbox",
        "samples": True,   # uploaded voice samples (server/voices/*.wav) become selectable voices
        "fields": [
            {"key": "device", "type": "choice", "choices": ["auto", "cuda", "cpu"]},
        ],
        "download_mb": 4500,
    },
    "xtts": {
        "name": "XTTS-v2 (GPU, cloning)",
        "extra": None,
        "isolated": True,
        # coqui-tts declares transformers>=4.57 without an upper bound, but 5.x removed
        # isin_mps_friendly; torchaudio >= 2.9 needs torchcodec (+FFmpeg) for torchaudio.load
        "packages": ["coqui-tts", "transformers>=4.57,<5"],
        "torch": {"version": "2.7.1", "cuda": "cu128"},
        "kind": "local-gpu",
        "gpu": True,
        "models": "xtts",
        "samples": True,
        "fields": [
            {"key": "device", "type": "choice", "choices": ["auto", "cuda", "cpu"]},
        ],
        "download_mb": 4300,
    },
    "openai_tts": {
        "name": "OpenAI TTS (cloud, paid)",
        "extra": None,
        "kind": "cloud",
        "gpu": False,
        "models": None,
        "key_from_translator": "openai",
        "fields": [
            {"key": "api_key", "type": "secret", "label": "API key (empty = use the OpenAI translator key)"},
            {"key": "model_id", "type": "choice", "choices": ["gpt-4o-mini-tts", "tts-1", "tts-1-hd"]},
            {"key": "instructions", "type": "text", "label": "delivery instructions (gpt-4o-mini-tts)"},
        ],
        "download_mb": 0,
    },
    "gemini_tts": {
        "name": "Google Gemini TTS (cloud)",
        "extra": None,
        "kind": "cloud",
        "gpu": False,
        "models": None,
        "key_from_translator": "gemini",
        "fields": [
            {"key": "api_key", "type": "secret", "label": "API key (empty = use the Gemini translator key)"},
            {"key": "model_id", "type": "choice", "choices": ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]},
        ],
        "download_mb": 0,
    },
    "elevenlabs": {
        "name": "ElevenLabs (cloud, paid)",
        "extra": None,
        "kind": "cloud",
        "gpu": False,
        "models": None,
        "fields": [
            {"key": "api_key", "type": "secret", "label": "API key"},
            {"key": "model_id", "type": "choice", "choices": ["eleven_flash_v2_5", "eleven_v3", "eleven_multilingual_v2"]},
        ],
        "download_mb": 0,
    },
}

# Python modules whose importability means "the extra is installed".
EXTRA_PROBES = {
    "edge": ["edge_tts"],
    "piper": ["piper"],
}

# Modules that must import inside an isolated engine's own venv.
ISOLATED_PROBES = {
    "chatterbox": ["chatterbox", "torch"],
    "xtts": ["TTS", "torch"],
}

# Model ids that providers have retired, with their replacement. Applied to config.yaml on
# start-up (config.migrate_models) so an old install keeps working after a provider change.
RETIRED_MODELS: dict[str, str] = {
    "gemini-2.5-flash": "gemini-3.6-flash",           # "no longer available to new users" (Google, 2026)
    "gemini-2.0-flash": "gemini-3.6-flash",           # shut down
    "gemini-2.0-flash-lite": "gemini-3.5-flash-lite",
    "gemini-2.5-flash-preview-tts": "gemini-3.1-flash-tts-preview",
}

TRANSLATORS: dict[str, dict[str, Any]] = {
    "openai": {"type": "openai_compat", "name": "OpenAI",
               "fields": [{"key": "api_key", "type": "secret"}, {"key": "model", "type": "text"},
                          {"key": "base_url", "type": "text"}],
               "defaults": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini"}},
    "gemini": {"type": "openai_compat", "name": "Google Gemini",
               "fields": [{"key": "api_key", "type": "secret"}, {"key": "model", "type": "text"},
                          {"key": "base_url", "type": "text"}],
               "defaults": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-3.6-flash"}},
    "ollama": {"type": "openai_compat", "name": "Ollama (local LLM, e.g. Bielik)",
               "fields": [{"key": "model", "type": "text"}, {"key": "base_url", "type": "text"}],
               "defaults": {"base_url": "http://127.0.0.1:11434/v1", "api_key": "ollama",
                            "model": "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M"}},
    "anthropic": {"type": "anthropic", "name": "Anthropic Claude",
                  "fields": [{"key": "api_key", "type": "secret"}, {"key": "model", "type": "text"}],
                  "defaults": {"model": "claude-haiku-4-5"}},
    "deepl": {"type": "deepl", "name": "DeepL",
              "fields": [{"key": "api_key", "type": "secret"}, {"key": "base_url", "type": "text"}],
              "defaults": {"base_url": "https://api-free.deepl.com"}},
}
