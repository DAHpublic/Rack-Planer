/* Schriftmaße für die SVG-Zeichnung (Text kürzen, Zeilen einpassen).
 *
 * Gemessen wird mit DejaVu Sans (app/fonts) – direkt aus der TTF-Datei (Vorschubbreiten aus
 * den Tabellen cmap/hmtx, Zeilenmaße aus hhea). Dadurch sind die Maße im Browser, beim Export
 * und in den Tests identisch und entsprechen denen der früheren Python-Version (Pillow).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.RackText = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const FONT_FAMILY = "RackSans, 'DejaVu Sans', Verdana, Arial, sans-serif";

  /** Minimaler TrueType-Leser: Vorschub je Zeichen und Zeilenmaße. */
  function parseTTF(buf) {
    const dv = new DataView(buf instanceof ArrayBuffer ? buf : buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
    const numTables = dv.getUint16(4);
    const tables = {};
    for (let i = 0; i < numTables; i++) {
      const o = 12 + i * 16;
      const tag = String.fromCharCode(dv.getUint8(o), dv.getUint8(o + 1), dv.getUint8(o + 2), dv.getUint8(o + 3));
      tables[tag] = dv.getUint32(o + 8);
    }
    const upm = dv.getUint16(tables.head + 18);
    const hhea = tables.hhea;
    const ascender = dv.getInt16(hhea + 4), descender = dv.getInt16(hhea + 6);
    const numHMetrics = dv.getUint16(hhea + 34);
    const hmtx = tables.hmtx;
    const advOf = (gid) => dv.getUint16(hmtx + 4 * Math.min(gid, numHMetrics - 1));
    // cmap: Unicode-Tabelle Format 4 (BMP) bzw. 12
    const cmap = tables.cmap;
    const n = dv.getUint16(cmap + 2);
    let sub4 = null, sub12 = null;
    for (let i = 0; i < n; i++) {
      const pid = dv.getUint16(cmap + 4 + i * 8), eid = dv.getUint16(cmap + 6 + i * 8);
      const off = cmap + dv.getUint32(cmap + 8 + i * 8);
      const fmt = dv.getUint16(off);
      if (fmt === 4 && (pid === 3 && eid === 1 || pid === 0)) sub4 = sub4 ?? off;
      if (fmt === 12 && (pid === 3 && eid === 10 || pid === 0)) sub12 = sub12 ?? off;
    }
    const cache = new Map();
    function glyph(cp) {
      if (cache.has(cp)) return cache.get(cp);
      let gid = 0;
      if (sub12 !== null) {
        const groups = dv.getUint32(sub12 + 12);
        for (let i = 0; i < groups; i++) {
          const g = sub12 + 16 + i * 12;
          const s = dv.getUint32(g), e = dv.getUint32(g + 4);
          if (cp >= s && cp <= e) { gid = dv.getUint32(g + 8) + (cp - s); break; }
        }
      } else if (sub4 !== null && cp <= 0xffff) {
        const segX2 = dv.getUint16(sub4 + 6);
        const ends = sub4 + 14, starts = ends + segX2 + 2, deltas = starts + segX2, ranges = deltas + segX2;
        for (let i = 0; i < segX2; i += 2) {
          if (cp > dv.getUint16(ends + i)) continue;
          const start = dv.getUint16(starts + i);
          if (cp < start) break;
          const delta = dv.getInt16(deltas + i), ro = dv.getUint16(ranges + i);
          if (ro === 0) gid = (cp + delta) & 0xffff;
          else {
            const g = dv.getUint16(ranges + i + ro + 2 * (cp - start));
            gid = g ? (g + delta) & 0xffff : 0;
          }
          break;
        }
      }
      cache.set(cp, gid);
      return gid;
    }
    return { upm, ascender, descender, advance: (cp) => advOf(glyph(cp)) };
  }

  const fonts = { regular: null, bold: null };
  function setFontData(regular, bold) {
    fonts.regular = parseTTF(regular);
    fonts.bold = parseTTF(bold);
  }

  class Font {
    constructor(size, bold = false) {
      this.size = Math.trunc(size);
      this.bold = bold;
      const f = bold ? fonts.bold : fonts.regular;
      this._f = f;
      if (f) {
        this.ascent = Math.ceil(f.ascender * this.size / f.upm - 1e-9);
        this.descent = Math.ceil(-f.descender * this.size / f.upm - 1e-9);
      } else {
        this.ascent = Math.round(this.size * 0.93);
        this.descent = Math.round(this.size * 0.24);
      }
      this._w = new Map();
    }
    withSize(size) { return new Font(size, this.bold); }
    height() { return this.ascent + this.descent; }
    width(text) {
      if (this._w.has(text)) return this._w.get(text);
      let w;
      if (this._f) {
        let units = 0;
        for (const ch of text) units += Math.round(this._f.advance(ch.codePointAt(0)) * this.size / this._f.upm * 64);
        w = units / 64;
      } else w = [...text].length * this.size * (this.bold ? 0.66 : 0.6);
      this._w.set(text, w);
      return w;
    }
    /** Text mit „…“ kürzen, bis er in width passt. */
    elide(text, width) {
      if (this.width(text) <= width) return text;
      if (width <= this.width("…")) return "";
      const chars = [...text];
      let lo = 0, hi = chars.length;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (this.width(chars.slice(0, mid).join("") + "…") <= width) lo = mid;
        else hi = mid - 1;
      }
      return chars.slice(0, lo).join("").trimEnd() + "…";
    }
  }
  const cacheFonts = new Map();
  function font(size, bold = false) {
    const k = `${Math.trunc(size)}|${bold}`;
    if (!cacheFonts.has(k) || cacheFonts.get(k)._f !== (bold ? fonts.bold : fonts.regular)) cacheFonts.set(k, new Font(size, bold));
    return cacheFonts.get(k);
  }
  /** Schriftgröße in Szeneneinheiten (wie die Desktop-Version). */
  const px = (pt) => Math.round(pt * 96 / 72);

  return { FONT_FAMILY, parseTTF, setFontData, Font, font, px };
});
