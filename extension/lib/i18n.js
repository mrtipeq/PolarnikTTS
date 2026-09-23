// Runtime localisation. Chrome's chrome.i18n follows the browser language only, so the
// extension ships its own flat JSON dictionaries in locales/<code>.json and lets the user
// override the language in the settings ("auto" = system language, English when the
// system language has no dictionary). Missing keys fall back to English, then to the key.

// Languages the UI is translated into (code -> native name). Order = order in pickers.
export const UI_LANGS = {
  pl: "polski", en: "English", zh: "中文（普通话）", yue: "粵語", hi: "हिन्दी", es: "español", fr: "français",
  ar: "العربية", bn: "বাংলা", pt: "português", ru: "русский", ur: "اردو", id: "Bahasa Indonesia", de: "Deutsch",
  ja: "日本語", sw: "Kiswahili", mr: "मराठी", te: "తెలుగు", tr: "Türkçe", ta: "தமிழ்", vi: "Tiếng Việt",
  ko: "한국어", fa: "فارسی",
};

// Languages the voice-over can be produced in (code -> native name). Mirrors the server's
// languages.py; the server's /languages is the authority once connected.
export const TARGET_LANGS = {
  ...UI_LANGS,
  cs: "čeština", hu: "magyar", uk: "українська", it: "italiano", nl: "Nederlands", ro: "română", el: "Ελληνικά",
  sv: "svenska", da: "dansk", fi: "suomi", no: "norsk", sk: "slovenčina", he: "עברית", th: "ไทย", ms: "Bahasa Melayu",
  bg: "български", hr: "hrvatski", sr: "српски", sl: "slovenščina", lt: "lietuvių", lv: "latviešu", et: "eesti",
  ca: "català", fil: "Filipino",
};

export const RTL_LANGS = new Set(["ar", "ur", "fa", "he"]);

/** Map any BCP-47 tag ("pt-BR", "zh-HK", "zh_TW", "iw") onto our language codes. */
export function normalizeLangTag(tag) {
  tag = String(tag || "").toLowerCase().replace("_", "-");
  if (/^zh-(hk|mo|yue)/.test(tag) || tag.startsWith("yue")) return "yue";
  if (tag.startsWith("zh")) return "zh";
  if (tag === "iw" || tag.startsWith("iw-")) return "he";
  if (/^(nb|nn)/.test(tag)) return "no";
  if (/^tl/.test(tag)) return "fil";
  return tag.split("-")[0];
}

/** Base language code of the browser/system UI, mapped onto our codes. */
export function systemLang() {
  let tag = "";
  try { tag = chrome.i18n.getUILanguage(); } catch { /* not in an extension context */ }
  return normalizeLangTag(tag || navigator.language || "en");
}

/** YouTube auto-translate target code for one of our language codes. */
export function youtubeTlang(code) {
  return { zh: "zh-Hans", yue: "zh-Hant", he: "iw" }[code] || code;
}

/** UI language for the given settings: explicit choice, else system language if translated, else English. */
export function resolveUiLang(settings) {
  const pick = settings?.uiLang && settings.uiLang !== "auto" ? settings.uiLang : systemLang();
  return UI_LANGS[pick] ? pick : "en";
}

/** Voice-over language: explicit choice, else the system language if supported, else English. */
export function resolveTargetLang(settings) {
  const pick = settings?.targetLang && settings.targetLang !== "auto" ? settings.targetLang : systemLang();
  return TARGET_LANGS[pick] ? pick : "en";
}

const cache = new Map();

async function loadDict(code) {
  if (cache.has(code)) return cache.get(code);
  let dict = {};
  try {
    const r = await fetch(chrome.runtime.getURL(`locales/${code}.json`));
    if (r.ok) dict = await r.json();
  } catch { /* keep empty */ }
  cache.set(code, dict);
  return dict;
}

/**
 * Load the dictionaries and return a translator: t("key") or t("key", {name: "x"}) with
 * {name} placeholders. Also exposes t.lang and t.dir ("ltr" | "rtl").
 */
export async function initI18n(settings) {
  const lang = resolveUiLang(settings);
  const [dict, en] = await Promise.all([loadDict(lang), lang === "en" ? Promise.resolve({}) : loadDict("en")]);
  const t = (key, subs) => {
    let s = dict[key] ?? en[key] ?? key;
    if (subs) for (const [k, v] of Object.entries(subs)) s = s.split(`{${k}}`).join(String(v));
    return s;
  };
  t.lang = lang;
  t.dir = RTL_LANGS.has(lang) ? "rtl" : "ltr";
  t.has = (key) => key in dict || key in en;
  return t;
}

/** Apply data-i18n / data-i18n-placeholder / data-i18n-title attributes in a document. */
export function localizeDom(t, root = document) {
  for (const el of root.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of root.querySelectorAll("[data-i18n-html]")) el.innerHTML = t(el.dataset.i18nHtml);
  for (const el of root.querySelectorAll("[data-i18n-placeholder]")) el.placeholder = t(el.dataset.i18nPlaceholder);
  for (const el of root.querySelectorAll("[data-i18n-title]")) el.title = t(el.dataset.i18nTitle);
  if (root === document) {
    document.documentElement.lang = t.lang;
    document.documentElement.dir = t.dir;
  }
}
