import { ServerClient, isLocalUrl, originPattern } from "../lib/api.js";
import { loadSettings, saveSettings } from "../lib/settings.js";
import { createManager } from "./manage.js";
import { initI18n, localizeDom, resolveTargetLang, systemLang, UI_LANGS, TARGET_LANGS } from "../lib/i18n.js";

const $ = (id) => document.getElementById(id);
let settings;
let t = (k) => k;
const targetLang = () => resolveTargetLang(settings);
let enginesCache = [];
let manager = null;
let lastClient = null;

function setStatus(el, text, cls = "") {
  el.textContent = text;
  el.className = `status ${cls}`;
}

function bindRange(inputId, outputId, format = (v) => v) {
  const input = $(inputId), out = $(outputId);
  const update = () => (out.textContent = format(input.value));
  input.addEventListener("input", update);
  update();
}

// chrome.permissions.request() needs a user gesture, so the automatic connect on page
// load only checks; the "Connect" button (interactive) can actually ask.
async function ensureHostPermission(url, interactive) {
  if (isLocalUrl(url)) return true;
  const pattern = originPattern(url);
  if (!pattern) return false;
  if (await chrome.permissions.contains({ origins: [pattern] })) return true;
  if (!interactive) throw new Error(t("opt.errClickConnect"));
  return chrome.permissions.request({ origins: [pattern] });
}

function fillEngines(engines) {
  enginesCache = engines;
  const sel = $("engine");
  sel.innerHTML = `<option value="">${t("opt.engineServerDefault")}</option>`;
  const lang = targetLang();
  for (const e of engines) {
    const opt = document.createElement("option");
    opt.value = e.id;
    const cannot = e.langs?.length && !e.langs.includes(lang);
    opt.textContent = !e.ready ? `${e.name} [${e.id}] – ${t("opt.unavailable")}: ${e.reason}`
      : cannot ? `${e.name} [${e.id}] – ${t("panel.engineNoLang", { name: TARGET_LANGS[lang] || lang })}` : `${e.name} [${e.id}]`;
    opt.disabled = !e.ready || cannot;
    sel.appendChild(opt);
  }
  sel.value = engines.some((e) => e.id === settings.engine && e.ready) ? settings.engine : "";
  fillVoices();
}

function fillVoices() {
  const engine = enginesCache.find((e) => e.id === $("engine").value);
  const sel = $("voice");
  sel.innerHTML = `<option value="">${t("opt.voiceEngineDefault")}</option>`;
  const lang = targetLang();
  for (const v of (engine?.voices || []).filter((v) => !v.lang || v.lang === lang)) {
    const opt = document.createElement("option");
    opt.value = v.id;
    opt.textContent = v.name === v.id ? v.id : `${v.name} (${v.id})`;
    sel.appendChild(opt);
  }
  sel.value = (engine?.voices || []).some((v) => v.id === settings.voice) ? settings.voice : "";
}

function fillTranslators(data) {
  const sel = $("translator");
  sel.innerHTML = "";
  for (const tr of data.items) {
    const opt = document.createElement("option");
    opt.value = tr.id;
    opt.textContent = tr.id === "youtube"
      ? t("opt.youtubeAuto")
      : `${tr.name} [${tr.id}]${tr.ready ? "" : ` – ${t("opt.unavailable")}: ${tr.reason}`}${tr.restores_punctuation ? ` – ${t("panel.restoresPunctuation")}` : ""}`;
    opt.disabled = !tr.ready;
    sel.appendChild(opt);
  }
  sel.value = data.items.some((x) => x.id === settings.translator && x.ready) ? settings.translator : "youtube";
}

async function connect(interactive = false) {
  const url = $("serverUrl").value.trim() || "http://127.0.0.1:8765";
  const token = $("serverToken").value;
  setStatus($("serverStatus"), t("opt.connecting"));
  $("btnConnect").disabled = true;
  try {
    if (!(await ensureHostPermission(url, interactive))) throw new Error(t("opt.errNoPermission"));
    const client = new ServerClient(url, token);
    const health = await client.health();
    const [engines, translators] = await Promise.all([client.engines(), client.translators()]);
    fillEngines(engines);
    fillTranslators(translators);
    const cuda = health.cuda?.available ? `CUDA: ${health.cuda.device} (${health.cuda.vram_gb} GB)` : `CUDA: ${t("opt.noCuda")}`;
    const info = $("serverInfo");
    info.classList.remove("hidden");
    info.innerHTML = `PolarnikTTS ${health.version}, ${cuda}<br>` +
      engines.map((e) => e.ready ? `✔ ${e.id}` : `<span class="bad">✘ ${e.id}: ${e.reason}</span>`).join("<br>");
    setStatus($("serverStatus"), t("opt.connected"), "ok");
    $("btnStart").classList.add("hidden");
    $("btnStop").classList.toggle("hidden", !isLocalUrl(url));
    lastClient = client;
    if (!manager) manager = createManager({ root: $("manageRoot"), getClient: () => lastClient, onChanged: () => reloadLists(), t, targetLang });
    manager.refresh();
    $("aboutStats").textContent = `${t("about.server")} ${health.version} · ${t("about.enginesReady")}: ${health.engines_ready.join(", ") || "–"} · ${cuda}`;
  } catch (e) {
    const down = /Failed to fetch/i.test(e.message);
    setStatus($("serverStatus"), down ? t("opt.errServerDown") : t("common.error", { error: e.message }), "err");
    $("btnStop").classList.add("hidden");
    if (down && isLocalUrl(url)) $("btnStart").classList.remove("hidden");
    $("manageRoot").innerHTML = `<p class="muted">${t("opt.startToManage")}</p>`;
  } finally {
    $("btnConnect").disabled = false;
  }
}

// Re-read engines/translators after a management change (keeps the selects in sync).
async function reloadLists() {
  if (!lastClient) return;
  try {
    const [engines, translators] = await Promise.all([lastClient.engines(), lastClient.translators()]);
    fillEngines(engines);
    fillTranslators(translators);
  } catch { /* server restarting */ }
}

// ---- settings transfer (extension settings + server config + voice samples) ----
async function exportSettings() {
  setStatus($("transferStatus"), t("opt.preparing"));
  try {
    const bundle = { format: "polarnik-settings", version: 1, exported_at: new Date().toISOString(),
                     extension: await loadSettings(), server: null };
    if (lastClient) {
      try { bundle.server = await lastClient.manageExport(); }
      catch (e) { setStatus($("transferStatus"), t("opt.serverSkipped", { error: e.message }), "err"); }
    }
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `PolarnikTTS-settings-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    setStatus($("transferStatus"), bundle.server ? t("opt.exportedFull") : t("opt.exportedExtOnly"), "ok");
  } catch (e) {
    setStatus($("transferStatus"), t("common.error", { error: e.message }), "err");
  }
}

async function importSettings(file) {
  setStatus($("transferStatus"), t("opt.importing"));
  try {
    const bundle = JSON.parse(await file.text());
    if (bundle.format !== "polarnik-settings") throw new Error(t("opt.errNotSettingsFile"));
    const ext = { ...bundle.extension };
    // keep this machine's server address unless the file points at a LAN server
    if (!ext.serverUrl || isLocalUrl(ext.serverUrl)) ext.serverUrl = settings.serverUrl;
    settings = await saveSettings(ext);
    let serverMsg = "";
    if (bundle.server && lastClient) {
      const r = await lastClient.manageImport(bundle.server);
      serverMsg = t("opt.importedServer", { n: r.samples_imported });
    } else if (bundle.server) {
      serverMsg = t("opt.importedServerSkipped");
    }
    setStatus($("transferStatus"), t("opt.importedExt") + serverMsg, "ok");
    setTimeout(() => location.reload(), 1200);
  } catch (e) {
    setStatus($("transferStatus"), t("common.error", { error: e.message }), "err");
  }
}

async function stopServer() {
  $("btnStop").disabled = true;
  setStatus($("serverStatus"), t("opt.stopping"));
  try {
    try { await lastClient.manageShutdown(); }
    catch { await chrome.runtime.sendMessage({ type: "server_stop" }); }
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 300));
      try { await lastClient.health(); } catch { break; }
    }
    setStatus($("serverStatus"), t("opt.stopped"), "");
    $("btnStop").classList.add("hidden");
    $("btnStart").classList.remove("hidden");
    $("serverInfo").classList.add("hidden");
    $("manageRoot").innerHTML = `<p class="muted">${t("opt.startToManage")}</p>`;
  } finally {
    $("btnStop").disabled = false;
  }
}

// Ask the native messaging host (install_host.cmd) to start the local server, then reconnect.
async function startServer() {
  $("btnStart").disabled = true;
  setStatus($("serverStatus"), t("common.startingServer"));
  try {
    const resp = await chrome.runtime.sendMessage({ type: "server_start" });
    if (resp?.ok && resp.running) {
      await connect(false);
    } else if (resp?.hostMissing) {
      setStatus($("serverStatus"), t("common.hostMissing"), "err");
    } else {
      setStatus($("serverStatus"), t("common.failed", { error: resp?.error || "?" }), "err");
    }
  } finally {
    $("btnStart").disabled = false;
  }
}

let currentAudio = null;
async function testVoice() {
  const url = $("serverUrl").value.trim() || "http://127.0.0.1:8765";
  const client = new ServerClient(url, $("serverToken").value);
  setStatus($("testStatus"), t("common.synthesizing"));
  $("btnTest").disabled = true;
  try {
    const t0 = performance.now();
    const res = await client.tts({
      text: $("testText").value.trim(),
      engine: $("engine").value,
      voice: $("voice").value,
      speed: parseFloat($("speed").value),
      lang: targetLang(),
    });
    const ms = Math.round(performance.now() - t0);
    if (currentAudio) { currentAudio.pause(); URL.revokeObjectURL(currentAudio.src); }
    currentAudio = new Audio(URL.createObjectURL(res.blob));
    await currentAudio.play();
    setStatus($("testStatus"), `${res.engine}/${res.voice}: ${ms} ms (${res.cache === "hit" ? t("common.fromCache") : t("common.synthesis")}), audio ${res.duration ? res.duration.toFixed(1) + " s" : "?"}`, "ok");
  } catch (e) {
    setStatus($("testStatus"), t("common.error", { error: e.message }), "err");
  } finally {
    $("btnTest").disabled = false;
  }
}

async function testTranslator() {
  const client = lastClient || new ServerClient($("serverUrl").value.trim() || "http://127.0.0.1:8765", $("serverToken").value);
  const translator = $("translator").value;
  const out = $("translateTestResult");
  out.classList.add("hidden");
  if (translator === "youtube") {
    setStatus($("translateTestStatus"), t("opt.youtubeNotTestable"), "");
    return;
  }
  const text = $("translateTestText").value.trim();
  if (!text) { setStatus($("translateTestStatus"), t("opt.enterSentence"), "err"); return; }
  setStatus($("translateTestStatus"), t("opt.translating"));
  $("btnTranslateTest").disabled = true;
  try {
    const t0 = performance.now();
    const res = await client.translate({ sentences: [text], sourceLang: "auto", translator, targetLang: targetLang() });
    const ms = Math.round(performance.now() - t0);
    out.textContent = res.translations[0] || t("opt.emptyReply");
    out.classList.remove("hidden");
    setStatus($("translateTestStatus"), `${res.translator}: ${ms} ms${ms > 8000 ? ` – ${t("opt.slowTranslator")}` : ""}`, ms > 8000 ? "" : "ok");
  } catch (e) {
    setStatus($("translateTestStatus"), t("common.error", { error: e.message }), "err");
  } finally {
    $("btnTranslateTest").disabled = false;
  }
}

async function save() {
  const uiChanged = $("uiLang").value !== settings.uiLang;
  settings = await saveSettings({
    uiLang: $("uiLang").value,
    targetLang: $("targetLang").value,
    serverUrl: $("serverUrl").value.trim() || "http://127.0.0.1:8765",
    serverToken: $("serverToken").value,
    engine: $("engine").value,
    voice: $("voice").value,
    speed: parseFloat($("speed").value),
    translator: $("translator").value,
    voiceVolume: parseFloat($("voiceVolume").value),
    duckingDb: parseInt($("duckingDb").value, 10),
    maxRate: parseFloat($("maxRate").value),
    lagMode: $("lagMode").value,
    offsetMs: parseInt($("offsetMs").value, 10),
    lookaheadS: parseInt($("lookaheadS").value, 10),
  });
  setStatus($("saveStatus"), t("common.saved"), "ok");
  setTimeout(() => setStatus($("saveStatus"), ""), 2000);
  if (uiChanged) setTimeout(() => location.reload(), 300);
}

function fillLanguagePickers() {
  const sys = systemLang();
  const ui = $("uiLang");
  ui.innerHTML = "";
  ui.appendChild(new Option(t("opt.langAuto", { name: UI_LANGS[sys] || "English" }), "auto"));
  for (const [code, name] of Object.entries(UI_LANGS)) ui.appendChild(new Option(name, code));
  ui.value = UI_LANGS[settings.uiLang] ? settings.uiLang : "auto";
  const tl = $("targetLang");
  tl.innerHTML = "";
  tl.appendChild(new Option(t("opt.langAuto", { name: TARGET_LANGS[sys] || "English" }), "auto"));
  for (const [code, name] of Object.entries(TARGET_LANGS)) tl.appendChild(new Option(name, code));
  tl.value = TARGET_LANGS[settings.targetLang] ? settings.targetLang : "auto";
  tl.addEventListener("change", () => {
    // voices and engines depend on the voice-over language: re-filter the pickers right away
    settings = { ...settings, targetLang: tl.value, voice: "" };
    if (enginesCache.length) fillEngines(enginesCache);
    manager?.refresh?.();
  });
}

async function init() {
  settings = await loadSettings();
  t = await initI18n(settings);
  localizeDom(t);
  document.title = `PolarnikTTS – ${t("opt.titleSuffix")}`;
  $("testText").value = t("opt.testSentence");
  fillLanguagePickers();
  $("serverUrl").value = settings.serverUrl;
  $("serverToken").value = settings.serverToken;
  $("speed").value = settings.speed;
  $("voiceVolume").value = settings.voiceVolume;
  $("duckingDb").value = settings.duckingDb;
  $("maxRate").value = settings.maxRate;
  $("lagMode").value = settings.lagMode;
  $("offsetMs").value = settings.offsetMs;
  $("lookaheadS").value = settings.lookaheadS;
  bindRange("speed", "speedOut", (v) => Number(v).toFixed(2));
  bindRange("voiceVolume", "voiceVolumeOut", (v) => Math.round(v * 100));
  bindRange("duckingDb", "duckingOut");
  bindRange("maxRate", "maxRateOut", (v) => Number(v).toFixed(2));
  bindRange("offsetMs", "offsetOut");
  bindRange("lookaheadS", "lookaheadOut");
  $("engine").addEventListener("change", fillVoices);
  $("btnConnect").addEventListener("click", () => connect(true));
  $("btnStart").addEventListener("click", startServer);
  $("btnStop").addEventListener("click", stopServer);
  $("btnExport").addEventListener("click", exportSettings);
  $("btnImport").addEventListener("click", () => $("importFile").click());
  $("importFile").addEventListener("change", () => { const f = $("importFile").files?.[0]; if (f) importSettings(f); $("importFile").value = ""; });
  $("aboutVersion").textContent = `${t("about.version")} ${chrome.runtime.getManifest().version}`;
  $("btnTest").addEventListener("click", testVoice);
  $("btnTranslateTest").addEventListener("click", testTranslator);
  $("btnSave").addEventListener("click", save);
  // Preselect stored values even before connecting.
  if (settings.engine) $("engine").insertAdjacentHTML("beforeend", `<option value="${settings.engine}" selected>${settings.engine}</option>`);
  if (settings.voice) $("voice").insertAdjacentHTML("beforeend", `<option value="${settings.voice}" selected>${settings.voice}</option>`);
  if (settings.translator !== "youtube") $("translator").insertAdjacentHTML("beforeend", `<option value="${settings.translator}" selected>${settings.translator}</option>`);
  connect(false);
}

init();
