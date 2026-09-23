// Content script (isolated world): the voice-over pipeline for the current YouTube video.
//   captions (sniffed /api/timedtext, json3) -> sentences -> translation (YouTube tlang or
//   server) -> look-ahead synthesis (server /tts) -> scheduled playback synced with the
//   video, with ducking of the original audio. Player-bar button toggles it.

(async () => {
  const TAG = "[PolarnikTTS]";
  const { ServerClient } = await import(chrome.runtime.getURL("lib/api.js"));
  const { loadSettings, saveSettings, onSettingsChanged, RESTART_KEYS } = await import(chrome.runtime.getURL("lib/settings.js"));
  const { createPanel } = await import(chrome.runtime.getURL("content/panel.js"));
  const { eventsToLines, linesToSentences, isPolishLike, parseTimedtext } = await import(chrome.runtime.getURL("content/captions.js"));

  const log = (...a) => console.info(TAG, ...a);
  const warn = (...a) => console.warn(TAG, ...a);

  // ---- bridge to page.js (MAIN world) ------------------------------------------------
  let reqId = 0;
  const pending = new Map();
  window.addEventListener("message", (ev) => {
    if (ev.source !== window || ev.data?.__polarnik !== "resp") return;
    const p = pending.get(ev.data.id);
    if (p) { pending.delete(ev.data.id); p(ev.data.result); }
  });
  function page(cmd, args = {}) {
    return new Promise((resolve) => {
      const id = ++reqId;
      pending.set(id, resolve);
      window.postMessage({ __polarnik: "req", id, cmd, args }, "*");
      setTimeout(() => { if (pending.delete(id)) resolve({ error: "page bridge timeout" }); }, 3000);
    });
  }

  // ---- state ----------------------------------------------------------------------
  let settings = await loadSettings();
  let session = null;      // active VoiceOverSession for the current video
  let notice = "";           // user-visible remark for the current video (cleared on restart)
  let button = null;       // player-bar button element
  let panel = null;        // in-player settings panel

  onSettingsChanged((s) => {
    const needsRestart = RESTART_KEYS.some((k) => s[k] !== settings[k]);
    const wasEnabled = settings.enabled;
    settings = s;
    updateButton();
    panel?.rerender();
    session?.applyLiveSettings();
    if (!s.enabled) { session?.destroy(); session = null; }
    else if (!session || needsRestart || !wasEnabled) restartSession();
  });
  // slider being dragged in the panel: preview the voice volume without saving
  window.addEventListener("polarnik-live", (ev) => {
    if (ev.detail?.voiceVolume !== undefined && session?.current) session.current.el.volume = ev.detail.voiceVolume;
  });

  // ---- player-bar button ----------------------------------------------------------
  const ICON = `<svg viewBox="0 0 36 36" width="100%" height="100%"><rect x="6" y="6" width="24" height="24" rx="5" fill="currentColor" opacity=".18"/><text x="18" y="25" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="17" fill="currentColor">P</text><circle class="polarnik-dot" cx="27" cy="9" r="4"/></svg>`;

  function ensureButton() {
    if (button && document.contains(button)) return button;
    const controls = document.querySelector(".ytp-right-controls");
    if (!controls) return null;
    button = document.createElement("button");
    button.className = "ytp-button polarnik-btn";
    button.innerHTML = ICON;
    button.addEventListener("click", () => {
      if (!panel) {
        const host = document.querySelector(".html5-video-player") || controls.parentElement;
        panel = createPanel({
          container: host,
          getSettings: () => settings,
          saveSettings,
          client: () => new ServerClient(settings.serverUrl, settings.serverToken),
          onServerStarted: () => restartSession(),
        });
      }
      panel.toggle();
    });
    controls.insertBefore(button, controls.firstChild);
    updateButton();
    return button;
  }

  function modeLabel(mode) {
    return { polish: "polskie napisy", youtube: "tłumaczenie YouTube", server: "tłumaczenie serwera" }[mode] || "…";
  }

  function updateButton(status, detail) {
    if (!button) return;
    const st = !settings.enabled ? "off" : (status || session?.status || "idle");
    button.dataset.status = st;
    const engine = settings.engine || "domyślny";
    const voice = settings.voice ? ` / ${settings.voice}` : "";
    const msgs = {
      off: "PolarnikTTS: wyłączony (kliknij, aby włączyć)",
      idle: `PolarnikTTS: włączony – ${engine}${voice}`,
      loading: "PolarnikTTS: pobieram napisy…",
      working: session?.hold ? "PolarnikTTS: tłumaczę pierwsze zdania (LLM)…"
        : `PolarnikTTS: lektor aktywny (${modeLabel(session?.mode)}) – ${engine}${voice}` + (notice ? ` · ${notice}` : ""),
      nocaptions: "PolarnikTTS: ten film nie ma napisów",
      error: `PolarnikTTS: błąd – ${detail || session?.lastError || "?"}`,
    };
    button.title = msgs[st] || msgs.idle;
  }

  // ---- ducking of the original audio ----------------------------------------------
  class Ducker {
    constructor(video) {
      this.video = video;
      this.base = video.volume;
      this.ducked = false;
      this.ourValue = null;
      this.timer = null;
      video.addEventListener("volumechange", () => {
        if (this.ourValue !== null && Math.abs(video.volume - this.ourValue) < 0.005) return; // our own change
        this.base = video.volume;                  // user moved the slider
        if (this.ducked) this.apply(true);
      });
    }
    factor() { return Math.pow(10, settings.duckingDb / 20); }
    apply(on) {
      this.ducked = on;
      const target = on ? this.base * this.factor() : this.base;
      clearInterval(this.timer);
      const steps = 6, from = this.video.volume, step = (target - from) / steps;
      let i = 0;
      this.timer = setInterval(() => {
        i++;
        const v = i >= steps ? target : from + step * i;
        this.ourValue = Math.max(0, Math.min(1, v));
        this.video.volume = this.ourValue;
        if (i >= steps) clearInterval(this.timer);
      }, 25);
    }
    release() { clearInterval(this.timer); if (this.ducked) { this.ducked = false; this.ourValue = this.base; this.video.volume = this.base; } }
  }

  // ---- the session: one per video ------------------------------------------------
  class VoiceOverSession {
    constructor(videoId, video, forceYoutube = false) {
      this.videoId = videoId;
      this.video = video;
      this.status = "loading";
      this.lastError = "";
      this.sentences = [];
      this.audio = new Map();       // index -> {url, duration}
      this.inflight = new Set();    // indices being synthesized
      this.translating = new Set(); // indices being translated
      this.cursor = 0;
      this.current = null;          // {index, el}
      this.destroyed = false;
      this.translateFailures = 0;   // consecutive failed translation batches
      this.translatedCount = 0;
      this.forceYoutube = forceYoutube;
      this.hold = null;             // {until} while the video is paused waiting for the first LLM batch
      this.client = new ServerClient(settings.serverUrl, settings.serverToken);
      this.nativeSpeed = true;      // does the engine honour the speed setting itself?
      this.client.engines().then((list) => {
        const eng = list.find((x) => x.id === (settings.engine || "")) || list.find((x) => x.id === "edge_tts");
        if (eng && eng.native_speed === false) this.nativeSpeed = false;
      }).catch(() => {});
      this.ducker = new Ducker(video);
      this.lastTime = video.currentTime;
      this.tick = this.tick.bind(this);
      this.timer = setInterval(this.tick, 100);
      this.start().catch((e) => this.fail(String(e?.message || e)));
    }

    fail(msg) { this.lastError = msg; this.status = "error"; warn("session error:", msg); updateButton("error", msg); }

    async start() {
      updateButton("loading");
      const events = await this.loadCaptions();
      if (this.destroyed) return;
      if (!events) return;
      const lines = eventsToLines(events);
      this.sentences = linesToSentences(lines);
      log(`${this.sentences.length} sentences (${this.mode}) for ${this.videoId}`);
      if (!this.sentences.length) { this.status = "nocaptions"; updateButton(); return; }
      if (this.mode !== "server") this.sentences.forEach((s) => { s.pl = s.text; });
      else if (!this.video.paused) {
        this.hold = { until: Date.now() + 20000 };
        // the user pressing play while we hold means "go on without waiting"
        this.video.addEventListener("play", () => { this.hold = null; }, { once: true });
      }
      this.status = "working";
      updateButton();
      // Reposition the cursor to the current playhead and let tick() drive everything.
      this.cursor = this.findCursor(this.video.currentTime * 1000, true);
    }

    /** Pick the best caption track: manual Polish > manual original (English first) > auto (asr). */
    static pickTrack(tracks) {
      const base = (t) => (t.languageCode || "").split("-")[0].toLowerCase();
      return tracks.find((t) => base(t) === "pl" && !t.kind)
        || tracks.find((t) => base(t) === "en" && !t.kind)
        || tracks.find((t) => !t.kind)
        || tracks.find((t) => base(t) === "en")
        || tracks[0] || null;
    }

    /** Choose a track, have the player load it, capture the player's own response (or, as
     *  a fallback, re-fetch a sniffed URL that carries a proof-of-origin token). */
    async loadCaptions() {
      const info = await page("playerInfo");
      if (!info.ready) throw new Error("player not ready");
      // Right after navigation the player may not have its caption list yet - poll briefly
      // before concluding the video has no captions at all.
      let ct = null;
      for (let attempt = 0; attempt < 8 && !this.destroyed; attempt++) {
        ct = await page("captionTracks");
        if (!ct.ok) throw new Error(ct.error);
        if (ct.tracks.length) break;
        await new Promise((res) => setTimeout(res, 400));
      }
      if (this.destroyed) return null;
      if (!ct.tracks.length) { log("no caption tracks reported by the player"); this.status = "nocaptions"; updateButton(); return null; }
      const track = VoiceOverSession.pickTrack(ct.tracks);
      const wantLang = track.languageCode, wantKind = track.kind || "";
      this.srcLang = wantLang.split("-")[0].toLowerCase();
      if (this.srcLang === "pl") this.mode = "polish";                       // speak the Polish track as is
      else this.mode = (settings.translator === "youtube" || this.forceYoutube) ? "youtube" : "server";
      const wantTlang = this.mode === "youtube" ? "pl" : "";
      log("caption tracks:", ct.tracks.map((t) => `${t.languageCode}${t.kind ? "/" + t.kind : ""}`).join(", "),
        "-> using", wantLang, wantKind || "manual", wantTlang ? `translated to ${wantTlang} by YouTube` : "", `(${this.mode})`);

      const matches = (urlStr) => {
        try {
          const u = new URL(urlStr, location.origin);
          const q = u.searchParams;
          if (q.get("v") && q.get("v") !== this.videoId) return false;
          return (q.get("lang") || "") === wantLang && (q.get("kind") || "") === wantKind && (q.get("tlang") || "") === wantTlang;
        } catch { return false; }
      };

      // 1) maybe the player already loaded exactly this track
      let body = null;
      const already = await page("capturedTimedtext", { afterSeq: 0 });
      const hit = (already.items || []).filter((c) => matches(c.url)).pop();
      if (hit) body = hit.body;

      // 2) ask the player to load it and wait for the captured response
      if (!body) {
        const wasOn = !!ct.current.languageCode;
        let seq = already.seq || 0;
        for (let attempt = 0; attempt < 3 && !body && !this.destroyed; attempt++) {
          const r = await page("setCaptionTrack", { languageCode: wantLang, kind: wantKind, translationLanguage: wantTlang });
          if (!r.ok) throw new Error(r.error);
          const deadline = Date.now() + (attempt === 0 ? 4000 : 2500);
          while (Date.now() < deadline && !body && !this.destroyed) {
            await new Promise((res) => setTimeout(res, 150));
            const got = await page("capturedTimedtext", { afterSeq: seq });
            seq = got.seq || seq;
            const m = (got.items || []).filter((c) => matches(c.url)).pop();
            if (m) body = m.body;
          }
          if (!body) {
            // 3) fallback: re-fetch a sniffed URL, but only one that carries a pot token
            body = await this.refetchSniffed(wantLang, wantKind, wantTlang);
          }
          if (!body) { log(`no caption body yet (attempt ${attempt + 1}), retrying`); page("hideCaptions"); await new Promise((res) => setTimeout(res, 400)); }
        }
        // Leave the captions as the user had them: hidden, or their previous track.
        if (!wasOn) page("hideCaptions");
        else page("setCaptionTrack", { languageCode: ct.current.languageCode, kind: ct.current.kind, translationLanguage: ct.current.translationLanguage });
      }
      if (!body) throw new Error("YouTube nie zwrócił treści napisów (spróbuj odświeżyć stronę)");

      const events = parseTimedtext(body);
      if (!events) throw new Error("nieznany format napisów");
      if (this.mode === "server" && events.length) {
        const sample = eventsToLines(events).slice(0, 20).map((l) => l.text).join(" ");
        if (isPolishLike(sample)) this.mode = "polish";                       // mislabelled track
      }
      return events;
    }

    /** Fallback: re-fetch the URL the player used, if it carries a proof-of-origin token. */
    async refetchSniffed(lang, kind, tlang) {
      const entry = await chrome.runtime.sendMessage({ type: "get_timedtext" });
      if (!entry) return null;
      let u;
      try { u = new URL(entry.url); } catch { return null; }
      const q = u.searchParams;
      if (q.get("v") && q.get("v") !== this.videoId) return null;
      if (!q.get("pot")) { log("sniffed timedtext URL has no pot token - skipping re-fetch"); return null; }
      if ((q.get("lang") || "") !== lang || (q.get("kind") || "") !== kind) return null;
      q.set("fmt", "json3");
      if (tlang) q.set("tlang", tlang); else q.delete("tlang");
      try {
        const r = await fetch(u.toString(), { headers: entry.headers, credentials: "include" });
        const text = await r.text();
        if (!r.ok || text.length < 20) { log(`re-fetch gave HTTP ${r.status}, ${text.length} bytes`); return null; }
        return text;
      } catch (e) {
        warn("re-fetch failed:", e.message);
        return null;
      }
    }

    /** First sentence worth speaking at tMs. After a seek, skip a sentence whose slot is mostly over. */
    findCursor(tMs, afterSeek = false) {
      let i = 0;
      while (i < this.sentences.length) {
        const s = this.sentences[i];
        if (s.slotEnd >= tMs) {
          if (!afterSeek) break;
          const remaining = (s.slotEnd - tMs) / Math.max(1, s.slotEnd - s.start);
          if (remaining >= 0.4 || s.start >= tMs) break;
        }
        i++;
      }
      return i;
    }

    // ---- translation (server mode) --------------------------------------------
    async ensureTranslated(fromIdx, toIdx) {
      if (this.mode !== "server") return;
      const batch = [];
      for (let i = fromIdx; i <= toIdx && i < this.sentences.length; i++) {
        const s = this.sentences[i];
        if (s.pl === undefined && !this.translating.has(i)) batch.push(i);
        if (batch.length >= 8) break;
      }
      if (!batch.length) return;
      batch.forEach((i) => this.translating.add(i));
      const first = batch[0], last = batch[batch.length - 1];
      const t0 = performance.now();
      try {
        const res = await this.client.translate({
          sentences: batch.map((i) => this.sentences[i].text),
          sourceLang: this.srcLang || "auto",
          contextBefore: this.sentences.slice(Math.max(0, first - 3), first).map((s) => s.pl || s.text),
          contextAfter: this.sentences.slice(last + 1, last + 4).map((s) => s.text),
          translator: settings.translator,
        });
        res.translations.forEach((t, k) => { this.sentences[batch[k]].pl = t; });
        this.translatedCount += batch.length;
        this.translateFailures = 0;
        log(`translated ${batch.length} sentences (${first}-${last}) in ${Math.round(performance.now() - t0)} ms`);
      } catch (e) {
        if (this.destroyed) return;
        this.translateFailures++;
        warn(`translation failed (${this.translateFailures}):`, e.message);
        this.lastError = `tłumaczenie: ${e.message}`;
        if (this.translateFailures >= 2) {
          // Reading the untranslated text aloud would be useless - switch this video to
          // YouTube's auto-translate instead and say so in the button tooltip / popup.
          const why = e.message.replace(/^\/translate: /, "");
          notice = `tłumacz „${settings.translator}” nie działa (${why.slice(0, 160)}) – ten film leci przez tłumaczenie YouTube`;
          warn(notice);
          setTimeout(() => restartSession({ forceYoutube: true, notice }), 0);
          return;
        }
        // leave the sentences untranslated so the next tick retries them after a short pause
        await new Promise((res) => setTimeout(res, 1500));
      } finally {
        batch.forEach((i) => this.translating.delete(i));
      }
    }

    // ---- synthesis ---------------------------------------------------------------
    async ensureSynthesized(fromIdx, toIdx) {
      let started = 0;
      for (let i = fromIdx; i <= toIdx && i < this.sentences.length; i++) {
        if (this.inflight.size >= 2 || started >= 2) break;
        const s = this.sentences[i];
        if (this.audio.has(i) || this.inflight.has(i) || s.pl === undefined || !s.pl) continue;
        this.inflight.add(i);
        started++;
        this.synthesize(i).finally(() => this.inflight.delete(i));
      }
    }

    async synthesize(i) {
      const s = this.sentences[i];
      try {
        const res = await this.client.tts({ text: s.pl, engine: settings.engine, voice: settings.voice, speed: settings.speed });
        if (this.destroyed) return;
        const url = URL.createObjectURL(res.blob);
        let duration = res.duration;
        if (!duration) duration = await probeDuration(url);
        this.audio.set(i, { url, duration });
      } catch (e) {
        warn(`tts failed for #${i}:`, e.message);
        this.lastError = /Failed to fetch/i.test(e.message) ? "serwer niedostępny (otwórz panel P → Uruchom serwer)" : `TTS: ${e.message}`;
        this.audio.set(i, { url: null, duration: 0, error: e.message });
        updateButton("error", this.lastError);
      }
    }

    // ---- playback ----------------------------------------------------------------
    tick() {
      if (this.destroyed || this.status !== "working") return;
      const v = this.video;
      const tMs = v.currentTime * 1000 + settings.offsetMs;

      // seek detection
      if (Math.abs(v.currentTime - this.lastTime) > 1.5) {
        this.stopCurrent();
        this.cursor = this.findCursor(tMs, true);
      }
      this.lastTime = v.currentTime;

      // pause / resume
      if (this.current) {
        if (v.paused && !this.current.el.paused) this.current.el.pause();
        else if (!v.paused && this.current.el.paused && !this.current.el.ended) this.current.el.play().catch(() => {});
      }

      // LLM translation of the first batch takes a few seconds; hold the video until the
      // sentence at the playhead has its audio, so the user does not get a silent start.
      if (this.hold) {
        const idx = this.findCursor(tMs);
        const ready = idx >= this.sentences.length || this.sentences[idx].start > tMs + 3000 || this.audio.has(idx);
        if (ready || Date.now() > this.hold.until || this.translateFailures) {
          this.hold = null;
          if (v.paused) v.play().catch(() => {});
          updateButton();
        } else {
          if (!v.paused) v.pause();
          this.ensureTranslated(this.cursor, this.findCursor(tMs + settings.lookaheadS * 1000));
          this.ensureSynthesized(this.cursor, this.cursor + 1);
          return;
        }
      }
      if (v.paused) return;

      // keep the pipeline ahead of the playhead
      const horizon = tMs + settings.lookaheadS * 1000;
      const lastIdx = this.findCursor(horizon);
      this.ensureTranslated(this.cursor, lastIdx);
      this.ensureSynthesized(this.cursor, Math.max(this.cursor + 1, lastIdx));

      if (this.current) return;

      // skip sentences whose slot is over (we could not speak them in time)
      while (this.cursor < this.sentences.length && this.sentences[this.cursor].slotEnd < tMs - 300) {
        const a = this.audio.get(this.cursor);
        if (a?.url) { URL.revokeObjectURL(a.url); this.audio.delete(this.cursor); }
        this.cursor++;
      }
      if (this.cursor >= this.sentences.length) return;
      const s = this.sentences[this.cursor];
      if (s.start > tMs) return;                   // not yet time
      const a = this.audio.get(this.cursor);
      if (!a) return;                              // still synthesizing; tick again in 100 ms
      if (!a.url) { this.cursor++; return; }       // synthesis error - skip
      this.play(this.cursor, a, tMs);
    }

    play(index, a, tMs) {
      const s = this.sentences[index];
      const el = new Audio(a.url);
      el.preservesPitch = true;
      el.volume = Math.max(0, Math.min(1, settings.voiceVolume));
      // fit the audio into the remaining slot: speed the voice up (never slower than 1x),
      // or - in "video" lag mode - slow the video down instead when 1x would not fit
      // engines without a native speed parameter: apply the speaking-rate setting here
      const base = this.nativeSpeed ? 1.0 : Math.max(0.5, Math.min(2.0, settings.speed || 1.0));
      const available = Math.max(0.4, (s.slotEnd - tMs) / 1000);
      const needed = a.duration ? (a.duration / base) / available : 1.0;
      let rate = 1.0;
      if (needed > 1.0) {
        if (settings.lagMode === "video") {
          rate = Math.min(1.1, needed);
          if (needed > 1.1) this.slowVideo(Math.max(0.5, 1.1 / needed));
        } else {
          rate = Math.min(settings.maxRate, needed);
        }
      }
      el.playbackRate = rate * base;
      const late = (tMs - s.start) / 1000;
      if (late > 0.35 && a.duration && late < a.duration - 0.5) el.currentTime = late * 0.5; // catch up a bit
      this.current = { index, el };
      this.ducker.apply(true);
      const done = () => {
        if (this.current?.el !== el) return;
        this.current = null;
        this.cursor = index + 1;
        this.restoreVideoRate();
        URL.revokeObjectURL(a.url);
        this.audio.delete(index);
        // keep ducked if the next sentence is imminent
        const next = this.sentences[index + 1];
        if (!next || next.start - this.video.currentTime * 1000 > 800) this.ducker.apply(false);
      };
      el.addEventListener("ended", done);
      el.addEventListener("error", done);
      el.play().catch((e) => { warn("audio play failed:", e.message); done(); });
    }

    /** Live-applicable settings (volume, ducking) for the sentence being spoken. */
    applyLiveSettings() {
      if (this.current) this.current.el.volume = Math.max(0, Math.min(1, settings.voiceVolume));
      if (this.ducker.ducked) this.ducker.apply(true);
    }

    slowVideo(factor) {
      if (this.savedRate === undefined) this.savedRate = this.video.playbackRate;
      this.video.playbackRate = Math.round(factor * 20) / 20;
    }

    restoreVideoRate() {
      if (this.savedRate !== undefined) { this.video.playbackRate = this.savedRate; this.savedRate = undefined; }
    }

    stopCurrent() {
      if (!this.current) return;
      const { el, index } = this.current;
      this.current = null;
      this.restoreVideoRate();
      el.pause();
      const a = this.audio.get(index);
      if (a?.url) URL.revokeObjectURL(a.url);
      this.audio.delete(index);
      this.ducker.apply(false);
    }

    destroy() {
      this.destroyed = true;
      clearInterval(this.timer);
      this.stopCurrent();
      this.restoreVideoRate();
      for (const a of this.audio.values()) if (a.url) URL.revokeObjectURL(a.url);
      this.audio.clear();
      this.ducker.release();
      if (this.status === "working") this.status = "idle";
    }
  }

  function probeDuration(url) {
    return new Promise((resolve) => {
      const el = new Audio(url);
      el.addEventListener("loadedmetadata", () => resolve(isFinite(el.duration) ? el.duration : 0));
      el.addEventListener("error", () => resolve(0));
    });
  }

  // ---- page lifecycle ---------------------------------------------------------------
  function currentVideoId() {
    return location.pathname === "/watch" ? new URLSearchParams(location.search).get("v") : null;
  }

  async function restartSession(opts = {}) {
    session?.destroy();
    session = null;
    notice = opts.notice || "";
    const videoId = currentVideoId();
    const video = document.querySelector("video.html5-main-video");
    if (!videoId || !video || !settings.enabled) { updateButton(); return; }
    // wait for the player bridge
    for (let i = 0; i < 20; i++) {
      const info = await page("playerInfo");
      if (info.ready && info.videoId === videoId) break;
      await new Promise((r) => setTimeout(r, 250));
    }
    session = new VoiceOverSession(videoId, video, !!opts.forceYoutube);
  }

  function onNavigate() {
    ensureButton();
    const videoId = currentVideoId();
    if (!videoId) { session?.destroy(); session = null; return; }
    if (session && session.videoId === videoId && !session.destroyed) return;
    restartSession();
  }

  document.addEventListener("yt-navigate-finish", onNavigate);
  document.addEventListener("yt-page-data-updated", () => ensureButton());
  // The player bar may appear after the script; poll briefly for it.
  const btnPoll = setInterval(() => { if (ensureButton()) clearInterval(btnPoll); }, 500);
  setTimeout(() => clearInterval(btnPoll), 30000);

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg?.type === "restart") { restartSession(); sendResponse({ ok: true }); return false; }
    if (msg?.type === "page_info") {
      sendResponse({
        videoId: currentVideoId(),
        status: session ? session.status : (settings.enabled ? "idle" : "off"),
        sentences: session?.sentences.length || 0,
        cursor: session?.cursor || 0,
        mode: session?.mode || null,
        lastError: session?.lastError || "",
        notice,
        translated: session?.translatedCount || 0,
        holding: !!session?.hold,
      });
    }
    return false;
  });

  log("content script loaded");
  onNavigate();
})();
