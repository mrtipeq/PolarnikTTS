# PolarnikTTS architecture

## Overview

```
 YouTube page (content script)                     engine server (Python, FastAPI)
 ┌──────────────────────────────────────┐          ┌──────────────────────────────────┐
 │ timedtext sniff (service worker)     │          │ /translate  ─► translator plugin │
 │   └► json3 caption events            │  HTTP    │               (LLM / DeepL)      │
 │ sentence reconstruction              │ ───────► │ /tts        ─► engine plugin     │
 │ translation (server or YouTube tlang)│ ◄─────── │               (edge/chatterbox/  │
 │ look-ahead synthesis queue (20-60 s) │  audio   │                xtts/piper/11labs)│
 │ duration fitting (time-stretch)      │          │ audio cache (sha256 of request)  │
 │ Web Audio scheduler + ducking        │          └──────────────────────────────────┘
 └──────────────────────────────────────┘
```

The server may run on the same PC (`127.0.0.1`) or on another machine in the LAN; the
extension asks for the host permission of a non-local address at runtime
(`optional_host_permissions`).

## Design decisions

- **Look-ahead, not real-time.** For normal videos the whole caption track is known up front,
  so speech is synthesized ahead of the playhead. Engine latency only matters after play/seek.
  Live streams are a separate mode (later iteration).
- **Everything selectable.** Server location, TTS engine, voice, translator - all runtime
  settings. The server reports what is *ready* on that machine (dependencies, models, keys,
  CUDA), the options page shows only that.
- **Plugins.** `server/polarnik_server/engines/*.py` (subclass `Engine`) and
  `server/polarnik_server/translators/*.py` (subclass `Translator`), registered in the
  package `__init__`. Config keys under `engines:` / `translators:` select and configure them.
- **No build step for the extension.** Plain ES modules (MV3 `type: module` service worker),
  so `Load unpacked` works straight from the repository. A bundler can be added later.
- **Cache first.** `/tts` results are cached by `(engine, voice, speed, text)`; re-watching a
  video or seeking back replays instantly.

## Extension internals (target state)

- `background/sw.js` - `webRequest.onBeforeSendHeaders` on `*/api/timedtext*` records the
  caption URL and `x-*` headers per tab; `fetch_timedtext` re-fetches it as `fmt=json3`
  (with `tlang=pl` when the YouTube translator is selected).
- `content/content.js` (isolated world) - orchestrates the pipeline, owns the `AudioContext`,
  talks to the server with `fetch`.
- `content/page.js` (MAIN world, iteration 3) - access to the player API
  (`getPlayer()`, `captionTracks`, playback rate); bridged with `window.postMessage`.
- Sentence reconstruction: merge `events[].segs[]` on sentence punctuation or gaps > 700 ms;
  keep `tStartMs` of the first and `tStartMs + dDurationMs` of the last event as the slot.
- Scheduling: `AudioContext.currentTime` is mapped to `video.currentTime` on every
  `timeupdate`; buffers are scheduled with `AudioBufferSourceNode.start(at)`; pause/seek
  flushes the queue. Ducking uses a `GainNode` on a `MediaElementSource` of the video with
  150 ms ramps.
- Duration fitting: if audio is longer than `slot * 1.15`, apply pitch-preserving stretch up
  to 1.25x; beyond that, ask the translator to condense the sentence and re-synthesize.
  Slowing the video down is opt-in only.

## Server API

See README. All endpoints except `/health` honour the optional bearer token.
