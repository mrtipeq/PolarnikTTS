import { ServerClient } from "../lib/api.js";
import { loadSettings, saveSettings } from "../lib/settings.js";
import { initI18n, localizeDom, resolveTargetLang, TARGET_LANGS } from "../lib/i18n.js";

const $ = (id) => document.getElementById(id);
let t = (k) => k;
// Plural forms come from the dictionary: "n.engines.one|few|many" (Polish needs three), "|"-separated.
function engines(n) {
  const forms = t("popup.engines").split("|");
  const idx = n === 1 ? 0 : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? 1 : 2;
  return `${n} ${forms[Math.min(idx, forms.length - 1)].trim()}`;
}

async function init() {
  const settings = await loadSettings();
  t = await initI18n(settings);
  localizeDom(t);
  $("enabled").checked = settings.enabled;
  $("enabled").addEventListener("change", (e) => saveSettings({ enabled: e.target.checked }));
  $("btnOptions").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("aboutLine").textContent = `PolarnikTTS ${chrome.runtime.getManifest().version} · MrTip (Tipson)`;
  const lang = resolveTargetLang(settings);
  $("engineText").textContent = `${TARGET_LANGS[lang] || lang} · ` + (settings.engine ? `${settings.engine}${settings.voice ? " / " + settings.voice : ""}` : t("popup.engineDefault"));

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // Server status
  try {
    const health = await new ServerClient(settings.serverUrl, settings.serverToken).health();
    $("serverDot").className = "dot ok";
    const ready = health.engines_ready || [];
    $("serverText").textContent = `v${health.version} · ${ready.length ? engines(ready.length) : t("popup.noEngines")}`;
    $("serverText").title = ready.join(", ");
    $("startRow").hidden = true;
  } catch {
    $("serverDot").className = "dot err";
    $("serverText").textContent = t("popup.unavailable");
    $("startRow").hidden = false;
  }
  $("btnStart").addEventListener("click", async () => {
    $("btnStart").disabled = true;
    $("startText").textContent = t("common.startingServer");
    const resp = await chrome.runtime.sendMessage({ type: "server_start" });
    if (resp?.ok && resp.running) {
      $("startText").textContent = "";
      $("startRow").hidden = true;
      $("serverDot").className = "dot ok";
      $("serverText").textContent = t("popup.started");
      if (tab?.id) chrome.tabs.sendMessage(tab.id, { type: "restart" }).catch(() => {});
    } else {
      $("startText").textContent = resp?.hostMissing ? t("common.hostMissing") : t("common.failed", { error: resp?.error || "?" });
      $("btnStart").disabled = false;
    }
  });

  // Caption track sniffed for the active tab
  if (!tab || !/^https:\/\/www\.youtube\.com\//.test(tab.url || "")) {
    $("capText").textContent = t("popup.notYoutube");
    return;
  }
  const entry = await chrome.runtime.sendMessage({ type: "get_timedtext", tabId: tab.id });
  if (!entry) {
    $("capText").textContent = t("popup.notDetected");
  } else {
    const u = new URL(entry.url);
    const lang = u.searchParams.get("lang") || "?";
    const kind = u.searchParams.get("kind") === "asr" ? t("popup.auto") : t("popup.manual");
    $("capDot").className = "dot ok";
    $("capText").textContent = `${lang} (${kind})`;
  }

  // Pipeline status from the content script
  try {
    const info = await chrome.tabs.sendMessage(tab.id, { type: "page_info" });
    const modeText = { native: t("popup.modeNative"), youtube: t("popup.modeYoutube"), server: t("popup.modeServer", { n: info.translated }) }[info.mode] || "?";
    const labels = {
      off: t("status.offShort"), idle: t("popup.idle"), loading: t("status.loading"),
      working: info.holding ? t("status.holding") : t("popup.speaking", { cursor: info.cursor, total: info.sentences, mode: modeText }),
      nocaptions: t("status.nocaptions"), error: t("status.error", { error: info.lastError }),
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
    $("lekText").textContent = t("popup.refreshTab");
  }
}

init();
