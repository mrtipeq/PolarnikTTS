// In-player settings panel (YouTube-menu look). Two levels: main list and choice submenus.
// Every change is saved to chrome.storage immediately; the pipeline reacts through
// onSettingsChanged in content.js.

export function createPanel({ container, getSettings, saveSettings, client, onClose, onServerStarted }) {
  const root = document.createElement("div");
  root.className = "polarnik-panel";
  root.hidden = true;
  container.appendChild(root);
  // The panel lives inside the player: keep clicks/keys from reaching YouTube's own handlers
  // (click = play/pause, double-click = fullscreen, keys = shortcuts).
  for (const type of ["click", "dblclick", "mousedown", "mouseup", "keydown", "keyup", "wheel", "touchstart"]) {
    root.addEventListener(type, (e) => e.stopPropagation());
  }

  let engines = [];        // from the server, refreshed when the panel opens
  let translators = [];
  let serverUp = false;
  let serverMsg = "";      // transient status of the start button
  let view = { kind: "main" };

  const fmt = {
    pct: (v) => `${Math.round(v * 100)}%`,
    db: (v) => `${v} dB`,
    ms: (v) => `${v > 0 ? "+" : ""}${v} ms`,
    x: (v) => `${Number(v).toFixed(2)}×`,
    s: (v) => `${v} s`,
  };

  function engineName(id) {
    if (!id) return "domyślny serwera";
    const e = engines.find((x) => x.id === id);
    return e ? e.name : id;
  }
  function voiceName(engineId, voiceId) {
    if (!voiceId) return "domyślny";
    const e = engines.find((x) => x.id === engineId) || engines.find((x) => x.voices.some((v) => v.id === voiceId));
    const v = e?.voices.find((x) => x.id === voiceId);
    return v ? v.name : voiceId;
  }
  function translatorName(id) {
    if (id === "youtube") return "YouTube (automatyczne)";
    const t = translators.find((x) => x.id === id);
    return t ? t.name : id;
  }

  // ---- rows -------------------------------------------------------------------------
  function rowToggle(label, key) {
    const s = getSettings();
    const row = el("div", "polarnik-row polarnik-row-toggle");
    row.innerHTML = `<span class="polarnik-label">${label}</span><span class="polarnik-switch${s[key] ? " on" : ""}"><span class="polarnik-knob"></span></span>`;
    row.addEventListener("click", async () => {
      const next = !getSettings()[key];
      await saveSettings({ [key]: next });
      row.querySelector(".polarnik-switch").classList.toggle("on", next);
    });
    return row;
  }

  function rowChoice(label, valueText, submenu) {
    const row = el("div", "polarnik-row polarnik-row-choice");
    row.innerHTML = `<span class="polarnik-label">${label}</span><span class="polarnik-value">${escape(valueText)}</span><span class="polarnik-chevron">›</span>`;
    row.addEventListener("click", () => { view = submenu; render(); });
    return row;
  }

  function rowRange(label, key, min, max, step, format, onLive) {
    const s = getSettings();
    const row = el("div", "polarnik-row polarnik-row-range");
    row.innerHTML = `<span class="polarnik-label">${label}</span><span class="polarnik-value"></span>`
      + `<input type="range" min="${min}" max="${max}" step="${step}" value="${s[key]}">`;
    const input = row.querySelector("input");
    const value = row.querySelector(".polarnik-value");
    value.textContent = format(s[key]);
    input.addEventListener("input", () => {
      const v = parseFloat(input.value);
      value.textContent = format(v);
      onLive?.(v);
    });
    input.addEventListener("change", () => saveSettings({ [key]: parseFloat(input.value) }));
    // keep YouTube's keyboard shortcuts from stealing the slider
    input.addEventListener("keydown", (e) => e.stopPropagation());
    return row;
  }

  function el(tag, cls) { const e = document.createElement(tag); e.className = cls; return e; }
  function escape(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  // ---- views ------------------------------------------------------------------------
  function renderMain() {
    const s = getSettings();
    root.replaceChildren(
      rowToggle("Lektor włączony", "enabled"),
      rowChoice("Silnik TTS", engineName(s.engine), { kind: "engine" }),
      rowChoice("Głos", voiceName(s.engine, s.voice), { kind: "voice" }),
      rowChoice("Tłumacz napisów", translatorName(s.translator), { kind: "translator" }),
      rowRange("Głośność lektora", "voiceVolume", 0, 1, 0.05, fmt.pct, (v) => window.dispatchEvent(new CustomEvent("polarnik-live", { detail: { voiceVolume: v } }))),
      rowRange("Ściszenie oryginału", "duckingDb", -40, 0, 1, fmt.db),
      rowRange("Tempo mowy", "speed", 0.7, 1.5, 0.05, fmt.x),
      rowRange("Maks. przyspieszenie dopasowania", "maxRate", 1.0, 1.6, 0.05, fmt.x),
      rowChoice("Gdy lektor nie nadąża", s.lagMode === "video" ? "zwolnij film" : "przyspiesz lektora", { kind: "lagMode" }),
      rowRange("Przesunięcie lektora", "offsetMs", -2000, 2000, 50, fmt.ms),
      rowRange("Wyprzedzenie syntezy", "lookaheadS", 10, 90, 5, fmt.s),
    );
    const foot = el("div", "polarnik-foot");
    const status = serverMsg || (serverUp ? "serwer połączony" : "serwer niedostępny");
    foot.innerHTML = `<span class="polarnik-server-status">${escape(status)}</span>`
      + (serverUp || serverMsg ? "" : `<button type="button" class="polarnik-start">Uruchom serwer</button>`)
      + `<a href="#">Wszystkie ustawienia…</a>`;
    foot.querySelector("a").addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.sendMessage({ type: "open_options" }); });
    foot.querySelector(".polarnik-start")?.addEventListener("click", startServer);
    root.appendChild(foot);
  }

  function renderList(title, items, selected, onPick) {
    const head = el("div", "polarnik-row polarnik-head");
    head.innerHTML = `<span class="polarnik-back">‹</span><span class="polarnik-label">${title}</span>`;
    head.addEventListener("click", () => { view = { kind: "main" }; render(); });
    root.replaceChildren(head);
    if (!items.length) {
      const empty = el("div", "polarnik-row polarnik-empty");
      empty.textContent = "brak pozycji – sprawdź połączenie z serwerem";
      root.appendChild(empty);
    }
    for (const it of items) {
      const row = el("div", "polarnik-row polarnik-row-item" + (it.id === selected ? " selected" : "") + (it.disabled ? " disabled" : ""));
      row.innerHTML = `<span class="polarnik-check">${it.id === selected ? "✓" : ""}</span><span class="polarnik-label">${escape(it.name)}</span>`
        + (it.note ? `<span class="polarnik-note">${escape(it.note)}</span>` : "");
      if (!it.disabled) row.addEventListener("click", async () => { await onPick(it.id); view = { kind: "main" }; render(); });
      root.appendChild(row);
    }
  }

  function render() {
    const s = getSettings();
    if (view.kind === "main") return renderMain();
    if (view.kind === "engine") {
      const items = [{ id: "", name: "Domyślny serwera" }].concat(engines.map((e) => ({
        id: e.id, name: e.name, disabled: !e.ready, note: e.ready ? "" : e.reason,
      })));
      return renderList("Silnik TTS", items, s.engine, (id) => saveSettings({ engine: id, voice: "" }));
    }
    if (view.kind === "voice") {
      const e = engines.find((x) => x.id === s.engine) || engines.find((x) => x.ready && x.id !== "test_tone");
      const items = [{ id: "", name: "Domyślny silnika" }].concat((e?.voices || []).map((v) => ({ id: v.id, name: v.name })));
      return renderList(`Głos (${e ? e.id : "?"})`, items, s.voice, (id) => saveSettings({ voice: id }));
    }
    if (view.kind === "translator") {
      const items = [{ id: "youtube", name: "YouTube (automatyczne tłumaczenie)" }].concat(translators.filter((t) => t.id !== "youtube").map((t) => ({
        id: t.id, name: t.name, disabled: !t.ready, note: t.ready ? (t.restores_punctuation ? "odtwarza interpunkcję" : "") : t.reason,
      })));
      return renderList("Tłumacz napisów", items, s.translator, (id) => saveSettings({ translator: id }));
    }
    if (view.kind === "lagMode") {
      return renderList("Gdy lektor nie nadąża", [
        { id: "speed", name: "Przyspiesz lektora (do maks. przyspieszenia)" },
        { id: "video", name: "Zwolnij film, aż lektor dogoni" },
      ], s.lagMode, (id) => saveSettings({ lagMode: id }));
    }
  }

  async function refreshLists() {
    try {
      const [e, t] = await Promise.all([client().engines(), client().translators()]);
      engines = e; translators = t.items; serverUp = true;
    } catch { engines = []; translators = []; serverUp = false; }
  }

  async function startServer() {
    serverMsg = "uruchamiam serwer…";
    render();
    const resp = await chrome.runtime.sendMessage({ type: "server_start" });
    if (resp?.ok && resp.running) {
      serverMsg = "";
      await refreshLists();
      render();
      onServerStarted?.();
    } else {
      serverMsg = resp?.hostMissing
        ? "brak launchera – uruchom install_host.cmd"
        : `nie udało się: ${resp?.error || "?"}`;
      render();
      setTimeout(() => { serverMsg = ""; if (!root.hidden) render(); }, 6000);
    }
  }

  // ---- open / close -------------------------------------------------------------------
  function onDocClick(ev) {
    if (!root.contains(ev.target) && !ev.target.closest?.(".polarnik-btn")) close();
  }
  function onKey(ev) { if (ev.key === "Escape") close(); }

  async function open() {
    view = { kind: "main" };
    root.hidden = false;
    render();
    await refreshLists();
    if (!root.hidden) render();
    setTimeout(() => { document.addEventListener("click", onDocClick, true); document.addEventListener("keydown", onKey, true); }, 0);
  }
  function close() {
    if (root.hidden) return;
    root.hidden = true;
    document.removeEventListener("click", onDocClick, true);
    document.removeEventListener("keydown", onKey, true);
    onClose?.();
  }
  function toggle() { root.hidden ? open() : close(); }

  // re-render when settings change elsewhere (popup, options page)
  const rerender = () => { if (!root.hidden && view.kind === "main") render(); };

  return { open, close, toggle, rerender, get isOpen() { return !root.hidden; }, element: root };
}
