#!/usr/bin/env python3
"""Chrome native messaging host for PolarnikTTS.

Chrome launches this process when the extension calls
chrome.runtime.sendNativeMessage("pl.polarnik.launcher", ...). It answers a few commands:

  {"cmd": "status"}  -> {"ok": true, "running": bool, "port": 8765}
  {"cmd": "start"}   -> starts the engine server in the background (pythonw, no window) and
                        waits until it answers /health; a hung server holding the port is
                        killed first. {"ok": true, "running": true, "startup_s": ...}
  {"cmd": "stop"}    -> {"ok": true, "stopped": n}  (kills polarnik_server processes, waits
                        until the port is free)

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
import urllib.request
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


# never route the local health probe through a system proxy (Windows reads IE proxy settings)
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe(timeout: float = 3.0) -> str:
    """State of the configured port: "ok" (a PolarnikTTS server answers /health),
    "busy" (something holds the port but does not answer - a hung or foreign process) or "down"."""
    host, port = server_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex((host, port)) != 0:
            return "down"
    try:
        with _OPENER.open(f"http://{host}:{port}/health", timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8") or "{}")
        return "ok" if body.get("name") == "PolarnikTTS" else "busy"
    except Exception:  # noqa: BLE001
        return "busy"


def is_running() -> bool:
    return probe() == "ok"


def python_for_server() -> Path:
    exe = Path(sys.executable)
    if os.name == "nt":
        pyw = exe.with_name("pythonw.exe")
        return pyw if pyw.exists() else exe
    return exe


def log_tail(path: Path, lines: int = 4) -> str:
    """Last non-empty lines of a log file, for error messages shown in the extension."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001
        return ""
    tail = [ln.strip() for ln in text if ln.strip()][-lines:]
    return " | ".join(tail)


def kill_servers() -> int:
    """Kill every `python -m polarnik_server[.worker]` process (hung server, leftover after sleep,
    old version, orphaned engine workers). Matches the module switch only, so a shell or an
    editor that merely mentions the name is left alone."""
    if os.name == "nt":
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '-m polarnik_server' } "
              "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,  # noqa: S603,S607
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)
        return len([x for x in r.stdout.split() if x.isdigit()])
    r = subprocess.run(["pkill", "-f", "--", "-m polarnik_server"], capture_output=True, text=True)  # noqa: S603,S607
    return 1 if r.returncode == 0 else 0


def wait_port_free(seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if probe(timeout=1.0) == "down":
            return True
        time.sleep(0.3)
    return probe(timeout=1.0) == "down"


def start_server(timeout_s: float = 60.0) -> dict:
    state = probe()
    if state == "ok":
        return {"ok": True, "running": True, "already": True}
    if state == "busy":
        # The port is taken but nothing answers /health within 3 s: a hung server (e.g. after the
        # PC woke from sleep) or one stuck loading. Kill it and start clean.
        n = kill_servers()
        log(f"port busy but /health does not answer - killed {n} server process(es)")
        if not wait_port_free(10):
            return {"ok": False, "running": False,
                    "error": f"port {server_port()[1]} is held by another program (not PolarnikTTS) - "
                             "change server.port in config.yaml or close that program"}
    py = python_for_server()
    args = [str(py), "-m", "polarnik_server", "--config", str(CONFIG)]
    stderr_path = SERVER_DIR / "logs" / "server-stderr.log"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_fh = open(stderr_path, "w", encoding="utf-8")  # noqa: SIM115 - inherited by the child
    kwargs: dict = {
        "cwd": str(SERVER_DIR),
        "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": stderr_fh,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True
    log(f"starting: {' '.join(args)}")
    t0 = time.time()
    proc = subprocess.Popen(args, **kwargs)  # noqa: S603
    stderr_fh.close()
    deadline = t0 + timeout_s
    while time.time() < deadline:
        if probe(timeout=2.0) == "ok":
            log(f"server answers after {time.time() - t0:.1f}s (pid {proc.pid})")
            return {"ok": True, "running": True, "pid": proc.pid, "startup_s": round(time.time() - t0, 1)}
        if proc.poll() is not None:
            if probe(timeout=2.0) == "ok":       # another instance won the race for the port
                return {"ok": True, "running": True, "already": True}
            detail = log_tail(stderr_path) or log_tail(SERVER_DIR / "logs" / "server.log")
            return {"ok": False, "running": False,
                    "error": f"server exited with code {proc.returncode}" + (f": {detail}" if detail else " (see logs/server.log)")}
        time.sleep(0.4)
    detail = log_tail(SERVER_DIR / "logs" / "server.log", 2)
    return {"ok": False, "running": False,
            "error": f"server did not answer within {int(timeout_s)} s" + (f" - last log: {detail}" if detail else " (see logs/server.log)")}


def stop_server() -> dict:
    n = kill_servers()
    wait_port_free(10)
    return {"ok": True, "stopped": n, "running": is_running()}


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
