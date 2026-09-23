import { ServerClient } from "../lib/api.js";
import { loadSettings, saveSettings } from "../lib/settings.js";

const $ = (id) => document.getElementById(id);
// Polish plural for "silnik": 1 silnik, 2-4 silniki, 5+ silników (and 12-14 -> silników).
const engines = (n) => `${n} ${n === 1 ? "silnik" : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? "silniki" : "silników"}`;

async function init() {
  const settings = await loadSettings();
  $("enabled").checked = settings.enabled;
  $("enabled").addEventListener("change", (e) => saveSettings({ enabled: e.target.checked }));
  $("btnOptions").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("aboutLine").textContent = `PolarnikTTS ${chrome.runtime.getManifest().version} · MrTip (Tipson)`;
  $("engineText").textContent = settings.engine ? `${settings.engine}${settings.voice ? " / " + settings.voice : ""}` : "silnik: domyślny";

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // Server status
  try {
    const health = await new ServerClient(settings.serverUrl, settings.serverToken).health();
    $("serverDot").className = "dot ok";
    const ready = health.engines_ready || [];
    $("serverText").textContent = `v${health.version} · ${ready.length ? engines(ready.length) : "brak silników"}`;
    $("serverText").title = ready.join(", ");
    $("startRow").hidden = true;
  } catch {
    $("serverDot").className = "dot err";
    $("serverText").textContent = "niedostępny";
    $("startRow").hidden = false;
  }
  $("btnStart").addEventListener("click", async () => {
    $("btnStart").disabled = true;
    $("startText").textContent = "uruchamiam…";
    const resp = await chrome.runtime.sendMessage({ type: "server_start" });
    if (resp?.ok && resp.running) {
      $("startText").textContent = "";
      $("startRow").hidden = true;
      $("serverDot").className = "dot ok";
      $("serverText").textContent = "uruchomiony";
      if (tab?.id) chrome.tabs.sendMessage(tab.id, { type: "restart" }).catch(() => {});
    } else {
      $("startText").textContent = resp?.hostMissing ? "brak launchera – uruchom install_host.cmd" : `błąd: ${resp?.error || "?"}`;
      $("btnStart").disabled = false;
    }
  });

  // Caption track sniffed for the active tab
  if (!tab || !/^https:\/\/www\.youtube\.com\//.test(tab.url || "")) {
    $("capText").textContent = "to nie jest YouTube";
    return;
  }
  const entry = await chrome.runtime.sendMessage({ type: "get_timedtext", tabId: tab.id });
  if (!entry) {
    $("capText").textContent = "nie wykryto";
  } else {
    const u = new URL(entry.url);
    const lang = u.searchParams.get("lang") || "?";
    const kind = u.searchParams.get("kind") === "asr" ? "automatyczne" : "ręczne";
    $("capDot").className = "dot ok";
    $("capText").textContent = `${lang} (${kind})`;
  }

  // Pipeline status from the content script
  try {
    const info = await chrome.tabs.sendMessage(tab.id, { type: "page_info" });
    const modeText = { polish: "napisy PL", youtube: "tłum. YouTube", server: `tłum. LLM, ${info.translated} przetł.` }[info.mode] || "?";
    const labels = {
      off: "wyłączony", idle: "czeka na film", loading: "pobieram napisy…",
      working: info.holding ? "tłumaczę pierwsze zdania…" : `mówi (${info.cursor}/${info.sentences} zdań, ${modeText})`,
      nocaptions: "film bez napisów", error: `błąd: ${info.lastError}`,
    };
    $("lekText").textContent = labels[info.status] || info.status;
    $("lekDot").className = "dot " + (info.status === "working" ? "ok" : info.status === "error" ? "err" : "");
    if (info.notice) {
      const row = document.createElement("div");
      row.className = "row muted";
      row.style.cssText = "font-size:11px;line-height:1.35;display:block";
      row.textContent = "⚠ " + info.notice;
      $("lekText").closest(".row").insertAdjacentElement("afterend", row);
    }
  } catch {
    $("lekText").textContent = "odśwież kartę YouTube";
  }
}

init();
