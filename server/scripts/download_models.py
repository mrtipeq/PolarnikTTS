#!/usr/bin/env python3
"""Download models for the local engines.

Usage:
  python scripts/download_models.py piper [voice ...]   # default: pl_PL-gosia-medium pl_PL-darkman-medium
  (Chatterbox / XTTS: use scripts/install_engine.py, which installs them into isolated envs
   and downloads their weights.)
Paths follow config.yaml (server.models_dir).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from polarnik_server.config import Config  # noqa: E402

PIPER_DEFAULT_VOICES = ["pl_PL-gosia-medium", "pl_PL-darkman-medium"]


def piper(models_dir: Path, voices: list[str]) -> None:
    target = models_dir / "piper"
    target.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "piper.download_voices", "--download-dir", str(target), *voices]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd)


def chatterbox(models_dir: Path) -> None:
    os.environ.setdefault("HF_HOME", str(models_dir / "hf"))
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    print("Chatterbox Multilingual weights cached in", os.environ["HF_HOME"])


def xtts(models_dir: Path) -> None:
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    os.environ.setdefault("TTS_HOME", str(models_dir / "tts"))
    from TTS.api import TTS

    TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    print("XTTS-v2 cached in", os.environ["TTS_HOME"])


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("piper", "chatterbox", "xtts"):
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] in ("chatterbox", "xtts"):
        print(f"Use: python scripts/install_engine.py {sys.argv[1]}")
        sys.exit(2)
    config = Config.load(None)
    models_dir = config.models_dir
    what = sys.argv[1]
    if what == "piper":
        piper(models_dir, sys.argv[2:] or PIPER_DEFAULT_VOICES)
    elif what == "chatterbox":
        chatterbox(models_dir)
    else:
        xtts(models_dir)


if __name__ == "__main__":
    main()
