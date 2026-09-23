// "Silniki i głosy" section of the options page: install engines, download voices,
// enable/disable, API keys, default engine - through the server's management API.

const ENGINE_TEXT = {
  edge_tts: {
    title: "Microsoft Edge – Zofia, Marek",
    desc: "Bardzo dobre polskie głosy neuronowe Microsoftu. Nie wymaga GPU, wymaga internetu. Nieoficjalne API – może kiedyś przestać działać, dlatego warto mieć też silnik lokalny. Domyślny wybór.",
  },
  piper: {
    title: "Piper – lokalny, CPU",
    desc: "Szybki i całkowicie offline, jakość podstawowa. Dobry jako silnik awaryjny.",
  },
  chatterbox: {
    title: "Chatterbox Multilingual – lokalny, GPU",
    desc: "Model open-source (MIT). Ma wbudowany głos domyślny, a z 5–15-sekundowej próbki potrafi sklonować dowolny głos (polska próbka poprawia też akcent). Wymaga karty NVIDIA. Instaluje się we własnym, odizolowanym środowisku (PyTorch 2.6 z CUDA + model, ~4,5 GB).",
  },
  xtts: {
    title: "XTTS-v2 – lokalny, GPU",
    desc: "Sześć wbudowanych głosów studyjnych plus klonowanie z próbki. Licencja niekomercyjna (na własny użytek OK). Wymaga karty NVIDIA. Własne, odizolowane środowisko (~4,3 GB).",
  },
  openai_tts: {
    title: "OpenAI TTS – chmura, płatny",
    desc: "Głosy OpenAI (gpt-4o-mini-tts), wielojęzyczne, czytają polski tekst z instrukcją „jak polski lektor”. Używa klucza wpisanego przy tłumaczu OpenAI, chyba że podasz osobny.",
  },
  gemini_tts: {
    title: "Google Gemini TTS – chmura",
    desc: "30 głosów Gemini (m.in. Kore, Puck, Charon), obsługuje polski. Używa klucza wpisanego przy tłumaczu Gemini, chyba że podasz osobny. Darmowy limit w AI Studio, dalej płatne.",
  },
  elevenlabs: {
    title: "ElevenLabs – chmura, płatny",
    desc: "Najbardziej ekspresyjne głosy. Wymaga klucza API i konta ElevenLabs.",
  },
};

const FIELD_LABEL = {
  api_key: "Klucz API", model_id: "Model", model: "Model", base_url: "Adres API", device: "Urządzenie",
  instructions: "Instrukcja stylu (jak ma czytać)",
};

// Which items can list their provider's models (GET <base_url>/models via the server).
const MODEL_LISTING = {
  translators: (t) => ["openai", "gemini", "ollama"].includes(t.id),
  engines: (e) => ["openai_tts", "gemini_tts"].includes(e.id),
};

const TRANSLATOR_TEXT = {
  openai: "OpenAI (GPT) – chmura, klucz API",
  gemini: "Google Gemini – chmura, klucz API",
  ollama: "Ollama – lokalny LLM (np. Bielik), bez klucza",
  anthropic: "Anthropic Claude – chmura, klucz API",
  deepl: "DeepL – chmura, klucz API (darmowy limit 500 tys. znaków/mies.)",
};

export function createManager({ root, getClient, onChanged }) {
  let catalog = null;
  let live = {};           // engine id -> live info from /engines (voices, ready, default_voice)
  let testText = "Dzień dobry, to jest próba głosu w rozszerzeniu Polarnik Te Te eS. Czy brzmi naturalnie?";
  let testAudio = null;
  let activeJob = null;
  let jobTimer = null;

  const h = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function badge(text, cls) { return `<span class="badge ${cls}">${esc(text)}</span>`; }

  function statusBadges(e) {
    const out = [];
    if (!e.installed) out.push(badge("do instalacji", "warn"));
    else if (e.models_ok === false) out.push(badge("brak głosów/modelu", "warn"));
    else out.push(badge("zainstalowany", "ok"));
    if (e.installed) out.push(e.enabled ? badge("włączony", "ok") : badge("wyłączony", ""));
    if (e.enabled) out.push(e.ready ? badge("gotowy", "ok") : badge(`niegotowy: ${e.reason}`, "err"));
    if (e.gpu) out.push(badge(catalog.cuda_driver ? "GPU wykryte" : "wymaga GPU NVIDIA", catalog.cuda_driver ? "" : "warn"));
    if (catalog.default_engine === e.id) out.push(badge("domyślny", "accent"));
    if (e.key_inherited) out.push(badge("klucz wspólny z tłumaczem", "ok"));
    return out.join(" ");
  }

  function fieldsForm(section, item) {
    if (!item.fields.length) return null;
    const form = h("div", "fields");
    for (const f of item.fields) {
      const row = h("label", "field");
      const label = FIELD_LABEL[f.key] || f.key;
      let input;
      if (f.type === "choice") {
        input = h("select");
        for (const c of f.choices) { const o = h("option"); o.value = c; o.textContent = c; input.appendChild(o); }
        input.value = item.values[f.key] || f.choices[0];
      } else {
        input = h("input");
        input.type = f.type === "secret" ? "password" : "text";
        input.value = item.values[f.key] || "";
        input.placeholder = f.type === "secret" ? "wklej klucz" : "";
        input.spellcheck = false;
        if (f.key === "api_key" && item.key_source) {
          const src = { openai: "OpenAI", gemini: "Gemini" }[item.key_source] || item.key_source;
          if (item.key_inherited && !item.values.api_key) {
            input.type = "text";
            input.placeholder = `✔ wspólny z tłumaczem ${src} – zostaw puste, wpisz tylko, jeśli chcesz inny klucz`;
            input.classList.add("inherited");
          } else if (!item.values.api_key) {
            input.placeholder = `wklej klucz albo wpisz go przy tłumaczu ${src} (będzie wspólny)`;
          }
        }
      }
      input.dataset.key = f.key;
      row.append(h("span", "", esc(label)), input);
      if (f.type === "secret") {
        // reveal / copy the stored key (served only to the local machine by the management API)
        const tools = h("span", "secret-tools");
        const eye = h("button", "icon", "👁"); eye.type = "button"; eye.title = "Pokaż / ukryj klucz";
        const copy = h("button", "icon", "⧉"); copy.type = "button"; copy.title = "Kopiuj klucz do schowka";
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
              if (!v) { note("brak zapisanego klucza", true); return; }
              input.value = v; input.type = "text"; revealed = true; eye.textContent = "🙈";
            } else {
              input.type = "password"; revealed = false; eye.textContent = "👁";
              if (!input.dataset.dirty) input.value = item.values[f.key] || "";
            }
          } catch (e) { note(`nie udało się odczytać klucza: ${e.message}`, true); }
        });
        copy.addEventListener("click", async (ev) => {
          ev.preventDefault();
          try {
            const v = await fetchValue();
            if (!v) { note("brak zapisanego klucza", true); return; }
            await navigator.clipboard.writeText(v);
            note("klucz skopiowany do schowka");
          } catch (e) { note(`nie udało się skopiować: ${e.message}`, true); }
        });
        input.addEventListener("input", () => { input.dataset.dirty = "1"; });
        tools.append(eye, copy);
        row.appendChild(tools);
      }
      if ((f.key === "model" || f.key === "model_id") && MODEL_LISTING[section]?.(item)) {
        // Ask the provider which model ids this key can use (providers retire models).
        const tools = h("span", "secret-tools");
        const btn = h("button", "icon", "☰"); btn.type = "button"; btn.title = "Pobierz listę modeli od dostawcy";
        btn.addEventListener("click", async (ev) => {
          ev.preventDefault();
          btn.disabled = true;
          try {
            const r = await getClient().manageModels(section, item.id);
            if (!r.models.length) { note("dostawca nie zwrócił żadnych modeli", true); return; }
            const pick = h("select");
            pick.appendChild(new Option("– wybierz model z listy –", ""));
            for (const m of r.models) pick.appendChild(new Option(m, m));
            pick.addEventListener("change", () => {
              if (!pick.value) return;
              if (input.tagName === "SELECT" && ![...input.options].some((o) => o.value === pick.value)) input.appendChild(new Option(pick.value, pick.value));
              input.value = pick.value;
              input.dataset.dirty = "1";
              note(`wybrano ${pick.value} – kliknij „Zapisz”`);
            });
            tools.replaceChildren(btn, pick);
          } catch (e) { note(`lista modeli: ${e.message}`, true); }
          finally { btn.disabled = false; }
        });
        tools.appendChild(btn);
        row.appendChild(tools);
      }
      form.appendChild(row);
    }
    const save = h("button", "", "Zapisz");
    save.type = "button";
    save.addEventListener("click", async () => {
      const values = {};
      form.querySelectorAll("[data-key]").forEach((i) => { values[i.dataset.key] = i.value; });
      await run(() => getClient().manageConfig(section, item.id, values), "zapisano");
    });
    form.appendChild(save);
    return form;
  }

  function engineCard(e) {
    const t = ENGINE_TEXT[e.id] || { title: e.name, desc: "" };
    const card = h("div", "card");
    card.innerHTML = `<div class="card-head"><b>${esc(t.title)}</b> ${statusBadges(e)}</div><p class="muted">${esc(t.desc)}</p>`;
    const actions = h("div", "actions");

    if (!e.installed || (e.installed && e.models_ok === false && e.models !== "piper" && e.id !== "piper")) {
      const b = h("button", "primary", e.installed ? "Pobierz model" : `Zainstaluj${e.download_mb ? ` (~${e.download_mb >= 1000 ? (e.download_mb / 1000).toFixed(1) + " GB" : e.download_mb + " MB"})` : ""}`);
      b.type = "button";
      b.addEventListener("click", () => startJob(e.id));
      actions.appendChild(b);
    }
    if (e.installed && e.isolated && e.enabled && !e.ready && /reinstall/i.test(e.reason || "")) {
      // e.g. torch build without kernels for this GPU (RTX 50xx) - the installer picks a matching build
      const b = h("button", "primary", "Przeinstaluj (napraw PyTorch dla tej karty)");
      b.type = "button";
      b.title = e.reason;
      b.addEventListener("click", () => startJob(e.id));
      actions.appendChild(b);
    }
    if (e.installed) {
      const b = h("button", "", e.enabled ? "Wyłącz" : "Włącz");
      b.type = "button";
      b.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { enabled: !e.enabled }), e.enabled ? "wyłączono" : "włączono"));
      actions.appendChild(b);
      if (catalog.default_engine !== e.id && e.enabled) {
        const d = h("button", "", "Ustaw jako domyślny");
        d.type = "button";
        d.addEventListener("click", () => run(() => getClient().manageConfig("server", null, { default_engine: e.id }), "ustawiono domyślny"));
        actions.appendChild(d);
      }
    }
    card.appendChild(actions);

    if (e.voices?.length) {
      const list = h("div", "voices");
      for (const v of e.voices) {
        const row = h("div", "voice");
        row.innerHTML = `<span>${esc(v.label)} <span class="muted">(${esc(v.id)}, ${v.size_mb} MB)</span></span>`;
        if (v.installed) {
          row.insertAdjacentHTML("beforeend", badge("pobrany", "ok"));
          if (e.default_voice !== v.id) {
            const d = h("button", "", "Domyślny głos"); d.type = "button";
            d.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { default_voice: v.id }), "ustawiono głos"));
            row.appendChild(d);
          } else row.insertAdjacentHTML("beforeend", badge("domyślny głos", "accent"));
        } else {
          const b = h("button", "", "Pobierz"); b.type = "button";
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
    box.appendChild(h("div", "muted", "Wypróbuj głos: wybierz z listy, wpisz tekst i odsłuchaj. „Ustaw jako domyślny głos” zapisuje wybór dla tego silnika."));
    const row = h("div", "tester-row");
    const sel = h("select");
    for (const v of info.voices) {
      const o = h("option"); o.value = v.id; o.textContent = v.name === v.id ? v.id : `${v.name} (${v.id})`;
      sel.appendChild(o);
    }
    const currentDefault = e.default_voice || info.default_voice || "";
    if (info.voices.some((v) => v.id === currentDefault)) sel.value = currentDefault;
    const ta = h("textarea"); ta.rows = 2; ta.value = testText;
    ta.addEventListener("input", () => { testText = ta.value; });
    const speedWrap = h("label", "tester-speed");
    speedWrap.innerHTML = `tempo <output>1.00</output>× <input type="range" min="0.7" max="1.6" step="0.05" value="1">`;
    const speedIn = speedWrap.querySelector("input"), speedOut = speedWrap.querySelector("output");
    speedIn.addEventListener("input", () => { speedOut.textContent = Number(speedIn.value).toFixed(2); });
    const play = h("button", "primary", "Odsłuchaj"); play.type = "button";
    const setDef = h("button", "", "Ustaw jako domyślny głos"); setDef.type = "button";
    const status = h("span", "status");
    play.addEventListener("click", async () => {
      play.disabled = true; status.textContent = "synteza…"; status.className = "status";
      try {
        const t0 = performance.now();
        const speed = parseFloat(speedIn.value);
        const res = await getClient().tts({ text: ta.value.trim(), engine: e.id, voice: sel.value, speed });
        if (testAudio) { testAudio.pause(); URL.revokeObjectURL(testAudio.src); }
        testAudio = new Audio(URL.createObjectURL(res.blob));
        testAudio.preservesPitch = true;
        if (info.native_speed === false) testAudio.playbackRate = speed;   // engine ignores speed -> stretch here
        await testAudio.play();
        status.textContent = `${Math.round(performance.now() - t0)} ms${res.cache === "hit" ? " (z cache)" : ""}, audio ${res.duration ? res.duration.toFixed(1) + " s" : "?"}`;
        status.className = "status ok";
      } catch (err) {
        status.textContent = `błąd: ${err.message}`; status.className = "status err";
      } finally { play.disabled = false; }
    });
    setDef.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { default_voice: sel.value }), `domyślny głos: ${sel.value}`));
    row.append(sel, play, setDef, status);
    box.append(row, ta, speedWrap);
    return box;
  }

  // Voice samples (server/voices/*.wav) for cloning engines: upload from disk, preview, set default, delete.
  let previewAudio = null;
  function samplesSection(e) {
    const box = h("div", "samples");
    box.appendChild(h("div", "muted", "Próbki głosu do klonowania (opcjonalnie – bez próbki działa głos wbudowany). Najlepiej 5–15 s czystej mowy, WAV lub MP3."));
    const list = h("div", "voices");
    for (const smp of catalog.samples || []) {
      const row = h("div", "voice");
      row.innerHTML = `<span>${esc(smp.name.replace(/\.wav$/, ""))} <span class="muted">(${smp.seconds ?? "?"} s)</span></span>`;
      const play = h("button", "", "Odsłuchaj"); play.type = "button";
      play.addEventListener("click", () => {
        if (previewAudio) { previewAudio.pause(); previewAudio = null; }
        previewAudio = new Audio(getClient().sampleAudioUrl(smp.name));
        previewAudio.play().catch((err) => note(`nie można odtworzyć: ${err.message}`, true));
      });
      row.appendChild(play);
      if (e.default_voice === smp.voice_id) row.insertAdjacentHTML("beforeend", badge("domyślny głos", "accent"));
      else {
        const d = h("button", "", "Domyślny głos"); d.type = "button";
        d.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { default_voice: smp.voice_id }), "ustawiono głos"));
        row.appendChild(d);
      }
      const del = h("button", "", "Usuń"); del.type = "button";
      del.addEventListener("click", () => run(() => getClient().manageDeleteSample(smp.name), "usunięto próbkę"));
      row.appendChild(del);
      list.appendChild(row);
    }
    if (e.installed && e.default_voice && !e.default_voice.startsWith("sample:")) {
      // nothing – built-in voice is the default
    }
    box.appendChild(list);
    const actions = h("div", "actions");
    const file = h("input"); file.type = "file"; file.accept = "audio/*,.wav,.mp3,.flac,.ogg,.m4a"; file.hidden = true;
    const up = h("button", "primary", "Prześlij próbkę z dysku…"); up.type = "button";
    up.addEventListener("click", () => file.click());
    file.addEventListener("change", async () => {
      const f = file.files?.[0];
      if (!f) return;
      note(`przesyłam ${f.name}…`);
      await run(() => getClient().manageUploadSample(f), `dodano próbkę ${f.name}`);
      file.value = "";
    });
    actions.append(up, file);
    if (e.default_voice && e.default_voice.startsWith("sample:")) {
      const b = h("button", "", "Wróć do głosu wbudowanego"); b.type = "button";
      b.addEventListener("click", () => run(() => getClient().manageConfig("engines", e.id, { default_voice: "" }), "ustawiono głos wbudowany"));
      actions.appendChild(b);
    }
    box.appendChild(actions);
    return box;
  }

  function translatorCard(t) {
    const card = h("div", "card");
    const badges = [t.enabled ? badge("włączony", "ok") : badge("wyłączony", ""), t.enabled ? (t.ready ? badge("gotowy", "ok") : badge(`niegotowy: ${t.reason}`, "err")) : ""].join(" ");
    card.innerHTML = `<div class="card-head"><b>${esc(TRANSLATOR_TEXT[t.id] || t.name)}</b> ${badges}</div>`;
    const actions = h("div", "actions");
    const b = h("button", "", t.enabled ? "Wyłącz" : "Włącz"); b.type = "button";
    b.addEventListener("click", () => run(() => getClient().manageConfig("translators", t.id, { enabled: !t.enabled }), t.enabled ? "wyłączono" : "włączono"));
    actions.appendChild(b);
    card.appendChild(actions);
    const form = fieldsForm("translators", t);
    if (form) card.appendChild(form);
    if (t.id === "ollama") card.appendChild(ollamaBlock(t));
    return card;
  }

  const OLLAMA_SUGGESTIONS = [
    ["SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M", "6,7 GB – najlepsza jakość, karta ≥ 8 GB VRAM"],
    ["SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0", "5,1 GB – dobry kompromis, karta 6 GB"],
    ["SpeakLeash/bielik-1.5b-v3.0-instruct", "~1,7 GB – szybki, słabszy"],
    ["gemma3:4b", "3,3 GB – model Google, dobrze zna polski"],
  ];

  // Ollama: is it running, is the configured model pulled, one-click pull.
  function ollamaBlock(t) {
    const box = h("div", "ollama");
    box.innerHTML = `<p class="muted">sprawdzam Ollamę…</p>`;
    getClient().manageOllama().then((st) => {
      box.innerHTML = "";
      if (!st.running) {
        box.innerHTML = `<p class="muted">${badge("Ollama nie odpowiada", "err")} pod ${esc(st.host)} – zainstaluj z <a href="https://ollama.com/download" target="_blank" rel="noopener">ollama.com/download</a> i uruchom (ikona w zasobniku). ${esc(st.error || "")}</p>`;
        return;
      }
      const head = h("p", "muted");
      head.innerHTML = `${badge("Ollama działa", "ok")} pobrane modele: ${st.models.length ? st.models.map((m) => `<code>${esc(m)}</code>`).join(", ") : "<i>żaden</i>"}`;
      box.appendChild(head);
      const line = h("div", "actions");
      if (st.pulled) {
        line.innerHTML = badge(`model ${st.model} pobrany`, "ok");
      } else {
        line.innerHTML = badge(`model ${st.model} nie jest pobrany`, "warn") + " ";
        const b = h("button", "primary", "Pobierz model (ollama pull)"); b.type = "button";
        b.addEventListener("click", () => startJobWith(() => getClient().manageOllamaPull(st.model)));
        line.appendChild(b);
      }
      box.appendChild(line);
      const sug = h("p", "muted");
      sug.innerHTML = "Polecane modele (wpisz w polu „Model”, zapisz, potem „Pobierz model”): "
        + OLLAMA_SUGGESTIONS.map(([m, d]) => `<code>${esc(m)}</code> – ${esc(d)}`).join("; ") + ".";
      box.appendChild(sug);
    }).catch((e) => { box.innerHTML = `<p class="muted">nie udało się sprawdzić Ollamy: ${esc(e.message)}</p>`; });
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
      note(`nie udało się uruchomić instalacji: ${e.message}`, true);
    }
  }

  function pollJob() {
    clearTimeout(jobTimer);
    if (!activeJob) return;
    jobTimer = setTimeout(async () => {
      try {
        activeJob = await getClient().manageJob(activeJob.id, 30);
      } catch (e) {
        activeJob.log.push(`(utracono połączenie z serwerem: ${e.message})`);
      }
      renderJob();
      if (activeJob.status === "running") pollJob();
      else if (activeJob.restart_required) { await waitForRestart(); await refresh(); onChanged?.(); }
      else { await refresh(); onChanged?.(); }
    }, 1000);
  }

  // The server restarts itself after installing packages into its own environment.
  async function waitForRestart() {
    note("serwer restartuje się, aby załadować nowe pakiety…");
    await new Promise((r) => setTimeout(r, 2500));
    for (let i = 0; i < 40; i++) {
      try { await getClient().health(); return; } catch { await new Promise((r) => setTimeout(r, 1000)); }
    }
    note("serwer nie wrócił po restarcie – uruchom go ręcznie", true);
  }

  function renderJob() {
    const box = root.querySelector(".job");
    if (!box) return;
    const j = activeJob;
    const st = { running: "trwa…", done: "zakończono", failed: "błąd" }[j.status] || j.status;
    box.innerHTML = `<div class="job-head"><b>${j.kind === "ollama-pull" ? "Pobieranie modelu" : "Instalacja"}: ${esc(j.target)}</b> ${badge(st, j.status === "done" ? "ok" : j.status === "failed" ? "err" : "")}${j.error ? ` <span class="err">${esc(j.error)}</span>` : ""}</div><pre>${esc(j.log.join("\n"))}</pre>`;
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
    catch (e) { note(`błąd: ${e.message}`, true); }
  }

  async function refresh() {
    try {
      const [cat, engines] = await Promise.all([getClient().manageCatalog(), getClient().engines()]);
      catalog = cat;
      live = Object.fromEntries(engines.map((x) => [x.id, x]));
      if (catalog.jobs?.length && !activeJob) { activeJob = await getClient().manageJob(catalog.jobs[0].id, 30); pollJob(); }
    } catch (e) {
      catalog = null;
      root.innerHTML = `<p class="muted">Zarządzanie silnikami wymaga połączenia z serwerem uruchomionym na tym komputerze (${esc(e.message)}).</p>`;
      return;
    }
    render();
  }

  function render() {
    if (!catalog) return;
    root.replaceChildren();
    root.appendChild(h("p", "muted", "Tu instalujesz silniki i głosy, włączasz je oraz wpisujesz klucze API – bez wiersza poleceń. Zmiany zapisują się w <code>server/config.yaml</code> i działają od razu."));
    root.appendChild(h("div", "manage-note status"));
    root.appendChild(h("div", "job" + (activeJob ? "" : " hidden")));
    if (activeJob) renderJob();
    root.appendChild(h("h3", "", "Silniki TTS"));
    for (const e of catalog.engines) root.appendChild(engineCard(e));
    root.appendChild(h("h3", "", "Tłumacze napisów (opcjonalnie)"));
    root.appendChild(h("p", "muted", "Tłumacz LLM odtwarza interpunkcję i granice zdań, przez co lektor brzmi naturalniej niż z automatycznym tłumaczeniem YouTube. Po włączeniu wybierz go w sekcji „Tłumaczenie” powyżej."));
    for (const t of catalog.translators) root.appendChild(translatorCard(t));
  }

  return { refresh };
}
