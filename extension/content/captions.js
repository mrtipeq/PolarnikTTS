// Caption (json3) parsing and sentence reconstruction. Pure functions, no DOM.

const SENTENCE_END = /[.!?…]["»”)]?$/;
const MAX_SENTENCE_MS = 7000;   // split long auto-caption runs even without punctuation
const MAX_WORDS = 28;
const GAP_MS = 700;             // silence that ends a sentence

/** json3 events -> [{start, end, text}] lines (ms). */
export function eventsToLines(events) {
  const lines = [];
  for (const ev of events || []) {
    if (!Array.isArray(ev.segs)) continue;
    // drop [Music]/[Applause]-style tags before merging so they do not glue sentences together
    const text = ev.segs.map((s) => s.utf8 || "").join("").replace(/\[[^\]]{1,40}\]/g, "").replace(/\s+/g, " ").trim();
    if (!text) continue;
    const start = ev.tStartMs || 0;
    const dur = ev.dDurationMs || 0;
    lines.push({ start, end: start + dur, text });
  }
  lines.sort((a, b) => a.start - b.start);
  return lines;
}

function countWords(s) {
  return s.split(/\s+/).filter(Boolean).length;
}

/** Merge lines into sentence-sized units: [{index, start, end, slotEnd, text}]. */
export function linesToSentences(lines) {
  const out = [];
  let cur = null;
  let prevEnd = 0;
  for (const line of lines) {
    const gap = line.start - prevEnd;
    if (cur) {
      const tooLong = line.start - cur.start > MAX_SENTENCE_MS || countWords(cur.text) >= MAX_WORDS;
      if (SENTENCE_END.test(cur.text) || gap > GAP_MS || tooLong) {
        out.push(cur);
        cur = null;
      }
    }
    if (!cur) {
      cur = { start: line.start, end: line.end, text: line.text };
    } else {
      cur.text += " " + line.text;
      cur.end = Math.max(cur.end, line.end);
    }
    prevEnd = Math.min(line.end, line.start + 4000); // auto captions stretch dDurationMs a lot
  }
  if (cur) out.push(cur);
  // Index and compute the time slot (until the next sentence starts).
  const cleaned = out.filter((s) => s.text.length > 0);
  cleaned.forEach((s, i) => {
    s.index = i;
    s.slotEnd = i + 1 < cleaned.length ? cleaned[i + 1].start : s.end;
    if (s.slotEnd - s.start < 400) s.slotEnd = s.start + 400;
  });
  return cleaned;
}

/** Parse a timedtext body in json3 or srv3 (XML) format into json3-style events. */
export function parseTimedtext(body) {
  const text = (body || "").trim();
  if (!text) return null;
  if (text.startsWith("{")) {
    try { return JSON.parse(text).events || []; } catch { return null; }
  }
  if (text.startsWith("<")) {
    const doc = new DOMParser().parseFromString(text, "text/xml");
    const events = [];
    for (const p of doc.querySelectorAll("body > p, transcript > text")) {
      const start = parseInt(p.getAttribute("t") ?? Math.round(parseFloat(p.getAttribute("start") || "0") * 1000), 10);
      const dur = parseInt(p.getAttribute("d") ?? Math.round(parseFloat(p.getAttribute("dur") || "0") * 1000), 10);
      const utf8 = p.textContent || "";
      events.push({ tStartMs: start || 0, dDurationMs: dur || 0, segs: [{ utf8 }] });
    }
    return events;
  }
  return null;
}

export function isPolishLike(text) {
  // crude check used to detect that the track is already Polish
  return /[ąćęłńóśźż]/i.test(text) && /\b(i|nie|się|jest|to|na|że)\b/i.test(text);
}
