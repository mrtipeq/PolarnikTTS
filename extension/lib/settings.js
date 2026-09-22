// Settings stored in chrome.storage.local (server URL differs per machine, so no sync).

export const DEFAULT_SETTINGS = {
  enabled: true,
  serverUrl: "http://127.0.0.1:8765",
  serverToken: "",
  engine: "",            // "" = server default
  voice: "",             // "" = engine default
  speed: 1.0,            // base speaking rate requested from the engine
  translator: "youtube", // "youtube" | id of a server-side translator
  voiceVolume: 1.0,      // volume of the Polish voice (0..1)
  duckingDb: -12,        // original audio level while the Polish voice speaks
  offsetMs: 0,           // shift Polish speech relative to subtitle timing
  lookaheadS: 30,        // how far ahead sentences are synthesized
  maxRate: 1.35,         // max playback speed-up used to fit a sentence into its slot
  lagMode: "speed",      // "speed": speed the voice up | "video": slow the video down when the voice lags
};

/** Settings whose change requires re-synthesizing (new session); the rest apply live. */
export const RESTART_KEYS = ["serverUrl", "serverToken", "engine", "voice", "speed", "translator"];

export async function loadSettings() {
  const stored = await chrome.storage.local.get("settings");
  return { ...DEFAULT_SETTINGS, ...(stored.settings || {}) };
}

export async function saveSettings(patch) {
  const current = await loadSettings();
  const next = { ...current, ...patch };
  await chrome.storage.local.set({ settings: next });
  return next;
}

export function onSettingsChanged(callback) {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.settings) {
      callback({ ...DEFAULT_SETTINGS, ...(changes.settings.newValue || {}) });
    }
  });
}
