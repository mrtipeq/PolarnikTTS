// MAIN-world bridge: the only place with access to the YouTube player API
// (document.getElementById("movie_player")) and to the player's own network calls.
// Runs at document_start so the fetch/XHR hooks are in place before the player loads.
// Talks to content.js via window.postMessage.

(() => {
  if (window.__polarnikPageBridge) return;
  window.__polarnikPageBridge = true;

  const player = () => document.getElementById("movie_player");

  // ---- capture the player's own /api/timedtext responses ------------------------------
  // YouTube answers timedtext requests without a valid proof-of-origin token ("pot") with an
  // empty 200 body, so re-fetching a sniffed URL is unreliable. Forwarding the body the
  // player itself received sidesteps that entirely.
  const captured = [];                      // last few {url, body, ts}
  let capturedSeq = 0;
  function forward(url, body, status = 200) {
    if (!body || body.length < 20) return;   // empty answers are the pot race, ignore them
    // status >= 400 (e.g. 429 "too many requests" for YouTube's auto-translation) is kept as
    // a failed item so content.js can tell "rate limited" from "nothing arrived"
    captured.push({ url: String(url), body: status >= 400 ? body.slice(0, 300) : body, status, ts: Date.now(), seq: ++capturedSeq });
    while (captured.length > 6) captured.shift();
    window.postMessage({ __polarnik: "timedtext", url: String(url), seq: capturedSeq }, "*");
  }

  // Every timedtext URL the page requests, also those our hooks do not see (made before them,
  // from a worker, ...). A PerformanceObserver keeps reporting after the page's Resource
  // Timing buffer (250 entries, full within minutes on YouTube) has filled up.
  const seenUrls = [];
  function rememberUrl(url) {
    if (!url || !url.includes("/api/timedtext") || seenUrls.includes(url)) return;
    seenUrls.push(url);
    while (seenUrls.length > 40) seenUrls.shift();
  }
  try {
    new PerformanceObserver((list) => { for (const e of list.getEntries()) rememberUrl(e.name); })
      .observe({ type: "resource", buffered: true });
  } catch { /* ignore */ }
  const knownUrls = () => {
    const out = captured.map((c) => c.url).concat(seenUrls);
    try { for (const e of performance.getEntriesByType("resource")) if (e.name.includes("/api/timedtext")) out.push(e.name); } catch { /* ignore */ }
    return out;
  };

  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : (input?.url || input?.href);
    const p = origFetch.apply(this, arguments);
    if (url && url.includes("/api/timedtext")) {
      rememberUrl(String(url));
      p.then((res) => { try { res.clone().text().then((t) => forward(url, t, res.status)).catch(() => {}); } catch { /* ignore */ } })
        .catch(() => {});
    }
    return p;
  };

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__polarnikUrl = typeof url === "string" ? url : String(url);
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    if (this.__polarnikUrl && this.__polarnikUrl.includes("/api/timedtext")) {
      rememberUrl(this.__polarnikUrl);
      this.addEventListener("load", () => {
        try {
          const rt = this.responseType;
          const st = this.status;
          if (rt === "" || rt === "text") forward(this.__polarnikUrl, this.responseText, st);
          else if (rt === "json") forward(this.__polarnikUrl, JSON.stringify(this.response), st);
          else if (rt === "arraybuffer" && this.response) forward(this.__polarnikUrl, new TextDecoder().decode(this.response), st);
          else if (rt === "blob" && this.response) this.response.text().then((t) => forward(this.__polarnikUrl, t, st)).catch(() => {});
        } catch { /* ignore */ }
      });
    }
    return origSend.apply(this, arguments);
  };

  // ---- player API handlers ---------------------------------------------------------------
  const handlers = {
    playerInfo() {
      const p = player();
      if (!p) return { ready: false };
      let videoId = null;
      try { videoId = p.getVideoData()?.video_id || null; } catch { /* ignore */ }
      return { ready: true, videoId, ad: p.classList.contains("ad-showing") };
    },

    // Load the captions module and list the available tracks plus the one currently shown.
    // Several sources are merged, because each of them can be empty on its own:
    //  - the captions module's tracklist (empty until the module has loaded; without
    //    {includeAsr: true} it leaves out auto-generated tracks),
    //  - the player response of the current video (getPlayerResponse, ytInitialPlayerResponse,
    //    the watch page's own data) - lists every track, "asr" included,
    //  - timedtext requests the player has already made for this video (our hooks and the
    //    Resource Timing list): if the player fetched a track, the track exists.
    captionTracks() {
      const p = player();
      if (!p) return { ok: false, error: "no player" };
      try {
        if (typeof p.loadModule === "function") p.loadModule("captions");
        let videoId = "";
        try { videoId = p.getVideoData()?.video_id || ""; } catch { /* ignore */ }
        const tracks = [];
        const seen = new Set();
        const diag = { module: 0, response: 0, page: 0, requests: 0 };
        const add = (languageCode, kind, name, source) => {
          if (!languageCode) return;
          const key = `${languageCode}|${kind || ""}`;
          if (seen.has(key)) return;
          seen.add(key);
          tracks.push({ languageCode, kind: kind || "", name: name || "", source });
        };
        const fromVss = (vss) => {                 // ".en" = manual English, "a.en" = auto English
          const m = /^(a?)\.(.+)$/.exec(String(vss || ""));
          return m ? { languageCode: m[2], kind: m[1] ? "asr" : "" } : null;
        };
        const addModuleTrack = (t) => {
          if (!t) return;
          const v = fromVss(t.vss_id || t.vssId);
          add(t.languageCode || t.language_code || v?.languageCode, t.kind || v?.kind, t.displayName || t.languageName || t.name, "module");
        };
        const moduleLists = [];
        const ad = p.classList.contains("ad-showing");   // during an ad the captions module describes the ad
        if (!ad) try { moduleLists.push(p.getOption("captions", "tracklist", { includeAsr: true }) || []); } catch { /* ignore */ }
        if (!ad) try { moduleLists.push(p.getOption("captions", "tracklist") || []); } catch { /* ignore */ }
        for (const list of moduleLists) for (const t of list) { diag.module++; addModuleTrack(t); }

        const addResponseTracks = (pr, source) => {
          if (!pr) return 0;
          const vid = pr.videoDetails?.videoId;
          if (videoId && vid && vid !== videoId) return 0;        // stale data of the previous video
          const list = pr.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
          for (const t of list) {
            const v = fromVss(t.vssId);
            const name = t.name?.simpleText || (t.name?.runs || []).map((r) => r.text).join("") || "";
            add(t.languageCode || v?.languageCode, t.kind || v?.kind, name, source);
          }
          return list.length;
        };
        try { diag.response += addResponseTracks(typeof p.getPlayerResponse === "function" ? p.getPlayerResponse() : null, "response"); } catch { /* ignore */ }
        try { diag.page += addResponseTracks(window.ytInitialPlayerResponse, "initial"); } catch { /* ignore */ }
        try {
          const flexy = document.querySelector("ytd-watch-flexy");
          diag.page += addResponseTracks(flexy?.playerData || flexy?.__data?.playerData, "page");
        } catch { /* ignore */ }

        const addFromUrl = (url) => {
          try {
            const q = new URL(url, location.origin).searchParams;
            if (videoId && q.get("v") && q.get("v") !== videoId) return;
            if (!q.get("lang")) return;
            diag.requests++;
            add(q.get("lang"), q.get("kind") || "", "", "request");
          } catch { /* ignore */ }
        };
        for (const u of knownUrls()) addFromUrl(u);

        let current = {};
        try { current = p.getOption("captions", "track") || {}; } catch { /* ignore */ }
        return {
          ok: true, videoId, tracks, diag, ad,
          current: {
            languageCode: current.languageCode || "", kind: current.kind || "",
            translationLanguage: current.translationLanguage?.languageCode || "",
          },
        };
      } catch (e) {
        return { ok: false, error: String(e) };
      }
    },

    // Make the player load a caption track (optionally auto-translated by YouTube) so that
    // its response can be captured by the hooks above.
    setCaptionTrack({ languageCode, kind, translationLanguage }) {
      const p = player();
      if (!p) return { ok: false, error: "no player" };
      try {
        const opt = { languageCode, ...(kind ? { kind } : {}) };
        if (translationLanguage) opt.translationLanguage = { languageCode: translationLanguage };
        p.setOption("captions", "track", opt);
        return { ok: true };
      } catch (e) {
        return { ok: false, error: String(e) };
      }
    },

    // Fetch a caption track ourselves, from a timedtext URL the player has already used for
    // this video (it carries the proof-of-origin token "pot", without which YouTube answers
    // with an empty body). Works even when the player made the request before our hooks or
    // in a way they do not see: the URL is also taken from the Resource Timing list. A URL of
    // the same track with another translation is adapted (tlang added / removed).
    async fetchTimedtext({ videoId, lang, kind, tlang }) {
      const urls = knownUrls();
      const candidates = [];
      for (const raw of urls.reverse()) {
        let u;
        try { u = new URL(raw, location.origin); } catch { continue; }
        const q = u.searchParams;
        if (!q.get("pot") || (videoId && q.get("v") !== videoId)) continue;
        if ((q.get("lang") || "") !== lang || (q.get("kind") || "") !== (kind || "")) continue;
        const exact = (q.get("tlang") || "") === (tlang || "");
        if (tlang) q.set("tlang", tlang); else q.delete("tlang");
        q.set("fmt", "json3");
        candidates.push({ url: u.toString(), exact });
      }
      candidates.sort((a, b) => Number(b.exact) - Number(a.exact));
      const tried = new Set();
      const tries = [];
      let rateLimited = false;
      for (const c of candidates) {
        if (tried.has(c.url)) continue;
        tried.add(c.url);
        try {
          const r = await origFetch(c.url, { credentials: "include" });
          const body = await r.text();
          tries.push(`HTTP ${r.status} ${body.length} chars${c.exact ? "" : " (tlang adapted)"}`);
          if (r.status === 429) rateLimited = true;
          if (r.ok && body.length >= 20) return { ok: true, body, url: c.url, candidates: candidates.length, urls: urls.length };
        } catch (e) { tries.push(String(e).slice(0, 80)); }
      }
      return { ok: false, candidates: candidates.length, urls: urls.length, tries, rateLimited };
    },

    // Captured timedtext responses newer than `afterSeq` (bodies included).
    capturedTimedtext({ afterSeq }) {
      return { items: captured.filter((c) => c.seq > (afterSeq || 0)), seq: capturedSeq };
    },

    hideCaptions() {
      const p = player();
      try { p?.setOption("captions", "track", {}); return { ok: true }; } catch (e) { return { ok: false, error: String(e) }; }
    },

    setPlaybackRate({ rate }) {
      const p = player();
      try { p?.setPlaybackRate(rate); return { ok: true }; } catch (e) { return { ok: false, error: String(e) }; }
    },
  };

  window.addEventListener("message", (ev) => {
    if (ev.source !== window || !ev.data || ev.data.__polarnik !== "req") return;
    const { id, cmd, args } = ev.data;
    Promise.resolve()
      .then(() => (handlers[cmd] ? handlers[cmd](args || {}) : { error: `unknown cmd ${cmd}` }))
      .catch((e) => ({ error: String(e) }))
      .then((result) => window.postMessage({ __polarnik: "resp", id, result }, "*"));
  });
})();
