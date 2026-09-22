// Service worker: sniffs the caption track URL the YouTube player requests
// (/api/timedtext) per tab and hands it to the content script / popup on demand.

import { loadSettings } from "../lib/settings.js";

const NATIVE_HOST = "pl.polarnik.launcher";

/** tabId -> { url, headers, ts } */
const timedtextByTab = new Map();

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (details.tabId < 0) return;
    const headers = {};
    for (const h of details.requestHeaders || []) {
      const name = h.name.toLowerCase();
      if (name.startsWith("x-")) headers[name] = h.value;
    }
    timedtextByTab.set(details.tabId, { url: details.url, headers, ts: Date.now() });
  },
  { urls: ["*://*.youtube.com/api/timedtext*"] },
  ["requestHeaders", "extraHeaders"],
);

chrome.tabs.onRemoved.addListener((tabId) => timedtextByTab.delete(tabId));

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  await loadSettings(); // materialize defaults
  if (reason === "install") chrome.runtime.openOptionsPage();
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg?.type) {
    case "get_timedtext": {
      const tabId = msg.tabId ?? sender.tab?.id;
      sendResponse(timedtextByTab.get(tabId) || null);
      return false;
    }
    case "fetch_timedtext": {
      // Fetch the caption track as json3 (optionally auto-translated by YouTube via tlang).
      const tabId = msg.tabId ?? sender.tab?.id;
      const entry = timedtextByTab.get(tabId);
      if (!entry) { sendResponse({ error: "no timedtext url for this tab" }); return false; }
      const url = new URL(entry.url);
      url.searchParams.set("fmt", "json3");
      if (msg.tlang && url.searchParams.get("lang") !== msg.tlang) url.searchParams.set("tlang", msg.tlang);
      fetch(url.toString(), { headers: entry.headers })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((json) => sendResponse({ url: url.toString(), events: json.events || [] }))
        .catch((e) => sendResponse({ error: String(e) }));
      return true; // async
    }
    case "open_options":
      chrome.runtime.openOptionsPage();
      return false;
    case "server_status":
    case "server_start":
    case "server_stop": {
      // Native messaging host (registered by install_host.cmd) starts/stops the engine server.
      const cmd = msg.type.replace("server_", "");
      chrome.runtime.sendNativeMessage(NATIVE_HOST, { cmd }, (resp) => {
        if (chrome.runtime.lastError) {
          const err = chrome.runtime.lastError.message || "";
          const missing = /not found|nie znaleziono/i.test(err);
          sendResponse({ ok: false, hostMissing: missing, error: err });
        } else {
          sendResponse(resp || { ok: false, error: "empty reply from host" });
        }
      });
      return true; // async
    }
    default:
      return false;
  }
});

async function updateBadge() {
  const s = await loadSettings();
  await chrome.action.setBadgeText({ text: s.enabled ? "" : "off" });
  await chrome.action.setBadgeBackgroundColor({ color: "#666" });
}
chrome.storage.onChanged.addListener(updateBadge);
updateBadge();
