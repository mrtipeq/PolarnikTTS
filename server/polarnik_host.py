#!/usr/bin/env python3
"""Chrome native messaging host for PolarnikTTS.

Chrome launches this process when the extension calls
chrome.runtime.sendNativeMessage("pl.polarnik.launcher", ...). It answers a few commands:

  {"cmd": "status"}  -> {"ok": true, "running": bool, "port": 8765}
  {"cmd": "start"}   -> starts the engine server in the background (pythonw, no window) and
                        waits until it answers on its port; {"ok": true, "running": true, ...}
  {"cmd": "stop"}    -> {"ok": true, "stopped": n}  (Windows: taskkill by command line)

Protocol: 4-byte little-endian length + UTF-8 JSON, on stdin/stdout. Registered by
install_host.ps1 / install.sh; see host/ for the manifest template.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import yaml

SERVER_DIR = Path(__file__).resolve().parent
CONFIG = SERVER_DIR / "config.yaml"
LOG = SERVER_DIR / "logs" / "host.log"


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def read_message() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    (length,) = struct.unpack("<I", raw)
    data = sys.stdin.buffer.read(length)
    return json.loads(data.decode("utf-8"))


def send_message(obj: dict) -> None:
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def server_port() -> tuple[str, int]:
    host, port = "127.0.0.1", 8765
    try:
        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
        srv = cfg.get("server") or {}
        host = str(srv.get("host", host))
        port = int(srv.get("port", port))
    except Exception:  # noqa: BLE001
        pass
    return ("127.0.0.1" if host in ("0.0.0.0", "") else host), port


def is_running() -> bool:
    host, port = server_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def python_for_server() -> Path:
    exe = Path(sys.executable)
    if os.name == "nt":
        pyw = exe.with_name("pythonw.exe")
        return pyw if pyw.exists() else exe
    return exe


def start_server(timeout_s: float = 25.0) -> dict:
    if is_running():
        return {"ok": True, "running": True, "already": True}
    py = python_for_server()
    args = [str(py), "-m", "polarnik_server", "--config", str(CONFIG)]
    kwargs: dict = {
        "cwd": str(SERVER_DIR),
        "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True
    log(f"starting: {' '.join(args)}")
    proc = subprocess.Popen(args, **kwargs)  # noqa: S603
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_running():
            return {"ok": True, "running": True, "pid": proc.pid}
        if proc.poll() is not None:
            return {"ok": False, "running": False, "error": f"server exited with code {proc.returncode} (see logs/server.log)"}
        time.sleep(0.4)
    return {"ok": False, "running": False, "error": "server did not answer within timeout (see logs/server.log)"}


def stop_server() -> dict:
    if os.name == "nt":
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'polarnik_server' } "
              "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,  # noqa: S603,S607
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        pids = [x for x in r.stdout.split() if x.isdigit()]
    else:
        r = subprocess.run(["pkill", "-f", "polarnik_server"], capture_output=True, text=True)  # noqa: S603,S607
        pids = ["?"] if r.returncode == 0 else []
    for _ in range(10):                       # give the process a moment to release the port
        if not is_running():
            break
        time.sleep(0.3)
    return {"ok": True, "stopped": len(pids), "running": is_running()}


def main() -> None:
    log(f"host started (argv={sys.argv[1:]})")
    while True:
        try:
            msg = read_message()
        except Exception as exc:  # noqa: BLE001
            log(f"bad message: {exc}")
            break
        if msg is None:
            break
        cmd = msg.get("cmd")
        host, port = server_port()
        try:
            if cmd == "status":
                resp = {"ok": True, "running": is_running()}
            elif cmd == "start":
                resp = start_server()
            elif cmd == "stop":
                resp = stop_server()
            else:
                resp = {"ok": False, "error": f"unknown cmd {cmd}"}
        except Exception as exc:  # noqa: BLE001
            resp = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        resp.update({"host": host, "port": port, "server_dir": str(SERVER_DIR)})
        log(f"{cmd} -> {resp}")
        send_message(resp)


if __name__ == "__main__":
    main()
