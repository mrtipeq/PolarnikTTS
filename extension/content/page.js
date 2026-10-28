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
  function forward(url, body) {
    if (!body || body.length < 20) return;   // empty answers are the pot race, ignore them
    captured.push({ url: String(url), body, ts: Date.now(), seq: ++capturedSeq });
    while (captured.length > 6) captured.shift();
    window.postMessage({ __polarnik: "timedtext", url: String(url), seq: capturedSeq }, "*");
  }

  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : input?.url;
    const p = origFetch.apply(this, arguments);
    if (url && url.includes("/api/timedtext")) {
      p.then((res) => { try { res.clone().text().then((t) => forward(url, t)).catch(() => {}); } catch { /* ignore */ } })
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
      this.addEventListener("load", () => {
        try { if (this.responseType === "" || this.responseType === "text") forward(this.__polarnikUrl, this.responseText); } catch { /* ignore */ }
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
      return { ready: true, videoId };
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
        try { moduleLists.push(p.getOption("captions", "tracklist", { includeAsr: true }) || []); } catch { /* ignore */ }
        try { moduleLists.push(p.getOption("captions", "tracklist") || []); } catch { /* ignore */ }
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
        for (const c of captured) addFromUrl(c.url);
        try {
          for (const e of performance.getEntriesByType("resource")) if (e.name.includes("/api/timedtext")) addFromUrl(e.name);
        } catch { /* ignore */ }

        let current = {};
        try { current = p.getOption("captions", "track") || {}; } catch { /* ignore */ }
        return {
          ok: true, videoId, tracks, diag,
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
    let result;
    try {
      result = handlers[cmd] ? handlers[cmd](args || {}) : { error: `unknown cmd ${cmd}` };
    } catch (e) {
      result = { error: String(e) };
    }
    window.postMessage({ __polarnik: "resp", id, result }, "*");
  });
})();
