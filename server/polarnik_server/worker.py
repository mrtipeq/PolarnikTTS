"""Engine worker: runs one TTS engine in its own process / virtualenv.

    python -m polarnik_server.worker <engine_id> <models_dir> <config_json>

Protocol (one JSON object per line on stdin/stdout):
  {"cmd": "check"}                              -> {"ok": true, "ready": bool, "reason": str}
  {"cmd": "voices"}                             -> {"ok": true, "voices": [{"id","name"}], "default_voice": str}
  {"cmd": "synthesize", "text", "voice", "speed", "lang"} -> {"ok": true, "mime", "sample_rate", "duration", "data_b64"}
  {"cmd": "download"}                           -> {"ok": true}   (pre-fetch model weights)
  {"cmd": "quit"}

Only the engine module and its dependencies are imported here, so the worker's virtualenv
needs nothing from the server (no fastapi/yaml).
"""

from __future__ import annotations

import base64
import json
import sys
import traceback
from pathlib import Path


def load_engine(engine_id: str, cfg: dict, models_dir: str):
    # Import lazily so a missing dependency shows up as a readable "reason".
    if engine_id == "chatterbox":
        from .engines.chatterbox_engine import ChatterboxEngine as Cls
    elif engine_id == "xtts":
        from .engines.xtts_engine import XttsEngine as Cls
    else:
        raise ValueError(f"engine {engine_id} cannot run as a worker")
    return Cls(cfg, Path(models_dir))


def main() -> None:
    engine_id, models_dir, cfg_json = sys.argv[1], sys.argv[2], sys.argv[3]
    cfg = json.loads(cfg_json)
    engine = None
    # The protocol owns stdout. Libraries (chatterbox prints "loaded PerthNet ...", tqdm,
    # transformers warnings) must not write there, so route Python-level stdout to stderr and
    # keep a private handle to the real stdout for the JSON replies.
    out = sys.stdout
    sys.stdout = sys.stderr
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            cmd = msg.get("cmd")
            if cmd == "quit":
                break
            if engine is None:
                engine = load_engine(engine_id, cfg, models_dir)
            if cmd == "check":
                ready, reason = engine.ensure_ready()
                resp = {"ok": True, "ready": ready, "reason": reason}
            elif cmd == "voices":
                resp = {"ok": True, "voices": [{"id": v.id, "name": v.name, "lang": v.lang} for v in engine.voices()],
                        "default_voice": engine.default_voice}
            elif cmd == "download":
                engine.load()
                engine._loaded = True  # noqa: SLF001
                resp = {"ok": True}
            elif cmd == "synthesize":
                result = engine._load_and_run(msg["text"], msg.get("voice") or engine.default_voice,  # noqa: SLF001
                                              float(msg.get("speed", 1.0)), str(msg.get("lang") or "pl"))
                resp = {"ok": True, "mime": result.mime, "sample_rate": result.sample_rate,
                        "duration": result.duration, "data_b64": base64.b64encode(result.data).decode("ascii")}
            else:
                resp = {"ok": False, "error": f"unknown cmd {cmd}"}
        except Exception as exc:  # noqa: BLE001
            resp = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-2000:]}
        out.write(json.dumps(resp) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
