"""Installation of engines: shared by the management API and scripts/install_engine.py.

Two kinds of engines:
- light ones (edge_tts, piper) go into the server's own virtualenv (`pip install -e .[extra]`);
  the server must restart afterwards, because compiled packages (numpy, onnxruntime) may have
  changed under a running process;
- isolated ones (chatterbox, xtts) get `server/envs/<engine>/.venv` with their own pinned
  torch/transformers, and run as worker processes - no restart needed.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .catalog import ENGINES, EXTRA_PROBES, ISOLATED_PROBES
from .engines.isolated_engine import env_dir, env_python

LogFn = Callable[[str], None]


def run_logged(cmd: list[str], cwd: Path, log: LogFn, env: dict[str, str] | None = None) -> int:
    log("$ " + " ".join(cmd))
    kwargs: dict[str, Any] = {"cwd": str(cwd), "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT,
                              "text": True, "encoding": "utf-8", "errors": "replace", "env": env,
                              "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip("\n"))
    return proc.wait()


def has_nvidia_driver() -> bool:
    return shutil.which("nvidia-smi") is not None


def torch_index(cuda_tag: str) -> str | None:
    """PyTorch wheel index for the given CUDA tag, or None for the CPU build (no NVIDIA driver)."""
    return f"https://download.pytorch.org/whl/{cuda_tag}" if has_nvidia_driver() else None


def gpu_compute_capability() -> float | None:
    """Highest CUDA compute capability of the local GPUs (e.g. 7.5, 8.6, 12.0), via nvidia-smi."""
    if not has_nvidia_driver():
        return None
    kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 15}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"], **kwargs).stdout  # noqa: S603, S607
        caps = [float(x.strip()) for x in out.splitlines() if x.strip()]
        return max(caps) if caps else None
    except Exception:  # noqa: BLE001
        return None


# Oldest PyTorch build with kernels for Blackwell GPUs (sm_100 data-centre, sm_120 RTX 50xx).
BLACKWELL_TORCH = {"version": "2.7.1", "cuda": "cu128"}


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def resolve_torch_spec(meta: dict[str, Any], log: LogFn) -> dict[str, Any]:
    """The catalog pin, bumped when the GPU is newer than that build supports."""
    spec = dict(meta.get("torch") or {})
    cap = gpu_compute_capability()
    if cap is not None and cap >= 10.0 and spec.get("version") and _version_tuple(spec["version"]) < (2, 7):
        log(f"GPU compute capability {cap} (Blackwell) needs PyTorch >= 2.7 with CUDA 12.8 - using "
            f"{BLACKWELL_TORCH['version']}+{BLACKWELL_TORCH['cuda']} instead of the package's pin "
            f"{spec['version']}+{spec.get('cuda', '')}")
        spec.update(BLACKWELL_TORCH)
    return spec


def extra_installed(extra: str | None) -> bool:
    """Is a server-venv extra importable in *this* process?"""
    if not extra:
        return True
    importlib.invalidate_caches()
    for mod in EXTRA_PROBES.get(extra, []):
        try:
            importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            return False
    return True


def isolated_installed(server_dir: Path, engine_id: str) -> bool:
    """Does the isolated venv exist and import the engine's modules? (cached per process)"""
    py = env_python(server_dir, engine_id)
    if not py.exists():
        return False
    cache = _ISOLATED_CACHE.get(engine_id)
    mtime = py.stat().st_mtime
    if cache and cache[0] == mtime:
        return cache[1]
    mods = ISOLATED_PROBES.get(engine_id, [])
    code = "import " + ", ".join(mods) if mods else "pass"
    kwargs: dict[str, Any] = {"capture_output": True, "timeout": 120}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        ok = subprocess.run([str(py), "-c", code], **kwargs).returncode == 0  # noqa: S603
    except Exception:  # noqa: BLE001
        ok = False
    _ISOLATED_CACHE[engine_id] = (mtime, ok)
    return ok


_ISOLATED_CACHE: dict[str, tuple[float, bool]] = {}


def install_engine(engine_id: str, server_dir: Path, models_dir: Path, log: LogFn,
                   voices: list[str] | None = None, engine_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Install dependencies and models for an engine. Returns {"restart_required": bool}."""
    meta = ENGINES.get(engine_id)
    if meta is None:
        raise ValueError(f"unknown engine {engine_id}")
    restart_required = False

    if meta.get("isolated"):
        _install_isolated(engine_id, meta, server_dir, models_dir, log, engine_cfg or {})
    else:
        if meta.get("extra") and not extra_installed(meta["extra"]):
            cmd = [sys.executable, "-m", "pip", "install", "-e", f"{server_dir}[{meta['extra']}]"]
            if run_logged(cmd, server_dir, log) != 0:
                raise RuntimeError("pip install failed")
            restart_required = True
        if meta.get("models") == "piper":
            wanted = voices or [meta["voices"][0]["id"]]
            vdir = models_dir / "piper"
            vdir.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, "-m", "piper.download_voices", "--download-dir", str(vdir), *wanted]
            if run_logged(cmd, server_dir, log) != 0:
                raise RuntimeError("voice download failed")
    return {"restart_required": restart_required}


def _install_isolated(engine_id: str, meta: dict[str, Any], server_dir: Path, models_dir: Path,
                      log: LogFn, engine_cfg: dict[str, Any]) -> None:
    venv = env_dir(server_dir, engine_id)
    py = env_python(server_dir, engine_id)
    if not py.exists():
        log(f"Creating isolated environment {venv}")
        venv.parent.mkdir(parents=True, exist_ok=True)
        if run_logged([sys.executable, "-m", "venv", str(venv)], server_dir, log) != 0:
            raise RuntimeError("virtualenv creation failed")
    if run_logged([str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel"], server_dir, log) != 0:
        raise RuntimeError("pip upgrade failed")

    torch_spec = resolve_torch_spec(meta, log)
    ver = torch_spec.get("version") or ""
    idx = torch_index(torch_spec.get("cuda", "cu128"))
    pkgs = [f"torch=={ver}" if ver else "torch", f"torchaudio=={ver}" if ver else "torchaudio"]
    log(f"Installing PyTorch {ver or '(latest)'} {'with CUDA ' + torch_spec.get('cuda', '') if idx else 'CPU-only (no NVIDIA driver found)'}")
    torch_cmd = [str(py), "-m", "pip", "install", *pkgs] + (["--index-url", idx] if idx else [])
    if run_logged(torch_cmd, server_dir, log) != 0:
        raise RuntimeError("PyTorch installation failed")

    # numpy + soundfile are needed by the worker/base engine code as well
    cmd = [str(py), "-m", "pip", "install", *meta["packages"], "numpy", "soundfile"]
    if run_logged(cmd, server_dir, log) != 0:
        raise RuntimeError("engine package installation failed")

    # The package may pin an older torch (chatterbox-tts: torch==2.6.0) and pip then replaces the
    # build installed above with a PyPI one. Re-assert the wanted build; pip only warns about the
    # version conflict and the engines work with the newer torch. No-op when nothing changed.
    if ver and run_logged(torch_cmd, server_dir, log) != 0:
        raise RuntimeError("PyTorch re-installation failed")
    _ISOLATED_CACHE.pop(engine_id, None)

    log("Downloading model weights (this can take a while)…")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(server_dir) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    cfg = dict(engine_cfg)
    cfg.setdefault("device", "cpu")  # weights only; keep the GPU out of the download step
    cmd = [str(py), "-c",
           "import json,sys; from polarnik_server.worker import load_engine; "
           "e=load_engine(sys.argv[1], json.loads(sys.argv[3]), sys.argv[2]); e.load(); print('model ready')",
           engine_id, str(models_dir), json.dumps(cfg)]
    if run_logged(cmd, server_dir, log, env=env) != 0:
        raise RuntimeError("model download failed")


def restart_server_process(server_dir: Path, config_path: Path, log: LogFn) -> None:
    """Spawn a fresh server (waiting for the port to free up) and exit this process."""
    py = Path(sys.executable)
    if os.name == "nt":
        pyw = py.with_name("pythonw.exe")
        if pyw.exists():
            py = pyw
    args = [str(py), "-m", "polarnik_server", "--config", str(config_path), "--wait-port"]
    kwargs: dict[str, Any] = {"cwd": str(server_dir), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                              "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True
    log("Restarting the server to load the new packages…")
    subprocess.Popen(args, **kwargs)  # noqa: S603
    import threading
    import time

    def bye() -> None:
        time.sleep(1.0)
        os._exit(0)  # noqa: S606

    threading.Thread(target=bye, daemon=True).start()
