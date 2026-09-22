#!/usr/bin/env python3
"""Listening bench: render the same Polish sentences with every ready engine.

Usage (from the repository root, with the server virtualenv active):
  python bench/bench.py                       # all ready engines from server/config.yaml
  python bench/bench.py --engines edge_tts,piper
  python bench/bench.py --config server/config.yaml --out bench/out --limit 5

Output: bench/out/<engine>/NN.<ext> and bench/out/index.html with side-by-side players,
wall-clock time, audio duration and real-time factor (RTF = synthesis time / audio time).
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from polarnik_server.audio import MIME_TO_EXT, probe_duration  # noqa: E402
from polarnik_server.config import Config  # noqa: E402
from polarnik_server.engines import build_engines  # noqa: E402


def load_sentences(path: Path, limit: int | None) -> list[str]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    return lines[:limit] if limit else lines


async def run_engine(engine, sentences: list[str], out_dir: Path, voice: str | None, speed: float) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    voice = voice or engine.default_voice
    for i, text in enumerate(sentences, 1):
        t0 = time.perf_counter()
        try:
            result = await engine.synthesize(text, voice, speed)
            elapsed = time.perf_counter() - t0
            ext = MIME_TO_EXT.get(result.mime, "bin")
            fname = f"{i:02d}.{ext}"
            (out_dir / fname).write_bytes(result.data)
            duration = result.duration or probe_duration(result.data, result.mime)
            rows.append({"n": i, "file": fname, "elapsed": elapsed, "duration": duration,
                         "rtf": (elapsed / duration) if duration else None, "error": ""})
            print(f"  {engine.id:12s} {i:02d} {elapsed:6.2f}s  audio {duration or 0:5.2f}s")
        except Exception as exc:  # noqa: BLE001
            rows.append({"n": i, "file": "", "elapsed": 0, "duration": None, "rtf": None,
                         "error": f"{type(exc).__name__}: {exc}"})
            print(f"  {engine.id:12s} {i:02d} ERROR {exc}")
    return rows


def write_index(out: Path, sentences: list[str], results: dict[str, dict]) -> None:
    engines = list(results)
    head = "".join(
        f"<th>{html.escape(eid)}<br><small>{html.escape(results[eid]['name'])}<br>"
        f"voice: {html.escape(results[eid]['voice'])}<br>"
        f"avg RTF {results[eid]['avg_rtf']:.2f}, first-sentence {results[eid]['first']:.2f}s</small></th>"
        for eid in engines
    )
    body = []
    for i, text in enumerate(sentences, 1):
        cells = []
        for eid in engines:
            row = results[eid]["rows"][i - 1]
            if row["error"]:
                cells.append(f"<td class='err'>{html.escape(row['error'])}</td>")
            else:
                cells.append(
                    f"<td><audio controls preload='none' src='{eid}/{row['file']}'></audio>"
                    f"<br><small>{row['elapsed']:.2f}s / audio {row['duration'] or 0:.2f}s</small></td>"
                )
        body.append(f"<tr><td class='n'>{i}</td><td class='txt'>{html.escape(text)}</td>{''.join(cells)}</tr>")
    doc = f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<title>PolarnikTTS – ławka odsłuchowa</title>
<style>
body{{font-family:system-ui,sans-serif;margin:20px;background:#111;color:#eee}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #333;padding:6px;vertical-align:top}}
th{{background:#222;position:sticky;top:0}} td.n{{color:#888}} td.txt{{max-width:28em}}
td.err{{color:#f66;font-size:.8em}} audio{{width:220px}} small{{color:#9a9}}
</style></head><body>
<h1>PolarnikTTS – ławka odsłuchowa</h1>
<p>Te same zdania przez każdy gotowy silnik. RTF = czas syntezy / długość audio (mniej = szybciej; &lt;1 = szybciej niż czas rzeczywisty).</p>
<table><thead><tr><th>#</th><th>Zdanie</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>
</body></html>"""
    (out / "index.html").write_text(doc, encoding="utf-8")


async def main_async(args: argparse.Namespace) -> None:
    config = Config.load(args.config)
    engines = build_engines(config.engines, config.models_dir)
    wanted = [e.strip() for e in args.engines.split(",")] if args.engines else None
    selected = {}
    for eid, eng in engines.items():
        if wanted and eid not in wanted:
            continue
        if not wanted and eid == "test_tone":
            continue
        ready, reason = eng.ensure_ready()
        if not ready:
            print(f"skip {eid}: {reason}")
            continue
        selected[eid] = eng
    if not selected:
        print("No ready engines. Check server/config.yaml and installed extras.")
        sys.exit(1)

    sentences = load_sentences(Path(args.sentences), args.limit)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for eid, eng in selected.items():
        print(f"== {eid}")
        voice = (args.voice or {}).get(eid) if isinstance(args.voice, dict) else None
        rows = await run_engine(eng, sentences, out / eid, voice, args.speed)
        ok = [r for r in rows if not r["error"] and r["rtf"]]
        results[eid] = {
            "name": eng.name, "voice": voice or eng.default_voice, "rows": rows,
            "avg_rtf": (sum(r["rtf"] for r in ok) / len(ok)) if ok else 0.0,
            "first": rows[0]["elapsed"] if rows else 0.0,
        }
    (out / "results.json").write_text(json.dumps({"sentences": sentences, "results": results}, indent=2,
                                                 ensure_ascii=False), encoding="utf-8")
    write_index(out, sentences, results)
    print(f"\nDone. Open {out / 'index.html'} in a browser.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(ROOT / "server" / "config.yaml"))
    p.add_argument("--sentences", default=str(ROOT / "bench" / "sentences_pl.txt"))
    p.add_argument("--out", default=str(ROOT / "bench" / "out"))
    p.add_argument("--engines", default="", help="comma-separated engine ids (default: all ready except test_tone)")
    p.add_argument("--voice", default=None, help='JSON map engine->voice, e.g. \'{"edge_tts":"pl-PL-MarekNeural"}\'')
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--limit", type=int, default=None, help="only the first N sentences")
    args = p.parse_args()
    if args.voice:
        args.voice = json.loads(args.voice)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
