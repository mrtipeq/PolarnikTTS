#!/usr/bin/env python3
"""Install a TTS engine from the command line (same code path as the options page).

    python scripts/install_engine.py chatterbox
    python scripts/install_engine.py xtts
    python scripts/install_engine.py piper [voice ...]     # e.g. pl_PL-darkman-medium
    python scripts/install_engine.py edge_tts

Chatterbox and XTTS are installed into isolated virtualenvs under server/envs/<engine>/
(they pin conflicting torch/transformers versions), with a CUDA build of PyTorch when an
NVIDIA driver is present. Run with the server's virtualenv Python (server/.venv).
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

from polarnik_server.config import Config  # noqa: E402
from polarnik_server.installer import install_engine  # noqa: E402
from polarnik_server.manage import load_yaml, save_yaml  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    engine = sys.argv[1]
    voices = sys.argv[2:] or None
    config = Config.load(SERVER_DIR / "config.yaml")
    cfg = load_yaml(SERVER_DIR / "config.yaml")
    ecfg = (cfg.get("engines") or {}).get(engine) or {}
    result = install_engine(engine, SERVER_DIR, config.models_dir, print, voices=voices, engine_cfg=ecfg)
    cfg.setdefault("engines", {}).setdefault(engine, {})["enabled"] = True
    save_yaml(SERVER_DIR / "config.yaml", cfg)
    print(f"Engine '{engine}' installed and enabled in config.yaml.")
    if result.get("restart_required"):
        print("Restart the server (run_server.cmd / the options page) to load the new packages.")


if __name__ == "__main__":
    main()
