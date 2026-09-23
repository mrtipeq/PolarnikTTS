// "Engines and voices" section of the options page: install engines, download voices,
// enable/disable, API keys, default engine - through the server's management API.

// Engine / translator titles and descriptions live in the dictionaries as
// "engine.<id>.title", "engine.<id>.desc", "translator.<id>", "field.<key>".
import { TARGET_LANGS } from "../lib/i18n.js";

// Which items can list their provider's models (GET <base_url>/models via the server).
const MODEL_LISTING = {
  translators: (t) => ["openai", "gemini", "ollama"].includes(t.id),
  engines: (e) => ["openai_tts", "gemini_tts"].includes(e.id),
};

export function createManager({ root, getClient, onChanged, t, targetLang }) {
  // t: translator from lib/i18n.js; targetLang(): voice-over language (filters voices)
  let catalog = null;
  let live = {};           // engine id -> live info from /engines (voices, ready, default_voice)
  let testText = t("opt.testSentence");
  let testAudio = null;
  let activeJob = null;
  let jobTimer = null;

  const h = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function badge(text, cls) { return `<span class="badge ${cls}">${esc(text)}</span>`; }

  function statusBadges(e) {
    const out = [];
    if (!e.installed) out.push(badge(t("mg.toInstall"), "warn"));
    else if (e.models_ok === false) out.push(badge(t("mg.noModel"), "warn"));
    else out.push(badge(t("mg.installed"), "ok"));
    if (e.installed) out.push(e.enabled ? badge(t("mg.enabled"), "ok") : badge(t("mg.disabled"), ""));
    if (e.enabled) out.push(e.ready ? badge(t("mg.ready"), "ok") : badge(`${t("mg.notReady")}: ${e.reason}`, "err"));
    if (e.gpu) out.push(badge(catalog.cuda_driver ? t("mg.gpuDetected") : t("mg.gpuRequired"), catalog.cuda_driver ? "" : "warn"));
    if (catalog.default_engine === e.id) out.push(badge(t("mg.default"), "accent"));
    if (e.key_inherited) out.push(badge(t("mg.keyShared"), "ok"));
    const lang = targetLang();
    if (e.langs?.length && !e.langs.includes(lang)) out.push(badge(t("panel.engineNoLang", { name: TARGET_LANGS[lang] || lang }), "warn"));
    return out.join(" ");
  }

  function fieldsForm(section, item) {
    if (!item.fields.length) return null;
    const form = h("div", "fields");
    for (const f of item.fields) {
      const row = h("label", "field");
      const label = t.has(`field.${f.key}`) ? t(`field.${f.key}`) : f.key;
      let input;
      if (f.type === "choice") {
        input = h("select");
        for (const c of f.choices) { const o = h("option"); o.value = c; o.textContent = c; input.appendChild(o); }
        input.value = item.values[f.key] || f.choices[0];
      } else {
        input = h("input");
        input.type = f.type === "secret" ? "password" : "text";
        input.value = item.values[f.key] || "";
        input.placeholder = f.type === "secret" ? t("mg.pasteKey") : "";
        input.spellcheck = false;
        if (f.key === "api_key" && item.key_source) {
          const src = { openai: "OpenAI", gemini: "Gemini" }[item.key_source] || item.key_source;
          if (item.key_inherited && !item.values.api_key) {
            input.type = "text";
            input.placeholder = t("mg.keyInheritedPh", { src });
            input.classList.add("inherited");
          } else if (!item.values.api_key) {
            input.placeholder = t("mg.keyOrTranslatorPh", { src });
          }
        }
      }
      input.dataset.key = f.key;
      row.append(h("span", "", esc(label)), input);
      if (f.type === "secret") {
        // reveal / copy the stored key (served only to the local machine by the management API)
        const tools = h("span", "secret-tools");
        const eye = h("button", "icon", "👁"); eye.type = "button"; eye.title = t("mg.showHideKey");
        const copy = h("button", "icon", "⧉"); copy.type = "button"; copy.title = t("mg.copyKey");
        let revealed = false;
        const fetchValue = async () => {
          if (input.value && input.value !== "•••") return input.value;   // freshly typed, not saved yet
          const r = await getClient().manageSecret(section, item.id, f.key);
          return r.value || "";
        };
        eye.addEventListener("click", async (ev) => {
          ev.preventDefault();
          try {
            if (!revealed) {
              const v = await fetchValue();
              if (!v) { note(t("mg.noStoredKey"), true); return; }
              input.value = v; input.type = "text"; revealed = true; eye.textContent = "🙈";
            } else {
              input.type = "password"; revealed = false; eye.textContent = "👁";
              if (!input.dataset.dirty) input.value = item.values[f.key] || "";
            }
          } catch (e) { note(t("mg.keyReadFailed", { error: e.message }), true); }
        });
        copy.addEventListener("click", async (ev) => {
          ev.preventDefault();
          try {
            const v = await fetchValue();
            if (!v) { note(t("mg.noStoredKey"), true); return; }
            await navigator.clipboard.writeText(v);
            note(t("mg.keyCopied"));
          } catch (e) { note(t("mg.copyFailed", { error: e.message }), true); }
        });
        input.addEventListener("input", () => { input.dataset.dirty = "1"; });
        tools.append(eye, copy);
        row.appendChild(tools);
      }
      if ((f.key === "model" || f.key === "model_id") && MODEL_LISTING[section]?.(item)) {
        // Ask the provider which model ids this key can use (providers retire models).
        const tools = h("span", "secret-tools");
        const btn = h("button", "icon", "☰"); btn.type = "button"; btn.title = t("mg.listModels");
        btn.addEventListener("click", async (ev) => {
          ev.preventDefault();
          btn.disabled = true;
          try {
            const r = await getClient().manageModels(section, item.id);
            if (!r.models.length) { note(t("mg.noModels"), true); return; }
            const pick = h("select");
            pick.appendChild(new Option(t("mg.pickModel"), ""));
            for (const m of r.models) pick.appendChild(new Option(m, m));
            pick.addEventListener("change", () => {
              if (!pick.value) return;
              if (input.tagName === "SELECT" && ![...input.options].some((o) => o.value === pick.value)) input.appendChild(new Option(pick.value, pick.value));
              input.value = pick.value;
              input.dataset.dirty = "1";
              note(t("mg.modelPicked", { model: pick.value }));
            });
            tools.replaceChildren(btn, pick);
          } catch (e) { note(t("mg.modelsFailed", { error: e.message }), true); }
          finally { btn.disabled = false; }
        });
        tools.appendChild(btn);
        row.appendChild(tools);
      }
      form.appendChild(row);
    }
    const save = h("button", "", t("common.save"));
    save.type = "button";
    save.addEventListener("click", async () => {
      const values = {};
      form.querySelectorAll("[data-key]").forEach((i) => { values[i.dataset.key] = i.value; });
      await run(() => getClient().manageConfig(section, item.id, values), t("common.saved"));
    });
    form.appendChild(save);
    return form;
  }

  function engineCard(e) {
    const lang = targetLang();
    const title = t.has(`engine.${e.id}.title`) ? t(`engine.${e.id}.title`) : e.name;
    const desc = t.has(`engine.${e.id}.desc`) ? t(`engine.${e.id}.desc`) : "";
    const card = h("div", "card");
    card.innerHTML = `<div class="card-head"><b>${esc(title)}</b> ${statusBadges(e)}</div><p class="muted">${esc(desc)}</p>`;
    const actions = h("div", "actions");

    if (!e.installed || (e.installed && e.models_ok === false && e.models !== "piper" && e.id !== "piper")) {
      const b = h("button", "primary", e.installed ? t("mg.downloadModel") : `${t("mg.install")}${e.download_mb ? ` (~${e.download_mb >= 1000 ? (e.download_mb / 1000).toFixed(1) + " GB" : e.download_mb + " MB"})` : ""}`);
      b.type = "button";
      b.addEventListener("click", () => startJob(e.id));
      actions.appendChild(b);
    }
    if (e.installed && e.isolated && e.enabled && !e.ready && /reinstall/i.test(e.reason || "")) {
      // e.g. torch build without kernels for this GPU (RTX 50xx) - the installer picks a matching build
      const b = h("button", "primary", t("mg.reinstall"));
      b.type = "button";
      b.title = e.reason;
      b.addEventListener("click", () => startJob(e.id));
      actions.appendChild(b);
    }
    if (e.installed) {
      const b = h("button", "", e.enabled ? t("mg.disable") : t("mg.enable"));
      b.type = "button";
      b.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { enabled: !e.enabled }), e.enabled ? t("mg.disabledDone") : t("mg.enabledDone")));
      actions.appendChild(b);
      if (catalog.default_engine !== e.id && e.enabled) {
        const d = h("button", "", t("mg.setDefault"));
        d.type = "button";
        d.addEventListener("click", () => run(() => getClient().manageConfig("server", null, { default_engine: e.id }), t("mg.defaultSet")));
        actions.appendChild(d);
      }
    }
    card.appendChild(actions);

    // downloadable voices: only those of the voice-over language (plus already downloaded ones)
    const dl = (e.voices || []).filter((v) => v.installed || !v.lang || v.lang === lang);
    if (dl.length) {
      const list = h("div", "voices");
      for (const v of dl) {
        const row = h("div", "voice");
        row.innerHTML = `<span>${esc(v.label)} <span class="muted">(${esc(v.id)}, ${v.size_mb} MB)</span></span>`;
        if (v.installed) {
          row.insertAdjacentHTML("beforeend", badge(t("mg.downloaded"), "ok"));
          if (e.default_voice !== v.id) {
            const d = h("button", "", t("mg.defaultVoice")); d.type = "button";
            d.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { default_voice: v.id }), t("mg.voiceSet")));
            row.appendChild(d);
          } else row.insertAdjacentHTML("beforeend", badge(t("mg.defaultVoiceBadge"), "accent"));
        } else {
          const b = h("button", "", t("mg.download")); b.type = "button";
          b.addEventListener("click", () => startJob(e.id, [v.id]));
          row.appendChild(b);
        }
        list.appendChild(row);
      }
      card.appendChild(list);
    }
    if (e.samples) card.appendChild(samplesSection(e));
    if (e.enabled && e.ready && live[e.id]?.voices?.length) card.appendChild(voiceTester(e, live[e.id]));
    const form = fieldsForm("engines", e);
    if (form) card.appendChild(form);
    return card;
  }

  // Try any voice of a ready engine with your own text; make it the engine's default.
  function voiceTester(e, info) {
    const box = h("div", "tester");
    box.appendChild(h("div", "muted", t("mg.testerHelp")));
    const row = h("div", "tester-row");
    const sel = h("select");
    const lang = targetLang();
    for (const v of info.voices.filter((v) => !v.lang || v.lang === lang)) {
      const o = h("option"); o.value = v.id; o.textContent = v.name === v.id ? v.id : `${v.name} (${v.id})`;
      sel.appendChild(o);
    }
    const currentDefault = e.default_voice || info.default_voice || "";
    if (info.voices.some((v) => v.id === currentDefault)) sel.value = currentDefault;
    const ta = h("textarea"); ta.rows = 2; ta.value = testText;
    ta.addEventListener("input", () => { testText = ta.value; });
    const speedWrap = h("label", "tester-speed");
    speedWrap.innerHTML = `${esc(t("mg.tempo"))} <output>1.00</output>× <input type="range" min="0.7" max="1.6" step="0.05" value="1">`;
    const speedIn = speedWrap.querySelector("input"), speedOut = speedWrap.querySelector("output");
    speedIn.addEventListener("input", () => { speedOut.textContent = Number(speedIn.value).toFixed(2); });
    const play = h("button", "primary", t("common.listen")); play.type = "button";
    const setDef = h("button", "", t("mg.setDefaultVoice")); setDef.type = "button";
    const status = h("span", "status");
    play.addEventListener("click", async () => {
      play.disabled = true; status.textContent = t("common.synthesizing"); status.className = "status";
      try {
        const t0 = performance.now();
        const speed = parseFloat(speedIn.value);
        const res = await getClient().tts({ text: ta.value.trim(), engine: e.id, voice: sel.value, speed, lang });
        if (testAudio) { testAudio.pause(); URL.revokeObjectURL(testAudio.src); }
        testAudio = new Audio(URL.createObjectURL(res.blob));
        testAudio.preservesPitch = true;
        if (info.native_speed === false) testAudio.playbackRate = speed;   // engine ignores speed -> stretch here
        await testAudio.play();
        status.textContent = `${Math.round(performance.now() - t0)} ms${res.cache === "hit" ? ` (${t("common.fromCache")})` : ""}, audio ${res.duration ? res.duration.toFixed(1) + " s" : "?"}`;
        status.className = "status ok";
      } catch (err) {
        status.textContent = t("common.error", { error: err.message }); status.className = "status err";
      } finally { play.disabled = false; }
    });
    setDef.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { default_voice: sel.value }), `${t("mg.defaultVoiceBadge")}: ${sel.value}`));
    row.append(sel, play, setDef, status);
    box.append(row, ta, speedWrap);
    return box;
  }

  // Voice samples (server/voices/*.wav) for cloning engines: upload from disk, preview, set default, delete.
  let previewAudio = null;
  function samplesSection(e) {
    const box = h("div", "samples");
    box.appendChild(h("div", "muted", t("mg.samplesHelp")));
    const list = h("div", "voices");
    for (const smp of catalog.samples || []) {
      const row = h("div", "voice");
      row.innerHTML = `<span>${esc(smp.name.replace(/\.wav$/, ""))} <span class="muted">(${smp.seconds ?? "?"} s)</span></span>`;
      const play = h("button", "", t("common.listen")); play.type = "button";
      play.addEventListener("click", () => {
        if (previewAudio) { previewAudio.pause(); previewAudio = null; }
        previewAudio = new Audio(getClient().sampleAudioUrl(smp.name));
        previewAudio.play().catch((err) => note(t("mg.cannotPlay", { error: err.message }), true));
      });
      row.appendChild(play);
      if (e.default_voice === smp.voice_id) row.insertAdjacentHTML("beforeend", badge(t("mg.defaultVoiceBadge"), "accent"));
      else {
        const d = h("button", "", t("mg.defaultVoice")); d.type = "button";
        d.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { default_voice: smp.voice_id }), t("mg.voiceSet")));
        row.appendChild(d);
      }
      const del = h("button", "", t("mg.delete")); del.type = "button";
      del.addEventListener("click", () => run(() => getClient().manageDeleteSample(smp.name), t("mg.sampleDeleted")));
      row.appendChild(del);
      list.appendChild(row);
    }
    if (e.installed && e.default_voice && !e.default_voice.startsWith("sample:")) {
      // nothing – built-in voice is the default
    }
    box.appendChild(list);
    const actions = h("div", "actions");
    const file = h("input"); file.type = "file"; file.accept = "audio/*,.wav,.mp3,.flac,.ogg,.m4a"; file.hidden = true;
    const up = h("button", "primary", t("mg.uploadSample")); up.type = "button";
    up.addEventListener("click", () => file.click());
    file.addEventListener("change", async () => {
      const f = file.files?.[0];
      if (!f) return;
      note(t("mg.uploading", { name: f.name }));
      await run(() => getClient().manageUploadSample(f), t("mg.sampleAdded", { name: f.name }));
      file.value = "";
    });
    actions.append(up, file);
    if (e.default_voice && e.default_voice.startsWith("sample:")) {
      const b = h("button", "", t("mg.backToBuiltin")); b.type = "button";
      b.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { default_voice: "" }), t("mg.builtinSet")));
      actions.appendChild(b);
    }
    box.appendChild(actions);
    return box;
  }

  function translatorCard(tr) {
    const card = h("div", "card");
    const badges = [tr.enabled ? badge(t("mg.enabled"), "ok") : badge(t("mg.disabled"), ""), tr.enabled ? (tr.ready ? badge(t("mg.ready"), "ok") : badge(`${t("mg.notReady")}: ${tr.reason}`, "err")) : ""].join(" ");
    const title = t.has(`translator.${tr.id}`) ? t(`translator.${tr.id}`) : tr.name;
    card.innerHTML = `<div class="card-head"><b>${esc(title)}</b> ${badges}</div>`;
    const actions = h("div", "actions");
    const b = h("button", "", tr.enabled ? t("mg.disable") : t("mg.enable")); b.type = "button";
    b.addEventListener("click", () => run(() => getClient().manageConfig("translators", tr.id, { enabled: !tr.enabled }), tr.enabled ? t("mg.disabledDone") : t("mg.enabledDone")));
    actions.appendChild(b);
    card.appendChild(actions);
    const form = fieldsForm("translators", tr);
    if (form) card.appendChild(form);
    if (tr.id === "ollama") card.appendChild(ollamaBlock(tr));
    return card;
  }

  // Suggested Ollama models: Bielik (Polish LLM) only makes sense for Polish; Gemma covers the rest.
  const OLLAMA_SUGGESTIONS = () => (targetLang() === "pl" ? [
    ["SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M", t("mg.ollamaBielik11")],
    ["SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0", t("mg.ollamaBielik45")],
    ["SpeakLeash/bielik-1.5b-v3.0-instruct", t("mg.ollamaBielik15")],
  ] : []).concat([
    ["gemma3:12b", t("mg.ollamaGemma12")],
    ["gemma3:4b", t("mg.ollamaGemma4")],
  ]);

  // Ollama: is it running, is the configured model pulled, one-click pull.
  function ollamaBlock(_tr) {
    const box = h("div", "ollama");
    box.innerHTML = `<p class="muted">${esc(t("mg.ollamaChecking"))}</p>`;
    getClient().manageOllama().then((st) => {
      box.innerHTML = "";
      if (!st.running) {
        box.innerHTML = `<p class="muted">${badge(t("mg.ollamaDown"), "err")} ${esc(t("mg.ollamaDownHelp", { host: st.host }))} <a href="https://ollama.com/download" target="_blank" rel="noopener">ollama.com/download</a> ${esc(st.error || "")}</p>`;
        return;
      }
      const head = h("p", "muted");
      head.innerHTML = `${badge(t("mg.ollamaUp"), "ok")} ${esc(t("mg.ollamaPulled"))}: ${st.models.length ? st.models.map((m) => `<code>${esc(m)}</code>`).join(", ") : `<i>${esc(t("mg.none"))}</i>`}`;
      box.appendChild(head);
      const line = h("div", "actions");
      if (st.pulled) {
        line.innerHTML = badge(t("mg.ollamaModelPulled", { model: st.model }), "ok");
      } else {
        line.innerHTML = badge(t("mg.ollamaModelMissing", { model: st.model }), "warn") + " ";
        const b = h("button", "primary", t("mg.ollamaPull")); b.type = "button";
        b.addEventListener("click", () => startJobWith(() => getClient().manageOllamaPull(st.model)));
        line.appendChild(b);
      }
      box.appendChild(line);
      const sug = h("p", "muted");
      sug.innerHTML = esc(t("mg.ollamaSuggested")) + " "
        + OLLAMA_SUGGESTIONS().map(([m, d]) => `<code>${esc(m)}</code> – ${esc(d)}`).join("; ") + ".";
      box.appendChild(sug);
    }).catch((e) => { box.innerHTML = `<p class="muted">${esc(t("mg.ollamaCheckFailed", { error: e.message }))}</p>`; });
    return box;
  }

  // ---- jobs -------------------------------------------------------------------------
  async function startJob(engine, voices) {
    return startJobWith(() => getClient().manageInstall(engine, voices));
  }

  async function startJobWith(begin) {
    try {
      const { job } = await begin();
      activeJob = job;
      render();
      pollJob();
    } catch (e) {
      note(t("mg.installStartFailed", { error: e.message }), true);
    }
  }

  function pollJob() {
    clearTimeout(jobTimer);
    if (!activeJob) return;
    jobTimer = setTimeout(async () => {
      try {
        activeJob = await getClient().manageJob(activeJob.id, 30);
      } catch (e) {
        activeJob.log.push(`(${t("mg.connectionLost", { error: e.message })})`);
      }
      renderJob();
      if (activeJob.status === "running") pollJob();
      else if (activeJob.restart_required) { await waitForRestart(); await refresh(); onChanged?.(); }
      else { await refresh(); onChanged?.(); }
    }, 1000);
  }

  // The server restarts itself after installing packages into its own environment.
  async function waitForRestart() {
    note(t("mg.serverRestarting"));
    await new Promise((r) => setTimeout(r, 2500));
    for (let i = 0; i < 40; i++) {
      try { await getClient().health(); return; } catch { await new Promise((r) => setTimeout(r, 1000)); }
    }
    note(t("mg.serverNotBack"), true);
  }

  function renderJob() {
    const box = root.querySelector(".job");
    if (!box) return;
    const j = activeJob;
    const st = { running: t("mg.jobRunning"), done: t("mg.jobDone"), failed: t("mg.jobFailed") }[j.status] || j.status;
    box.innerHTML = `<div class="job-head"><b>${j.kind === "ollama-pull" ? t("mg.jobPull") : t("mg.jobInstall")}: ${esc(j.target)}</b> ${badge(st, j.status === "done" ? "ok" : j.status === "failed" ? "err" : "")}${j.error ? ` <span class="err">${esc(j.error)}</span>` : ""}</div><pre>${esc(j.log.join("\n"))}</pre>`;
    box.querySelector("pre").scrollTop = 1e9;
  }

  // ---- helpers --------------------------------------------------------------------
  let noteTimer = null;
  function note(text, isErr = false) {
    const n = root.querySelector(".manage-note");
    if (!n) return;
    n.textContent = text; n.className = `manage-note status ${isErr ? "err" : "ok"}`;
    clearTimeout(noteTimer);
    noteTimer = setTimeout(() => { n.textContent = ""; }, 4000);
  }

  async function run(fn, okText) {
    try { await fn(); note(okText); await refresh(); onChanged?.(); }
    catch (e) { note(t("common.error", { error: e.message }), true); }
  }

  async function refresh() {
    try {
      const [cat, engines] = await Promise.all([getClient().manageCatalog(), getClient().engines()]);
      catalog = cat;
      live = Object.fromEntries(engines.map((x) => [x.id, x]));
      if (catalog.jobs?.length && !activeJob) { activeJob = await getClient().manageJob(catalog.jobs[0].id, 30); pollJob(); }
    } catch (e) {
      catalog = null;
      root.innerHTML = `<p class="muted">${esc(t("mg.needsLocalServer", { error: e.message }))}</p>`;
      return;
    }
    render();
  }

  function render() {
    if (!catalog) return;
    root.replaceChildren();
    root.appendChild(h("p", "muted", t("mg.intro")));
    root.appendChild(h("div", "manage-note status"));
    root.appendChild(h("div", "job" + (activeJob ? "" : " hidden")));
    if (activeJob) renderJob();
    root.appendChild(h("h3", "", esc(t("mg.enginesHeading"))));
    for (const e of catalog.engines) root.appendChild(engineCard(e));
    root.appendChild(h("h3", "", esc(t("mg.translatorsHeading"))));
    root.appendChild(h("p", "muted", esc(t("mg.translatorsHelp"))));
    for (const tr of catalog.translators) root.appendChild(translatorCard(tr));
  }

  return { refresh };
}
