"""FastAPI application: /health, /engines, /translators, /tts, /translate."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import __version__
from .cache import AudioCache
from .config import Config
from .engines import Engine, build_engines
from .languages import DEFAULT_LANGUAGE, LANGUAGES, catalog as language_catalog, normalize_lang
from .manage import build_router
from .translators import build_translators

log = logging.getLogger(__name__)


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    engine: str | None = None
    voice: str | None = None
    speed: float = Field(1.0, ge=0.5, le=2.0)
    lang: str = "pl"             # target language of the text (languages.py code)
    no_cache: bool = False


class TranslateRequest(BaseModel):
    sentences: list[str]
    source_lang: str = "auto"
    target_lang: str = "pl"
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)
    translator: str | None = None


class State:
    def __init__(self, config: Config):
        self.config = config
        self.engines: dict[str, Engine] = build_engines(config.engines, config.models_dir, config.base_dir, config.translators)
        self.translators, self.default_translator = build_translators(config.translators)
        self.cache = AudioCache(config.cache_dir)
        self.started = time.time()

    def default_engine(self) -> str | None:
        """Configured default engine when ready, else the first ready real engine, else the test tone."""
        ready = [eid for eid, e in self.engines.items() if e.ensure_ready()[0]]
        preferred = str(self.config.server.get("default_engine") or "edge_tts")
        if preferred in ready:
            return preferred
        real = [eid for eid in ready if eid != "test_tone"]
        return (real or ready or [None])[0]


_CUDA_CACHE: dict[str, Any] | None = None


def cuda_info() -> dict[str, Any]:
    """GPU info from nvidia-smi (torch lives in the isolated engine envs, not in the server venv)."""
    global _CUDA_CACHE  # noqa: PLW0603
    if _CUDA_CACHE is not None:
        return _CUDA_CACHE
    import shutil
    import subprocess

    info: dict[str, Any] = {"available": False, "device": None, "vram_gb": 0}
    if shutil.which("nvidia-smi"):
        try:
            kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 5}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],  # noqa: S603,S607
                               **kwargs)
            line = (r.stdout or "").strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
            if line:
                name, mem = [x.strip() for x in line.split(",", 1)]
                info = {"available": True, "device": name, "vram_gb": round(float(mem) / 1024, 1)}
        except Exception:  # noqa: BLE001
            pass
    _CUDA_CACHE = info
    return info


def create_app(config: Config) -> FastAPI:
    state = State(config)
    app = FastAPI(title="PolarnikTTS engine server", version=__version__)
    app.state.polarnik = state

    # Chrome extensions send Origin: chrome-extension://<id>; allow everything, the
    # optional bearer token is the actual access control.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["X-Duration", "X-Cache", "X-Engine", "X-Voice"])

    token = str(config.server.get("token") or "")

    async def require_token(authorization: str | None = Header(default=None)) -> None:
        if not token:
            return
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid or missing token")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> str:
        """Human-readable status page (English; the extension UI is localized)."""
        rows = []
        for e in state.engines.values():
            info = e.info()
            mark = "✔" if info.ready else "✘"
            note = f" – {info.reason}" if info.reason else ""
            rows.append(f"<li>{mark} <b>{info.id}</b> ({info.name}){note}</li>")
        translators_html = "".join(
            f"<li>{'✔' if t.info().ready else '✘'} <b>{t.id}</b> ({t.info().name})"
            f"{' – ' + t.info().reason if t.info().reason else ''}</li>"
            for t in state.translators.values()
        ) or "<li>none (only YouTube auto-translate in the extension)</li>"
        cuda = cuda_info()
        cuda_html = f"{cuda['device']} ({cuda['vram_gb']} GB)" if cuda["available"] else "none (CPU / cloud only)"
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>PolarnikTTS engine server</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:32px auto;padding:0 16px;line-height:1.5}}
code{{background:#8882;padding:1px 5px;border-radius:4px}} li{{margin:4px 0}}</style></head><body>
<h1>PolarnikTTS engine server</h1>
<p>Version {__version__}. The server is running - this is the API for the PolarnikTTS extension; there is no user
interface here. Voice settings live in the extension's options page in Chrome.</p>
<p>CUDA: {cuda_html}</p>
<h2>TTS engines</h2><ul>{''.join(rows)}</ul>
<h2>Translators</h2><ul>{translators_html}</ul>
<h2>API</h2><ul>
<li><a href="/health"><code>GET /health</code></a> - server status (JSON)</li>
<li><a href="/engines"><code>GET /engines</code></a> - engines and voices</li>
<li><a href="/translators"><code>GET /translators</code></a> - translators</li>
<li><code>POST /tts</code>, <code>POST /translate</code> - synthesis and translation; <a href="/languages"><code>GET /languages</code></a> - target languages</li>
<li><a href="/docs"><code>/docs</code></a> - interactive API docs</li></ul>
</body></html>"""

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "name": "PolarnikTTS",
            "version": __version__,
            "uptime_s": round(time.time() - state.started, 1),
            "cuda": cuda_info(),
            "engines_ready": [eid for eid, e in state.engines.items() if e.ensure_ready()[0]],
            "default_engine": state.default_engine(),
            "translators_ready": [tid for tid, t in state.translators.items() if t.info().ready],
            "default_translator": state.default_translator,
            "auth_required": bool(token),
        }

    @app.get("/engines", dependencies=[Depends(require_token)])
    async def engines() -> list[dict[str, Any]]:
        return [asdict(e.info()) for e in state.engines.values()]

    @app.get("/languages")
    async def languages() -> dict[str, Any]:
        """Target languages of the voice-over and which engines can speak each of them."""
        by_engine = {eid: (e.langs or None) for eid, e in state.engines.items()}
        return {"default": DEFAULT_LANGUAGE, "languages": language_catalog(), "engine_langs": by_engine}

    @app.get("/translators", dependencies=[Depends(require_token)])
    async def translators() -> dict[str, Any]:
        items = [{"id": "youtube", "name": "YouTube auto-translate (in extension)", "type": "youtube",
                  "ready": True, "reason": "", "restores_punctuation": False}]
        items += [asdict(t.info()) for t in state.translators.values()]
        return {"default": state.default_translator, "items": items}

    @app.post("/tts", dependencies=[Depends(require_token)])
    async def tts(req: TtsRequest) -> Response:
        engine_id = req.engine or state.default_engine()
        if not engine_id or engine_id not in state.engines:
            raise HTTPException(status_code=404, detail=f"engine not configured: {engine_id}")
        engine = state.engines[engine_id]
        ready, reason = engine.ensure_ready()
        if not ready:
            raise HTTPException(status_code=503, detail=f"engine {engine_id} not ready: {reason}")
        lang = normalize_lang(req.lang)
        if not engine.supports_lang(lang):
            raise HTTPException(status_code=400, detail=f"engine {engine_id} cannot speak {LANGUAGES[lang]['name']} - pick another engine")
        voice = req.voice or engine.default_voice_for(lang)
        key = AudioCache.key(engine_id, voice, req.speed, req.text if lang == "pl" else f"{lang}\x1f{req.text}")
        hit = None if req.no_cache else state.cache.get(engine_id, key)
        if hit is None:
            t0 = time.perf_counter()
            try:
                result = await engine.synthesize(req.text, voice, req.speed, lang)
            except Exception as exc:  # noqa: BLE001
                log.exception("%s synthesis failed", engine_id)
                raise HTTPException(status_code=500, detail=f"{engine_id}: {type(exc).__name__}: {exc}") from exc
            elapsed = time.perf_counter() - t0
            log.info("%s/%s %.2fs for %d chars (audio %.2fs)", engine_id, voice, elapsed, len(req.text),
                     result.duration or -1)
            state.cache.put(engine_id, key, result)
            cache_state = "miss"
        else:
            result, cache_state = hit, "hit"
        headers = {
            "X-Duration": f"{result.duration:.3f}" if result.duration is not None else "",
            "X-Cache": cache_state,
            "X-Engine": engine_id,
            "X-Voice": voice,
            "Cache-Control": "no-store",
        }
        return Response(content=result.data, media_type=result.mime, headers=headers)

    @app.post("/translate", dependencies=[Depends(require_token)])
    async def translate(req: TranslateRequest) -> dict[str, Any]:
        tid = req.translator or state.default_translator
        if tid == "youtube":
            raise HTTPException(status_code=400, detail="translator 'youtube' is handled by the extension")
        tr = state.translators.get(tid)
        if tr is None:
            raise HTTPException(status_code=404, detail=f"translator not configured: {tid}")
        info = tr.info()
        if not info.ready:
            raise HTTPException(status_code=503, detail=f"translator {tid} not ready: {info.reason}")
        t0 = time.perf_counter()
        try:
            out = await tr.translate(req.sentences, req.source_lang, req.context_before, req.context_after,
                                     normalize_lang(req.target_lang))
        except Exception as exc:  # noqa: BLE001
            log.exception("%s translation failed", tid)
            raise HTTPException(status_code=502, detail=f"{tid}: {type(exc).__name__}: {exc}") from exc
        return {"translator": tid, "translations": out, "elapsed_s": round(time.perf_counter() - t0, 3)}

    app.include_router(build_router(state))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})

    return app
