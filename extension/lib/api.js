// Thin client for the PolarnikTTS engine server.

export class ServerClient {
  constructor(baseUrl, token = "") {
    this.baseUrl = String(baseUrl || "").replace(/\/+$/, "");
    this.token = token || "";
  }

  headers(extra = {}) {
    const h = { ...extra };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  }

  async getJson(path) {
    const r = await fetch(`${this.baseUrl}${path}`, { headers: this.headers() });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status} ${await r.text()}`);
    return r.json();
  }

  health() { return this.getJson("/health"); }
  engines() { return this.getJson("/engines"); }
  translators() { return this.getJson("/translators"); }

  async postJson(path, body) {
    const r = await fetch(`${this.baseUrl}${path}`, {
      method: "POST", headers: this.headers({ "Content-Type": "application/json" }), body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status} ${await r.text()}`);
    return r.json();
  }

  // ---- management API (local-only on the server side) ----
  manageCatalog() { return this.getJson("/manage/catalog"); }
  manageInstall(engine, voices) { return this.postJson("/manage/install", { engine, voices: voices || null }); }
  manageJob(id, tail = 40) { return this.getJson(`/manage/jobs/${id}?tail=${tail}`); }
  languages() { return this.getJson("/languages"); }
  manageOllama() { return this.getJson("/manage/ollama"); }
  manageModels(section, id) { return this.getJson(`/manage/models?section=${section}&id=${encodeURIComponent(id)}`); }
  manageOllamaPull(model) { return this.postJson("/manage/ollama/pull", { model }); }
  manageConfig(section, id, values) { return this.postJson("/manage/config", { section, id, values }); }
  manageReload() { return this.postJson("/manage/reload", {}); }
  manageShutdown() { return this.postJson("/manage/shutdown", {}); }
  manageSamples() { return this.getJson("/manage/samples"); }
  manageExport() { return this.getJson("/manage/export"); }
  manageImport(bundle) { return this.postJson("/manage/import", bundle); }
  manageSecret(section, id, key) { return this.getJson(`/manage/secret?section=${section}&id=${encodeURIComponent(id)}&key=${key}`); }
  async manageUploadSample(file) {
    const r = await fetch(`${this.baseUrl}/manage/samples?name=${encodeURIComponent(file.name)}`, {
      method: "POST", headers: this.headers({ "Content-Type": "application/octet-stream" }), body: file,
    });
    if (!r.ok) throw new Error(`upload: HTTP ${r.status} ${await r.text()}`);
    return r.json();
  }
  async manageDeleteSample(name) {
    const r = await fetch(`${this.baseUrl}/manage/samples/${encodeURIComponent(name)}`, { method: "DELETE", headers: this.headers() });
    if (!r.ok) throw new Error(`delete: HTTP ${r.status} ${await r.text()}`);
    return r.json();
  }
  sampleAudioUrl(name) { return `${this.baseUrl}/manage/samples/${encodeURIComponent(name)}/audio`; }

  /** Returns { blob, duration, cache, engine, voice }. */
  async tts({ text, engine, voice, speed, lang }) {
    const r = await fetch(`${this.baseUrl}/tts`, {
      method: "POST",
      headers: this.headers({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text, engine: engine || null, voice: voice || null, speed: speed || 1.0, lang: lang || "pl" }),
    });
    if (!r.ok) throw new Error(`/tts: HTTP ${r.status} ${await r.text()}`);
    return {
      blob: await r.blob(),
      duration: parseFloat(r.headers.get("X-Duration") || "0") || null,
      cache: r.headers.get("X-Cache"),
      engine: r.headers.get("X-Engine"),
      voice: r.headers.get("X-Voice"),
    };
  }

  async translate({ sentences, sourceLang = "auto", contextBefore = [], contextAfter = [], translator, targetLang }) {
    const r = await fetch(`${this.baseUrl}/translate`, {
      method: "POST",
      headers: this.headers({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        sentences, source_lang: sourceLang, context_before: contextBefore,
        context_after: contextAfter, translator: translator || null, target_lang: targetLang || "pl",
      }),
    });
    if (!r.ok) throw new Error(`/translate: HTTP ${r.status} ${await r.text()}`);
    return r.json();
  }
}

/** Origin pattern for chrome.permissions, e.g. "http://192.168.1.10:8765/" -> "http://192.168.1.10/*". */
export function originPattern(url) {
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.hostname}/*`;
  } catch {
    return null;
  }
}

export function isLocalUrl(url) {
  try {
    const h = new URL(url).hostname;
    return h === "127.0.0.1" || h === "localhost" || h === "::1";
  } catch {
    return false;
  }
}
