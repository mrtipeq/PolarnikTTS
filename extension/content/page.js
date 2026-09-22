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
    captionTracks() {
      const p = player();
      if (!p) return { ok: false, error: "no player" };
      try {
        if (typeof p.loadModule === "function") p.loadModule("captions");
        const tracks = (p.getOption("captions", "tracklist") || []).map((t) => ({
          languageCode: t.languageCode, kind: t.kind || "", name: t.displayName || t.languageName || "",
        }));
        const current = p.getOption("captions", "track") || {};
        return {
          ok: true, tracks,
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
