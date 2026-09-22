"""Entry point: python -m polarnik_server [--config config.yaml] [--host H] [--port P] [--log-file F]

Runs fine without a console (pythonw.exe / autostart): logs go to a rotating file and, when
a terminal is attached, to stderr as well.
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import socket
import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .config import Config


def enable_console_colors() -> bool:
    """Enable ANSI escape sequences in the legacy Windows console (conhost).

    Windows Terminal handles them natively; conhost needs ENABLE_VIRTUAL_TERMINAL_PROCESSING,
    otherwise uvicorn's coloured log lines show up as literal "<-[32m" garbage.
    Returns True when colours can be used.
    """
    if sys.stdout is None or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if not kernel32.SetConsoleMode(handle, mode.value | 0x0004):  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


def setup_logging(level: str, log_file: Path | None) -> None:
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3,
                                                             encoding="utf-8"))
    if not handlers:
        handlers.append(logging.NullHandler())
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        handlers=handlers, force=True)


def port_in_use(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((probe_host, port)) == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="PolarnikTTS engine server")
    parser.add_argument("--config", default=None, help="path to config.yaml (default: ./config.yaml)")
    parser.add_argument("--host", default=None, help="override server.host")
    parser.add_argument("--port", type=int, default=None, help="override server.port")
    parser.add_argument("--log-file", default=None, help="override server.log_file (rotating log file)")
    parser.add_argument("--wait-port", action="store_true",
                        help="wait up to 30 s for the port to become free (used when the server restarts itself)")
    args = parser.parse_args()

    use_colors = enable_console_colors()
    config = Config.load(args.config)
    level = str(config.server.get("log_level", "info")).upper()
    log_file_cfg = args.log_file or config.server.get("log_file") or "logs/server.log"
    log_file = config.resolve(log_file_cfg) if log_file_cfg else None
    setup_logging(level, log_file)
    log = logging.getLogger(__name__)

    host = args.host or config.server.get("host", "127.0.0.1")
    port = args.port or int(config.server.get("port", 8765))
    if args.wait_port:
        import time

        for _ in range(60):
            if not port_in_use(host, port):
                break
            time.sleep(0.5)
    if port_in_use(host, port):
        log.warning("Port %s:%d is already in use - another PolarnikTTS server is probably running. Exiting.", host, port)
        return

    app = create_app(config)
    log.info("PolarnikTTS server listening on http://%s:%d (log: %s)", host, port, log_file)
    # log_config=None -> uvicorn logs through the root logger configured above
    uvicorn.run(app, host=host, port=port, log_level=level.lower(), use_colors=use_colors, log_config=None)


if __name__ == "__main__":
    main()
