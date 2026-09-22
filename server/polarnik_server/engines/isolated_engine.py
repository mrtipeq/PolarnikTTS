"""Proxy engine that runs a heavy engine (Chatterbox, XTTS) in its own virtualenv/process.

Why: those packages pin conflicting versions of torch/transformers/numpy. Keeping each in
`server/envs/<engine>/.venv` protects the server's own environment and lets the two coexist.
The worker process is started lazily and restarted if it dies.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .base import AudioResult, Engine, Voice

log = logging.getLogger(__name__)


def env_dir(server_dir: Path, engine_id: str) -> Path:
    return server_dir / "envs" / engine_id / ".venv"


def env_python(server_dir: Path, engine_id: str) -> Path:
    d = env_dir(server_dir, engine_id)
    return d / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


class IsolatedEngine(Engine):
    kind = "local-gpu"
    cloning = True
    serialize = True

    def __init__(self, engine_id: str, cfg: dict[str, Any], models_dir: Path, server_dir: Path,
                 name: str, licence: str = "", native_speed: bool = True):
        super().__init__(cfg, models_dir)
        self.id = engine_id
        self.name = name
        self.licence = licence
        self.native_speed = native_speed
        self.server_dir = server_dir
        self._proc: subprocess.Popen | None = None
        self._plock = threading.Lock()
        self._voices: list[Voice] | None = None
        self._default_voice = ""

    # -- process management ------------------------------------------------------------
    def _python(self) -> Path:
        return env_python(self.server_dir, self.id)

    def _ensure_proc(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        py = self._python()
        if not py.exists():
            raise RuntimeError(f"isolated environment not installed ({py})")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.server_dir) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        kwargs: dict[str, Any] = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL,
                                  "text": True, "encoding": "utf-8", "cwd": str(self.server_dir), "env": env}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cmd = [str(py), "-m", "polarnik_server.worker", self.id, str(self.models_dir), json.dumps(self.cfg)]
        log.info("%s: starting worker %s", self.id, py)
        self._proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
        return self._proc

    def _call(self, msg: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        with self._plock:
            proc = self._ensure_proc()
            assert proc.stdin and proc.stdout
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
            # Tolerate stray non-JSON lines (a C library writing to fd 1 bypasses the Python redirect).
            resp = None
            for _ in range(200):
                line = proc.stdout.readline()
                if not line:
                    code = proc.poll()
                    self._proc = None
                    raise RuntimeError(f"worker exited (code {code}) while handling {msg.get('cmd')}")
                stripped = line.strip()
                if not stripped.startswith("{"):
                    log.debug("%s worker noise: %s", self.id, stripped[:120])
                    continue
                try:
                    resp = json.loads(stripped)
                    break
                except json.JSONDecodeError:
                    log.debug("%s worker non-JSON line: %s", self.id, stripped[:120])
            if resp is None:
                raise RuntimeError("worker produced no JSON reply")
            if not resp.get("ok"):
                raise RuntimeError(resp.get("error", "worker error"))
            return resp

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write('{"cmd":"quit"}\n')  # type: ignore[union-attr]
                self._proc.stdin.flush()  # type: ignore[union-attr]
                self._proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self._proc.kill()
        self._proc = None

    # -- Engine API --------------------------------------------------------------------
    def check(self) -> tuple[bool, str]:
        if not self._python().exists():
            return False, "not installed (isolated environment missing)"
        try:
            resp = self._call({"cmd": "check"})
        except Exception as exc:  # noqa: BLE001
            return False, f"worker: {exc}"
        if resp.get("ready"):
            try:
                v = self._call({"cmd": "voices"})
                self._voices = [Voice(x["id"], x["name"]) for x in v.get("voices", [])]
                self._default_voice = v.get("default_voice", "")
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: voices failed: %s", self.id, exc)
        return bool(resp.get("ready")), resp.get("reason", "")

    def voices(self) -> list[Voice]:
        return list(self._voices or [])

    @property
    def default_voice(self) -> str:
        return self._default_voice or str(self.cfg.get("default_voice") or "")

    def synthesize_sync(self, text: str, voice: str, speed: float) -> AudioResult:
        resp = self._call({"cmd": "synthesize", "text": text, "voice": voice, "speed": speed})
        return AudioResult(data=base64.b64decode(resp["data_b64"]), mime=resp["mime"],
                           sample_rate=resp.get("sample_rate"), duration=resp.get("duration"))

    def load(self) -> None:  # the worker loads the model on first synthesize
        pass
