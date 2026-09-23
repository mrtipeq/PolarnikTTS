import { ServerClient, isLocalUrl, originPattern } from "../lib/api.js";
import { loadSettings, saveSettings } from "../lib/settings.js";
import { createManager } from "./manage.js";

const $ = (id) => document.getElementById(id);
let settings;
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
// load only checks; the "Połącz" button (interactive) can actually ask.
async function ensureHostPermission(url, interactive) {
  if (isLocalUrl(url)) return true;
  const pattern = originPattern(url);
  if (!pattern) return false;
  if (await chrome.permissions.contains({ origins: [pattern] })) return true;
  if (!interactive) throw new Error("kliknij „Połącz”, aby przyznać dostęp do tego adresu");
  return chrome.permissions.request({ origins: [pattern] });
}

function fillEngines(engines) {
  enginesCache = engines;
  const sel = $("engine");
  sel.innerHTML = '<option value="">(domyślny serwera)</option>';
  for (const e of engines) {
    const opt = document.createElement("option");
    opt.value = e.id;
    opt.textContent = e.ready ? `${e.name} [${e.id}]` : `${e.name} [${e.id}] – niedostępny: ${e.reason}`;
    opt.disabled = !e.ready;
    sel.appendChild(opt);
  }
  sel.value = engines.some((e) => e.id === settings.engine && e.ready) ? settings.engine : "";
  fillVoices();
}

function fillVoices() {
  const engine = enginesCache.find((e) => e.id === $("engine").value);
  const sel = $("voice");
  sel.innerHTML = '<option value="">(domyślny silnika)</option>';
  for (const v of engine?.voices || []) {
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
  for (const t of data.items) {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = t.id === "youtube"
      ? "YouTube (automatyczne tłumaczenie)"
      : `${t.name} [${t.id}]${t.ready ? "" : ` – niedostępny: ${t.reason}`}${t.restores_punctuation ? " – odtwarza interpunkcję" : ""}`;
    opt.disabled = !t.ready;
    sel.appendChild(opt);
  }
  sel.value = data.items.some((t) => t.id === settings.translator && t.ready) ? settings.translator : "youtube";
}

async function connect(interactive = false) {
  const url = $("serverUrl").value.trim() || "http://127.0.0.1:8765";
  const token = $("serverToken").value;
  setStatus($("serverStatus"), "łączenie…");
  $("btnConnect").disabled = true;
  try {
    if (!(await ensureHostPermission(url, interactive))) throw new Error("brak zgody na dostęp do tego adresu");
    const client = new ServerClient(url, token);
    const health = await client.health();
    const [engines, translators] = await Promise.all([client.engines(), client.translators()]);
    fillEngines(engines);
    fillTranslators(translators);
    const cuda = health.cuda?.available ? `CUDA: ${health.cuda.device} (${health.cuda.vram_gb} GB)` : "CUDA: brak (tylko CPU / chmura)";
    const info = $("serverInfo");
    info.classList.remove("hidden");
    info.innerHTML = `PolarnikTTS ${health.version}, ${cuda}<br>` +
      engines.map((e) => e.ready ? `✔ ${e.id}` : `<span class="bad">✘ ${e.id}: ${e.reason}</span>`).join("<br>");
    setStatus($("serverStatus"), "połączono", "ok");
    $("btnStart").classList.add("hidden");
    $("btnStop").classList.toggle("hidden", !isLocalUrl(url));
    lastClient = client;
    if (!manager) manager = createManager({ root: $("manageRoot"), getClient: () => lastClient, onChanged: () => reloadLists() });
    manager.refresh();
    $("aboutStats").textContent = `Serwer ${health.version} · silniki gotowe: ${health.engines_ready.join(", ") || "brak"} · ${cuda}`;
  } catch (e) {
    const down = /Failed to fetch/i.test(e.message);
    setStatus($("serverStatus"), down ? "błąd: serwer nie odpowiada" : `błąd: ${e.message}`, "err");
    $("btnStop").classList.add("hidden");
    if (down && isLocalUrl(url)) $("btnStart").classList.remove("hidden");
    $("manageRoot").innerHTML = '<p class="muted">Uruchom serwer, aby zarządzać silnikami i głosami.</p>';
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
  setStatus($("transferStatus"), "przygotowuję…");
  try {
    const bundle = { format: "polarnik-settings", version: 1, exported_at: new Date().toISOString(),
                     extension: await loadSettings(), server: null };
    if (lastClient) {
      try { bundle.server = await lastClient.manageExport(); }
      catch (e) { setStatus($("transferStatus"), `serwer pominięty: ${e.message}`, "err"); }
    }
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `PolarnikTTS-ustawienia-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    setStatus($("transferStatus"), bundle.server ? "wyeksportowano (rozszerzenie + serwer)" : "wyeksportowano (tylko rozszerzenie)", "ok");
  } catch (e) {
    setStatus($("transferStatus"), `błąd: ${e.message}`, "err");
  }
}

async function importSettings(file) {
  setStatus($("transferStatus"), "importuję…");
  try {
    const bundle = JSON.parse(await file.text());
    if (bundle.format !== "polarnik-settings") throw new Error("to nie jest plik ustawień PolarnikTTS");
    const ext = { ...bundle.extension };
    // keep this machine's server address unless the file points at a LAN server
    if (!ext.serverUrl || isLocalUrl(ext.serverUrl)) ext.serverUrl = settings.serverUrl;
    settings = await saveSettings(ext);
    let serverMsg = "";
    if (bundle.server && lastClient) {
      const r = await lastClient.manageImport(bundle.server);
      serverMsg = `, serwer: ${r.samples_imported} próbek, konfiguracja wczytana`;
    } else if (bundle.server) {
      serverMsg = ", serwer pominięty (brak połączenia)";
    }
    setStatus($("transferStatus"), `zaimportowano rozszerzenie${serverMsg}`, "ok");
    setTimeout(() => location.reload(), 1200);
  } catch (e) {
    setStatus($("transferStatus"), `błąd: ${e.message}`, "err");
  }
}

async function stopServer() {
  $("btnStop").disabled = true;
  setStatus($("serverStatus"), "zatrzymuję serwer…");
  try {
    try { await lastClient.manageShutdown(); }
    catch { await chrome.runtime.sendMessage({ type: "server_stop" }); }
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 300));
      try { await lastClient.health(); } catch { break; }
    }
    setStatus($("serverStatus"), "serwer zatrzymany", "");
    $("btnStop").classList.add("hidden");
    $("btnStart").classList.remove("hidden");
    $("serverInfo").classList.add("hidden");
    $("manageRoot").innerHTML = '<p class="muted">Uruchom serwer, aby zarządzać silnikami i głosami.</p>';
  } finally {
    $("btnStop").disabled = false;
  }
}

// Ask the native messaging host (install_host.cmd) to start the local server, then reconnect.
async function startServer() {
  $("btnStart").disabled = true;
  setStatus($("serverStatus"), "uruchamiam serwer…");
  try {
    const resp = await chrome.runtime.sendMessage({ type: "server_start" });
    if (resp?.ok && resp.running) {
      await connect(false);
    } else if (resp?.hostMissing) {
      setStatus($("serverStatus"), "brak launchera – uruchom install_host.cmd w katalogu PolarnikTTS", "err");
    } else {
      setStatus($("serverStatus"), `nie udało się uruchomić: ${resp?.error || "?"}`, "err");
    }
  } finally {
    $("btnStart").disabled = false;
  }
}

let currentAudio = null;
async function testVoice() {
  const url = $("serverUrl").value.trim() || "http://127.0.0.1:8765";
  const client = new ServerClient(url, $("serverToken").value);
  setStatus($("testStatus"), "synteza…");
  $("btnTest").disabled = true;
  try {
    const t0 = performance.now();
    const res = await client.tts({
      text: $("testText").value.trim(),
      engine: $("engine").value,
      voice: $("voice").value,
      speed: parseFloat($("speed").value),
    });
    const ms = Math.round(performance.now() - t0);
    if (currentAudio) { currentAudio.pause(); URL.revokeObjectURL(currentAudio.src); }
    currentAudio = new Audio(URL.createObjectURL(res.blob));
    await currentAudio.play();
    setStatus($("testStatus"), `${res.engine}/${res.voice}: ${ms} ms (${res.cache === "hit" ? "z cache" : "synteza"}), audio ${res.duration ? res.duration.toFixed(1) + " s" : "?"}`, "ok");
  } catch (e) {
    setStatus($("testStatus"), `błąd: ${e.message}`, "err");
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
    setStatus($("translateTestStatus"), "tłumaczenie YouTube działa w odtwarzaczu – nie da się go sprawdzić stąd", "");
    return;
  }
  const text = $("translateTestText").value.trim();
  if (!text) { setStatus($("translateTestStatus"), "wpisz zdanie", "err"); return; }
  setStatus($("translateTestStatus"), "tłumaczę…");
  $("btnTranslateTest").disabled = true;
  try {
    const t0 = performance.now();
    const res = await client.translate({ sentences: [text], sourceLang: "auto", translator });
    const ms = Math.round(performance.now() - t0);
    out.textContent = res.translations[0] || "(pusta odpowiedź)";
    out.classList.remove("hidden");
    setStatus($("translateTestStatus"), `${res.translator}: ${ms} ms${ms > 8000 ? " – wolno; lektor pierwsze zdania dostanie z opóźnieniem" : ""}`, ms > 8000 ? "" : "ok");
  } catch (e) {
    setStatus($("translateTestStatus"), `błąd: ${e.message}`, "err");
  } finally {
    $("btnTranslateTest").disabled = false;
  }
}

async function save() {
  settings = await saveSettings({
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
  setStatus($("saveStatus"), "zapisano", "ok");
  setTimeout(() => setStatus($("saveStatus"), ""), 2000);
}

async function init() {
  settings = await loadSettings();
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
  $("aboutVersion").textContent = `wersja ${chrome.runtime.getManifest().version}`;
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
