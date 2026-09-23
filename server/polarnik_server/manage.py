"""Management API: install engines, download models, edit config, reload, shutdown.

Only reachable from the local machine (loopback) unless a bearer token is configured.
Long operations run as background jobs whose log can be polled.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import __version__
from .catalog import ENGINES, TRANSLATORS
from .installer import extra_installed, install_engine, isolated_installed, restart_server_process
from .samples import list_samples, sample_path, store_sample

log = logging.getLogger(__name__)


# ---- jobs ----------------------------------------------------------------------------
class Job:
    def __init__(self, kind: str, target: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.target = target
        self.status = "running"      # running | done | failed
        self.log: list[str] = []
        self.started = time.time()
        self.finished: float | None = None
        self.error = ""
        self.restart_required = False

    def write(self, line: str) -> None:
        self.log.append(line.rstrip("\n"))
        if len(self.log) > 2000:
            del self.log[:500]

    def to_dict(self, tail: int = 60) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "target": self.target, "status": self.status,
                "error": self.error, "started": self.started, "finished": self.finished,
                "restart_required": self.restart_required,
                "log": self.log[-tail:], "lines": len(self.log)}


JOBS: dict[str, Job] = {}
_JOB_LOCK = threading.Lock()


# ---- config editing --------------------------------------------------------------------
def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        example = path.with_name("config.example.yaml")
        if example.exists():
            shutil.copy(example, path)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("# PolarnikTTS configuration (edited by the management API; see config.example.yaml for comments)\n")
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


# ---- router ------------------------------------------------------------------------------
class ConfigUpdate(BaseModel):
    section: str                       # "engines" | "translators" | "server"
    id: str | None = None              # engine / translator id (None for "server")
    values: dict[str, Any]


class InstallRequest(BaseModel):
    engine: str
    voices: list[str] | None = None     # piper voices to download (default: first one)


class ImportBundle(BaseModel):
    config: dict[str, Any]
    samples: list[dict[str, Any]] = []


class OllamaPull(BaseModel):
    model: str


def build_router(state) -> APIRouter:  # noqa: C901 - one place for all management endpoints
    router = APIRouter(prefix="/manage")
    config = state.config
    server_dir = config.base_dir
    config_path = server_dir / "config.yaml"
    token = str(config.server.get("token") or "")

    def guard(request: Request) -> None:
        host = request.client.host if request.client else ""
        if host in ("127.0.0.1", "::1", "localhost"):
            return
        auth = request.headers.get("authorization", "")
        if token and auth == f"Bearer {token}":
            return
        raise HTTPException(status_code=403, detail="management API is local-only")

    def reload_engines() -> None:
        from .engines import build_engines
        from .translators import build_translators

        state.config = config.__class__.load(config_path)
        for old in state.engines.values():
            stop = getattr(old, "stop", None)
            if callable(stop):
                stop()
        state.engines = build_engines(state.config.engines, state.config.models_dir, state.config.base_dir,
                                      state.config.translators)
        state.translators, state.default_translator = build_translators(state.config.translators)
        log.info("Engines reloaded: %s", ", ".join(state.engines) or "none")

    @router.get("/catalog")
    async def catalog(request: Request) -> dict[str, Any]:
        guard(request)
        cfg = load_yaml(config_path)
        engines_cfg = cfg.get("engines") or {}
        out_engines = []
        for eid, meta in ENGINES.items():
            ecfg = engines_cfg.get(eid) or {}
            live = state.engines.get(eid)
            info = live.info() if live else None
            models_ok = None
            voices = []
            if meta.get("models") == "piper":
                vdir = state.config.models_dir / "piper"
                voices = [{**v, "installed": (vdir / f"{v['id']}.onnx").exists()} for v in meta["voices"]]
                models_ok = any(v["installed"] for v in voices)
            elif meta.get("models") in ("chatterbox", "xtts"):
                hf = state.config.models_dir / ("hf" if meta["models"] == "chatterbox" else "tts")
                models_ok = hf.exists() and any(hf.rglob("*"))
            key_inherited = (bool(meta.get("key_from_translator")) and not ecfg.get("api_key")
                             and bool(((cfg.get("translators") or {}).get(meta.get("key_from_translator")) or {}).get("api_key")))
            out_engines.append({
                "id": eid, "name": meta["name"], "kind": meta["kind"], "gpu": meta["gpu"],
                "extra": meta["extra"], "isolated": bool(meta.get("isolated")),
                "installed": isolated_installed(server_dir, eid) if meta.get("isolated") else extra_installed(meta["extra"]),
                "enabled": bool(ecfg.get("enabled", False)),
                "ready": bool(info and info.ready), "reason": (info.reason if info else "not loaded"),
                "models_ok": models_ok, "voices": voices, "download_mb": meta.get("download_mb", 0),
                "fields": meta["fields"], "recommended": meta.get("recommended", False),
                "samples": bool(meta.get("samples")),
                "values": {f["key"]: ("•••" if f["type"] == "secret" and ecfg.get(f["key"]) else ecfg.get(f["key"], ""))
                           for f in meta["fields"]},
                "key_inherited": key_inherited,
                "key_source": meta.get("key_from_translator", ""),
                "default_voice": ecfg.get("default_voice", ""),
            })
        translators_cfg = cfg.get("translators") or {}
        out_translators = []
        for tid, meta in TRANSLATORS.items():
            tcfg = translators_cfg.get(tid) or {}
            live = state.translators.get(tid)
            tinfo = live.info() if live else None
            out_translators.append({
                "id": tid, "name": meta["name"], "type": meta["type"],
                "enabled": bool(tcfg.get("enabled", False)),
                "ready": bool(tinfo and tinfo.ready), "reason": (tinfo.reason if tinfo else "not loaded"),
                "fields": meta["fields"],
                "values": {f["key"]: ("•••" if f["type"] == "secret" and tcfg.get(f["key"]) else
                                      tcfg.get(f["key"], meta["defaults"].get(f["key"], "")))
                           for f in meta["fields"]},
            })
        return {
            "engines": out_engines,
            "translators": out_translators,
            "samples": list_samples(server_dir),
            "default_translator": translators_cfg.get("default", "youtube"),
            "default_engine": (cfg.get("server") or {}).get("default_engine", "edge_tts"),
            "cuda_driver": shutil.which("nvidia-smi") is not None,
            "python": sys.executable,
            "server_dir": str(server_dir),
            "jobs": [j.to_dict(tail=1) for j in JOBS.values() if j.status == "running"],
        }

    @router.post("/install")
    async def install(request: Request, req: InstallRequest) -> dict[str, Any]:
        guard(request)
        meta = ENGINES.get(req.engine)
        if meta is None:
            raise HTTPException(status_code=404, detail=f"unknown engine {req.engine}")
        with _JOB_LOCK:
            if any(j.status == "running" for j in JOBS.values()):
                raise HTTPException(status_code=409, detail="another installation is already running")
            job = Job("install", req.engine)
            JOBS[job.id] = job

        def work() -> None:
            try:
                cfg0 = load_yaml(config_path)
                ecfg = (cfg0.get("engines") or {}).get(req.engine) or {}
                result = install_engine(req.engine, server_dir, state.config.models_dir, job.write,
                                        voices=req.voices, engine_cfg=ecfg)
                cfg = load_yaml(config_path)
                cfg.setdefault("engines", {}).setdefault(req.engine, {})["enabled"] = True
                save_yaml(config_path, cfg)
                job.restart_required = bool(result.get("restart_required"))
                if job.restart_required:
                    job.write("Done. The server restarts now to load the new packages.")
                    job.status = "done"
                    job.finished = time.time()
                    restart_server_process(server_dir, config_path, job.write)
                    return
                reload_engines()
                job.write("Done.")
                job.status = "done"
            except Exception as exc:  # noqa: BLE001
                job.error = str(exc)
                job.write(f"ERROR: {exc}")
                job.status = "failed"
            finally:
                job.finished = time.time()

        threading.Thread(target=work, name=f"install-{req.engine}", daemon=True).start()
        return {"job": job.to_dict()}

    @router.get("/jobs/{job_id}")
    async def job_status(request: Request, job_id: str, tail: int = 60) -> dict[str, Any]:
        guard(request)
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such job")
        return job.to_dict(tail=tail)

    @router.post("/config")
    async def update_config(request: Request, req: ConfigUpdate) -> dict[str, Any]:
        guard(request)
        cfg = load_yaml(config_path)
        if req.section == "server":
            allowed = {"default_engine", "host", "port", "token"}
            bad = set(req.values) - allowed
            if bad:
                raise HTTPException(status_code=400, detail=f"not editable: {sorted(bad)}")
            cfg.setdefault("server", {}).update(req.values)
        elif req.section in ("engines", "translators"):
            if not req.id:
                raise HTTPException(status_code=400, detail="id required")
            catalog_meta = (ENGINES if req.section == "engines" else TRANSLATORS).get(req.id)
            if catalog_meta is None and req.id != "test_tone":
                raise HTTPException(status_code=404, detail=f"unknown {req.section[:-1]} {req.id}")
            allowed = {"enabled", "default_voice"} | {f["key"] for f in (catalog_meta or {}).get("fields", [])}
            bad = set(req.values) - allowed
            if bad:
                raise HTTPException(status_code=400, detail=f"not editable: {sorted(bad)}")
            entry = cfg.setdefault(req.section, {}).setdefault(req.id, {})
            if catalog_meta and req.section == "translators":
                entry.setdefault("type", catalog_meta["type"])
                for k, v in catalog_meta.get("defaults", {}).items():
                    entry.setdefault(k, v)
            for k, v in req.values.items():
                if v == "•••":           # untouched secret placeholder
                    continue
                entry[k] = v
            if req.section == "translators" and req.values.get("enabled") and cfg["translators"].get("default", "youtube") == "youtube":
                pass  # the extension chooses the translator; server default stays as is
        else:
            raise HTTPException(status_code=400, detail="unknown section")
        save_yaml(config_path, cfg)
        reload_engines()
        return {"ok": True}

    @router.get("/secret")
    async def reveal_secret(request: Request, section: str, id: str, key: str) -> dict[str, Any]:
        """Return a stored secret in clear text (local-only; the value sits in config.yaml anyway)."""
        guard(request)
        if section not in ("engines", "translators"):
            raise HTTPException(status_code=400, detail="unknown section")
        meta = (ENGINES if section == "engines" else TRANSLATORS).get(id)
        if meta is None or not any(f["key"] == key and f["type"] == "secret" for f in meta.get("fields", [])):
            raise HTTPException(status_code=404, detail="no such secret field")
        cfg = load_yaml(config_path)
        value = ((cfg.get(section) or {}).get(id) or {}).get(key, "")
        source = ""
        if not value and section == "engines" and meta.get("key_from_translator"):
            source = meta["key_from_translator"]
            value = ((cfg.get("translators") or {}).get(source) or {}).get(key, "")
        return {"value": value or "", "inherited_from": source}

    # ---- voice samples for cloning engines --------------------------------------------
    @router.get("/samples")
    async def samples(request: Request) -> dict[str, Any]:
        guard(request)
        return {"items": list_samples(server_dir)}

    @router.post("/samples")
    async def upload_sample(request: Request, name: str) -> dict[str, Any]:
        guard(request)
        data = await request.body()
        if not data or len(data) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="empty or too large (max 50 MB)")
        try:
            item = store_sample(server_dir, name, data)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"cannot decode audio: {exc}") from exc
        reload_engines()  # new sample = new voice in cloning engines
        return item

    @router.get("/samples/{name}/audio")
    async def sample_audio(request: Request, name: str) -> FileResponse:
        guard(request)
        p = sample_path(server_dir, name)
        if p is None:
            raise HTTPException(status_code=404, detail="no such sample")
        return FileResponse(str(p), media_type="audio/wav")

    @router.delete("/samples/{name}")
    async def delete_sample(request: Request, name: str) -> dict[str, Any]:
        guard(request)
        p = sample_path(server_dir, name)
        if p is None:
            raise HTTPException(status_code=404, detail="no such sample")
        p.unlink()
        reload_engines()
        return {"ok": True}

    # ---- settings transfer -------------------------------------------------------------
    @router.get("/export")
    async def export_settings(request: Request) -> dict[str, Any]:
        """Config (with keys) + voice samples, for moving to another machine. Local-only."""
        guard(request)
        import base64

        samples = []
        for smp in list_samples(server_dir):
            p = sample_path(server_dir, smp["name"])
            if p:
                samples.append({"name": smp["name"], "data_b64": base64.b64encode(p.read_bytes()).decode("ascii")})
        return {"config": load_yaml(config_path), "samples": samples, "server_version": __version__}

    @router.post("/import")
    async def import_settings(request: Request, bundle: ImportBundle) -> dict[str, Any]:
        guard(request)
        import base64

        cfg = load_yaml(config_path)
        incoming = bundle.config or {}
        # keep machine-specific paths/ports of this installation, take engines/translators/defaults
        for section in ("engines", "translators"):
            if section in incoming:
                cfg[section] = incoming[section]
        for key in ("default_engine",):
            if key in (incoming.get("server") or {}):
                cfg.setdefault("server", {})[key] = incoming["server"][key]
        save_yaml(config_path, cfg)
        n = 0
        for smp in bundle.samples:
            try:
                store_sample(server_dir, smp["name"], base64.b64decode(smp["data_b64"]))
                n += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("sample %s skipped: %s", smp.get("name"), exc)
        reload_engines()
        return {"ok": True, "samples_imported": n}

    # ---- Ollama (local LLM translator): pulled models and model download -------------
    def ollama_host() -> str:
        cfg = load_yaml(config_path)
        base = str(((cfg.get("translators") or {}).get("ollama") or {}).get("base_url")
                   or TRANSLATORS["ollama"]["defaults"]["base_url"])
        return base.rstrip("/").removesuffix("/v1")

    @router.get("/ollama")
    async def ollama_status(request: Request) -> dict[str, Any]:
        """Is Ollama reachable, which models are pulled, is the configured one among them?"""
        guard(request)
        cfg = load_yaml(config_path)
        model = str(((cfg.get("translators") or {}).get("ollama") or {}).get("model")
                    or TRANSLATORS["ollama"]["defaults"]["model"])
        host = ollama_host()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(host + "/api/tags")
                r.raise_for_status()
            models = [m.get("name", "") for m in r.json().get("models", [])]
        except Exception as exc:  # noqa: BLE001
            return {"running": False, "host": host, "model": model, "models": [], "pulled": False,
                    "error": f"{type(exc).__name__}: {exc}"}
        norm = lambda n: n if ":" in n else n + ":latest"  # noqa: E731
        pulled = norm(model) in {norm(m) for m in models}
        return {"running": True, "host": host, "model": model, "models": models, "pulled": pulled}

    @router.post("/ollama/pull")
    async def ollama_pull(request: Request, req: OllamaPull) -> dict[str, Any]:
        """Download a model through Ollama's own API (streams progress into a job log)."""
        guard(request)
        model = req.model.strip()
        if not model:
            raise HTTPException(status_code=400, detail="model required")
        host = ollama_host()
        with _JOB_LOCK:
            if any(j.status == "running" for j in JOBS.values()):
                raise HTTPException(status_code=409, detail="another installation is already running")
            job = Job("ollama-pull", model)
            JOBS[job.id] = job

        def work() -> None:
            last = ""
            try:
                job.write(f"ollama pull {model}  (via {host}/api/pull)")
                with httpx.Client(timeout=httpx.Timeout(30.0, read=None)) as client, \
                        client.stream("POST", host + "/api/pull", json={"name": model, "stream": True}) as r:
                    r.raise_for_status()
                    for raw in r.iter_lines():
                        if not raw:
                            continue
                        try:
                            ev = json.loads(raw)
                        except ValueError:
                            continue
                        if ev.get("error"):
                            raise RuntimeError(ev["error"])
                        status = ev.get("status", "")
                        total, done = ev.get("total"), ev.get("completed")
                        if total and done is not None:
                            line = f"{status}: {done / 1e9:.2f} / {total / 1e9:.2f} GB ({100 * done / total:.0f}%)"
                        else:
                            line = status
                        if line and line != last:
                            job.write(line)
                            last = line
                job.write("Done.")
                job.status = "done"
            except Exception as exc:  # noqa: BLE001
                job.error = str(exc)
                job.write(f"ERROR: {exc}")
                job.status = "failed"
            finally:
                job.finished = time.time()

        threading.Thread(target=work, name=f"ollama-pull-{model}", daemon=True).start()
        return {"job": job.to_dict()}

    # ---- model discovery for OpenAI-compatible providers ------------------------------
    ENGINE_MODEL_ENDPOINTS = {
        "openai_tts": ("https://api.openai.com/v1", "openai", lambda m: "tts" in m),
        "gemini_tts": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini", lambda m: "tts" in m),
    }

    @router.get("/models")
    async def list_models(request: Request, section: str, id: str) -> dict[str, Any]:
        """GET <base_url>/models with the configured key - which model ids does this key see?"""
        guard(request)
        cfg = load_yaml(config_path)
        if section == "translators":
            meta = TRANSLATORS.get(id)
            if meta is None or meta.get("type") != "openai_compat":
                raise HTTPException(status_code=404, detail="no model listing for this translator")
            entry = (cfg.get("translators") or {}).get(id) or {}
            base = str(entry.get("base_url") or meta["defaults"].get("base_url") or "")
            key = str(entry.get("api_key") or meta["defaults"].get("api_key") or "")
            keep = lambda m: True  # noqa: E731
        elif section == "engines" and id in ENGINE_MODEL_ENDPOINTS:
            base, tr_id, keep = ENGINE_MODEL_ENDPOINTS[id]
            entry = (cfg.get("engines") or {}).get(id) or {}
            key = str(entry.get("api_key") or ((cfg.get("translators") or {}).get(tr_id) or {}).get("api_key") or "")
        else:
            raise HTTPException(status_code=404, detail="no model listing for this item")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(base.rstrip("/") + "/models", headers=headers)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"cannot reach {base}: {type(exc).__name__}: {exc}") from exc
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"HTTP {r.status_code} from {base}/models: {r.text[:300]}")
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        ids = []
        for m in items or []:
            mid = m.get("id") if isinstance(m, dict) else str(m)
            if not mid:
                continue
            mid = str(mid).removeprefix("models/")
            if keep(mid):
                ids.append(mid)
        return {"base_url": base, "models": sorted(set(ids))}

    @router.post("/reload")
    async def reload(request: Request) -> dict[str, Any]:
        guard(request)
        reload_engines()
        return {"ok": True, "engines_ready": [e for e, en in state.engines.items() if en.ensure_ready()[0]]}

    @router.post("/shutdown")
    async def shutdown(request: Request) -> dict[str, Any]:
        guard(request)
        log.info("Shutdown requested through the management API")

        def bye() -> None:
            time.sleep(0.5)
            os._exit(0)  # noqa: S606 - uvicorn's graceful shutdown hangs on open keep-alive connections

        threading.Thread(target=bye, daemon=True).start()
        return {"ok": True}

    return router
