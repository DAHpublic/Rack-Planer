/* Rack-Planer – gemeinsamer Kern für die Webversion (Port von rackcore/ in JavaScript).
 *
 * Enthält Datenmodell (Schrank, Geräte, Fachböden, Belegung, Tiefe, Konflikte), IP-Prüfung
 * und das Dateiformat (*.rack.json inkl. Migration älterer Dateien). Die Regeln entsprechen
 * 1:1 rackcore/model.py, rackcore/ips.py und rackcore/fileformat.py der Desktop-Version –
 * Änderungen dort bitte hier nachziehen (tests/test_web_parity.py vergleicht beide).
 *
 * Läuft im Browser (globales Objekt RackCore) und in Node (module.exports, für Tests).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.RackCore = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const APP_NAME = "Rack-Planer";
  const CAT_NAS = "NAS", CAT_FIREWALL = "Firewall", CAT_SERVER = "Server", CAT_USV = "USV",
    CAT_SWITCH = "Switch", CAT_ROUTER = "Router", CAT_PATCH = "Patchpanel", CAT_ACCESSORY = "Zubehör",
    CAT_OTHER = "Sonstiges", CAT_NVR = "NVR", CAT_PBX = "Telefonanlage", CAT_SHELF = "Fachboden";
  const CATEGORIES = [CAT_NAS, CAT_FIREWALL, CAT_SERVER, CAT_USV, CAT_SWITCH, CAT_ROUTER, CAT_NVR, CAT_PBX,
    CAT_PATCH, CAT_ACCESSORY, CAT_OTHER];
  const CRITICAL_CATEGORIES = [CAT_NAS, CAT_FIREWALL, CAT_SERVER];
  const CATEGORY_COLORS = {
    [CAT_NAS]: "#2f6fb3", [CAT_FIREWALL]: "#c0392b", [CAT_SERVER]: "#3d4a5c", [CAT_USV]: "#d68910",
    [CAT_SWITCH]: "#1e8449", [CAT_ROUTER]: "#8e44ad", [CAT_PATCH]: "#5d6d7e", [CAT_ACCESSORY]: "#7f8c8d",
    [CAT_OTHER]: "#2e86c1", [CAT_NVR]: "#138d75", [CAT_PBX]: "#a04000", [CAT_SHELF]: "#95a5a6",
  };
  const FRONT = "front", REAR = "rear", SIDES = [FRONT, REAR];
  const SIDE_LABEL = { front: "Vorderseite", rear: "Rückseite" };
  const SIDE_SHORT = { front: "vorne", rear: "hinten" };
  const otherSide = (side) => (side === FRONT ? REAR : FRONT);

  const SHELF_WIDTH_MM = 450, U_MM = 44.45, DEFAULT_DEPTH_MM = 800;
  const DEPTH_PRESETS = [450, 600, 800, 1000, 1200];
  const EPS = 1e-6, MAX_IPS = 5, PLATE_U = 1 / 3, SHELF_DEPTH_MM = 400;
  const FORMAT_VERSION = 2, FILE_SUFFIX = ".rack.json";

  /* --- Zahlen wie in Python ------------------------------------------------------------ */
  /** round() wie Python: kaufmännisch, aber genau x,5 zur geraden Zahl. */
  function pyround(x, nd = 0) {
    const m = Math.pow(10, nd);
    const v = x * m;
    const r = Math.round(v);
    const out = Math.abs(v % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
    return nd ? out / m : out;
  }
  /** f"{v:g}" (für Leistungsangaben). */
  const fmtG = (v) => String(Number(Number(v).toPrecision(6)));
  /** Zahl mit deutschem Tausenderpunkt, z. B. 1.234,5 */
  function fmtNum(v, digits = 0) {
    const neg = v < 0;
    let [i, f] = Math.abs(pyround(v, digits)).toFixed(digits).split(".");
    i = i.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (neg ? "-" : "") + i + (f ? "," + f : "");
  }

  function todayIso() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function nowIso() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `${todayIso()}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }
  const snapThird = (v) => pyround(v * 3) / 3;
  function fmtU(value) {
    let whole = Math.floor(value + EPS);
    let frac = pyround((value - whole) * 3);
    if (frac === 3) { whole += 1; frac = 0; }
    return `${whole}` + ({ 0: "", 1: "⅓", 2: "⅔" }[frac] ?? "");
  }
  const fmtRange = (pos, span) => (span <= 1 + EPS ? fmtU(pos) : `${fmtU(pos)}–${fmtU(pos + span - 1)}`);
  function fmtDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    if (!m) return iso || "";
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    if (d.getMonth() !== Number(m[2]) - 1) return iso || "";
    return `${m[3]}.${m[2]}.${m[1]}`;
  }
  function validIsoDate(v) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v || "").slice(0, 10));
    if (!m) return null;
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return d.getMonth() === Number(m[2]) - 1 && d.getDate() === Number(m[3]) ? m[0] : null;
  }
  function splitIps(text) {
    const out = [];
    for (let tok of String(text).replace(/;/g, ",").replace(/ /g, ",").split(",")) {
      tok = tok.trim();
      if (!tok) continue;
      const last = out[out.length - 1];
      if (out.length && tok.startsWith("255.") && !last.includes("/") && !last.includes(" ")) out[out.length - 1] += " " + tok;
      else out.push(tok);
    }
    return out;
  }
  const unitsForCm = (cm) => Math.max(1, Math.ceil(cm * 10 / U_MM - 1e-6));
  const ceilThird = (v) => Math.ceil(v * 3 - 1e-6) / 3;

  function newUid() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, "");
    let s = "";
    for (let i = 0; i < 32; i++) s += Math.floor(Math.random() * 16).toString(16);
    return s;
  }

  /* --- Gerät ---------------------------------------------------------------------------- */
  const ITEM_DEFAULTS = () => ({
    name: "", category: CAT_OTHER, height_u: 1, ip: "", model: "", rackmount: true, width_mm: 440,
    power_w: 0.0, position: 0, shelf_id: "", offset_mm: -1, height_cm: 0.0, show_name: true, ips: [],
    uid: newUid(), depth_mm: 0, mount_side: FRONT, rails: false,
  });
  const ITEM_FIELDS = Object.keys(ITEM_DEFAULTS());

  /** Neues Gerät (Felder wie rackcore.Item, gleiche Reihenfolge für die Datei). */
  function makeItem(fields = {}) {
    const it = ITEM_DEFAULTS();
    for (const k of ITEM_FIELDS) if (k in fields && fields[k] !== undefined) it[k] = fields[k];
    return it;
  }
  const isShelf = (it) => it.category === CAT_SHELF;
  const label = (it) => it.name || it.model || it.category;
  function allIps(it) {
    return [it.ip, ...(it.ips || [])].filter((a) => a && String(a).trim()).map((a) => String(a).trim()).slice(0, MAX_IPS);
  }

  /* --- Schrank -------------------------------------------------------------------------- */
  class Rack {
    constructor(name = "Serverschrank", heightU = 12, depthMm = DEFAULT_DEPTH_MM, asOf = null) {
      this.name = name;
      this.height_u = heightU;
      this.depth_mm = depthMm;
      this.as_of = asOf === null ? todayIso() : asOf;
      this.items = [];
    }

    get(uid) { return this.items.find((i) => i.uid === uid) || null; }
    topLevel(side = null) { return this.items.filter((i) => !i.shelf_id && (side === null || i.mount_side === side)); }
    onShelf(shelfUid) { return this.items.filter((i) => i.shelf_id === shelfUid); }
    devices() { return this.items.filter((i) => !isShelf(i)); }
    topOf(item) { return item.shelf_id ? (this.get(item.shelf_id) || item) : item; }
    sideOf(item) { return this.topOf(item).mount_side; }
    static loadU(dev) { return dev.height_cm > 0 ? dev.height_cm * 10 / U_MM : Number(dev.height_u); }

    shelfSpan(shelf, extra = null) {
      const devs = this.onShelf(shelf.uid).filter((d) => extra === null || d.uid !== extra.uid);
      if (extra !== null) devs.push(extra);
      const load = devs.length ? Math.max(...devs.map((d) => Rack.loadU(d))) : 0;
      if (load <= 0) return Number(shelf.height_u);
      return Math.max(Number(shelf.height_u), ceilThird(PLATE_U + load));
    }
    span(item, heightOverride = null) {
      if (isShelf(item)) return this.shelfSpan(item);
      return heightOverride === null ? item.height_u : heightOverride;
    }
    shelfOverlaps(shelfUid, offset, width, exclude = "") {
      if (offset < 0 || offset + width > SHELF_WIDTH_MM) return true;
      for (const d of this.onShelf(shelfUid)) {
        if (d.uid !== exclude && d.offset_mm >= 0 && offset < d.offset_mm + d.width_mm && d.offset_mm < offset + width) return true;
      }
      return false;
    }
    shelfGap(shelfUid, width, exclude = "") {
      const cands = [0, ...this.onShelf(shelfUid).filter((d) => d.uid !== exclude && d.offset_mm >= 0)
        .map((d) => d.offset_mm + d.width_mm).sort((a, b) => a - b)];
      for (const c of cands) if (!this.shelfOverlaps(shelfUid, c, width, exclude)) return c;
      return -1;
    }
    canPlaceOnShelf(dev, shelf, offset) {
      if (this.shelfOverlaps(shelf.uid, offset, dev.width_mm, dev.uid)) return false;
      const old = [dev.shelf_id, dev.offset_mm];
      dev.shelf_id = shelf.uid; dev.offset_mm = offset;
      try {
        return this.isFree(shelf.position, this.span(shelf), shelf.uid, shelf.mount_side);
      } finally {
        [dev.shelf_id, dev.offset_mm] = old;
      }
    }
    normalize() {
      for (const d of this.items) {
        if (!d.rackmount && d.height_cm <= 0) d.height_cm = pyround(d.height_u * U_MM / 10, 1);
        if (!SIDES.includes(d.mount_side)) d.mount_side = FRONT;
        d.depth_mm = Math.max(0, Math.trunc(Number(d.depth_mm || 0)) || 0);
      }
      for (const s of this.items.filter(isShelf)) {
        for (const d of this.onShelf(s.uid)) {
          d.mount_side = s.mount_side;
          if (d.offset_mm < 0) d.offset_mm = Math.max(0, this.shelfGap(s.uid, d.width_mm, d.uid));
        }
      }
    }
    isFree(pos, span, ignore = "", side = FRONT) {
      if (pos < 1 - EPS || pos + span - 1 > this.height_u + EPS) return false;
      for (const it of this.topLevel(side)) {
        if (it.uid === ignore) continue;
        const a = it.position, b = it.position + this.span(it);
        if (pos < b - EPS && a < pos + span - EPS) return false;
      }
      return true;
    }
    static step(span) { return Math.abs(span - Math.round(span)) < EPS ? 1.0 : 1 / 3; }
    findFree(span, side = FRONT) {
      const step = Rack.step(span);
      let pos = snapThird(Math.floor((this.height_u - span + 1) / step + EPS) * step);
      while (pos >= 1 - EPS) {
        if (this.isFree(pos, span, "", side)) return step === 1 ? Math.trunc(pos) : pos;
        pos = snapThird(pos - step);
      }
      return 0;
    }
    nearestFree(pos, span, ignore = "", side = FRONT) {
      const step = Rack.step(span);
      const n = Math.trunc(this.height_u / step) + 1;
      for (let k = 0; k < n; k++) {
        const dist = k * step;
        for (const cand of [snapThird(pos - dist), snapThird(pos + dist)]) {
          if (this.isFree(cand, span, ignore, side)) return cand;
        }
      }
      return 0;
    }
    occupiedThirds(side = null) {
      const out = new Set();
      for (const it of this.topLevel(side)) {
        const a = pyround(it.position * 3);
        const n = pyround(3 * this.span(it));
        for (let k = a; k < a + n; k++) out.add(k);
      }
      return out;
    }
    usedU(side = null) { return this.occupiedThirds(side).size / 3; }
    requiredHeight() {
      const tops = this.topLevel().map((i) => i.position + this.span(i) - 1);
      const top = tops.length ? Math.max(...tops) : 0;
      return Math.ceil(top - EPS);
    }
    missingUps() {
      const cats = new Set(this.devices().map((d) => d.category));
      if (cats.has(CAT_USV)) return [];
      return CRITICAL_CATEGORIES.filter((c) => cats.has(c));
    }
    totalPower() { return this.devices().reduce((s, d) => s + Number(d.power_w || 0), 0); }
    powerSummary() {
      const p = this.totalPower();
      return `Max. Stromlast: ${fmtNum(p)} W (≈ ${fmtNum(p / 230, 1)} A bei 230 V)   ·   ` +
        `Wärmelast: ${fmtNum(p)} W ≈ ${fmtNum(p * 3.412)} BTU/h`;
    }

    /* --- Tiefe --- */
    depthOf(item) {
      if (isShelf(item)) return Math.max(item.depth_mm, ...this.onShelf(item.uid).map((d) => d.depth_mm));
      return item.depth_mm;
    }
    facing(pos, span, side, ignore = "") {
      const out = [];
      for (const it of this.topLevel(otherSide(side))) {
        if (it.uid === ignore) continue;
        const a = it.position, b = it.position + this.span(it);
        if (pos < b - EPS && a < pos + span - EPS) out.push(it);
      }
      return out;
    }
    freeDepth(pos, span, side, ignore = "") {
      const f = this.facing(pos, span, side, ignore);
      const used = f.length ? Math.max(...f.map((o) => this.depthOf(o))) : 0;
      return Math.max(0, this.depth_mm - used);
    }
    railBlockers(pos, span, side, ignore = "") { return this.facing(pos, span, side, ignore).filter((o) => o.rails); }
    conflicts() {
      const out = [];
      const dmax = this.depth_mm;
      for (const it of this.topLevel()) {
        const d = this.depthOf(it);
        if (dmax > 0 && d > dmax) {
          out.push({ kind: "too_deep", uids: [it.uid], pos: it.position, span: this.span(it),
            text: `„${label(it)}“ ist ${d} mm tief, der Schrank hat nur ${dmax} mm Einbautiefe.` });
        }
      }
      for (const f of this.topLevel(FRONT)) {
        const fa = f.position, fb = f.position + this.span(f);
        for (const r of this.topLevel(REAR)) {
          const ra = r.position, rb = r.position + this.span(r);
          const lo = Math.max(fa, ra), hi = Math.min(fb, rb);
          if (hi - lo <= EPS) continue;
          const he = fmtRange(lo, hi - lo);
          if (f.rails || r.rails) {
            const rail = f.rails ? f : r;
            const victim = rail === f ? r : f;
            out.push({ kind: "rails", uids: [f.uid, r.uid], pos: lo, span: hi - lo,
              text: `„${label(rail)}“ (${SIDE_SHORT[rail.mount_side]}) sitzt auf Einbauschienen, die HE ${he} auf der ` +
                `${SIDE_LABEL[victim.mount_side]} blockieren – dort ist „${label(victim)}“ montiert.` });
            continue;
          }
          const df = this.depthOf(f), dr = this.depthOf(r);
          if (dmax > 0 && df + dr > dmax) {
            out.push({ kind: "depth", uids: [f.uid, r.uid], pos: lo, span: hi - lo,
              text: `HE ${he}: „${label(f)}“ (vorne, ${df} mm) und „${label(r)}“ (hinten, ${dr} mm) brauchen zusammen ` +
                `${df + dr} mm – Einbautiefe ${dmax} mm.` });
          }
        }
      }
      return out;
    }
    conflictUids() { return new Set(this.conflicts().flatMap((c) => c.uids)); }
    railDevices() { return this.topLevel().filter((i) => i.rails); }

    remove(uid) { this.items = this.items.filter((i) => i.uid !== uid && i.shelf_id !== uid); }

    toDict() {
      return { name: this.name, height_u: this.height_u, depth_mm: this.depth_mm, as_of: this.as_of,
        items: this.items.map((i) => { const o = {}; for (const k of ITEM_FIELDS) o[k] = i[k]; return o; }) };
    }
    static fromDict(data) {
      data = data || {};
      const rack = new Rack(data.name ?? "Serverschrank", Math.trunc(Number(data.height_u ?? 12)),
        Math.trunc(Number(data.depth_mm || DEFAULT_DEPTH_MM)), String(data.as_of || ""));
      if (!Number.isFinite(rack.height_u)) throw new Error("Ungültige Höhe");
      if (!Number.isFinite(rack.depth_mm)) throw new Error("Ungültige Tiefe");
      rack.items = [];
      for (const d of data.items || []) {
        const item = makeItem(d);
        item.ips = (Array.isArray(item.ips) ? item.ips : []).map(String).filter((a) => a.trim()).slice(0, MAX_IPS - 1);
        if (!("show_name" in d) && isShelf(item)) item.show_name = false;   // ältere Dateien: Fachboden ohne Namen
        rack.items.push(item);
      }
      rack.normalize();
      return rack;
    }
  }

  /* --- IP-Adressen (wie rackcore/ips.py, Python ipaddress) -------------------------------- */
  function parseV4(s) {
    const p = s.split(".");
    if (p.length !== 4) return null;
    const out = [];
    for (const o of p) {
      if (!/^\d{1,3}$/.test(o)) return null;
      if (o.length > 1 && o[0] === "0") return null;
      const n = Number(o);
      if (n > 255) return null;
      out.push(n);
    }
    return out;
  }
  function parseV6(s) {
    if (!s || s.includes(":::")) return null;
    const halves = s.split("::");
    if (halves.length > 2) return null;
    const groups = (part) => (part === "" ? [] : part.split(":"));
    let head = groups(halves[0]);
    let tail = halves.length === 2 ? groups(halves[1]) : [];
    const all = halves.length === 2 ? tail : head;
    // IPv4 am Ende (z. B. ::ffff:1.2.3.4)
    if (all.length && all[all.length - 1].includes(".")) {
      const v4 = parseV4(all[all.length - 1]);
      if (!v4) return null;
      const repl = [((v4[0] << 8) | v4[1]).toString(16), ((v4[2] << 8) | v4[3]).toString(16)];
      all.splice(all.length - 1, 1, ...repl);
      if (halves.length === 2) tail = all; else head = all;
    }
    const check = (g) => g.every((x) => /^[0-9a-fA-F]{1,4}$/.test(x));
    if (!check(head) || !check(tail)) return null;
    let words;
    if (halves.length === 2) {
      const missing = 8 - head.length - tail.length;
      if (missing < 1) return null;
      words = [...head, ...Array(missing).fill("0"), ...tail];
    } else {
      if (head.length !== 8) return null;
      words = head;
    }
    return words.map((x) => parseInt(x, 16));
  }
  function v6str(words) {
    // längste Folge von mindestens zwei 0-Gruppen durch :: ersetzen (wie Python)
    let best = -1, bestLen = 0, cur = -1, curLen = 0;
    words.forEach((w, i) => {
      if (w === 0) { if (cur < 0) { cur = i; curLen = 0; } curLen++; if (curLen > bestLen) { best = cur; bestLen = curLen; } }
      else { cur = -1; curLen = 0; }
    });
    const hex = words.map((w) => w.toString(16));
    if (bestLen > 1) {
      const left = hex.slice(0, best).join(":"), right = hex.slice(best + bestLen).join(":");
      return `${left}::${right}`;
    }
    return hex.join(":");
  }
  function v4MaskOk(mask) {
    if (/^\d+$/.test(mask)) return Number(mask) <= 32;
    const m = parseV4(mask);
    if (!m) return false;
    const n = ((m[0] << 24) >>> 0) + (m[1] << 16) + (m[2] << 8) + m[3];
    const bits = n.toString(2).padStart(32, "0");
    return /^1*0*$/.test(bits) || /^0*1*$/.test(bits);   // Netzmaske oder Hostmaske
  }
  /** IP-Adresse aus einer Eingabe (mit/ohne Maske, IPv6-Zone); null = ungültig. */
  function parseIp(text) {
    text = String(text).trim().replace(/\s*\/\s*/g, "/");
    if (!text) return null;
    const parts = text.split(/\s+/);
    if (parts.length === 2 && !text.includes("/")) text = `${parts[0]}/${parts[1]}`;
    else if (parts.length !== 1) return null;
    const slash = text.indexOf("/");
    let addr = slash >= 0 ? text.slice(0, slash) : text;
    const mask = slash >= 0 ? text.slice(slash + 1) : "";
    addr = addr.split("%", 1)[0];
    if (/^\d{1,3}(\.\d{1,3}){3}$/.test(addr)) addr = addr.split(".").map((o) => String(Number(o))).join(".");
    const v4 = parseV4(addr);
    if (v4) {
      if (slash >= 0 && !v4MaskOk(mask.trim())) return null;
      return v4.join(".");
    }
    const v6 = parseV6(addr);
    if (v6) {
      if (slash >= 0 && !(/^\d+$/.test(mask.trim()) && Number(mask.trim()) <= 128)) return null;
      return v6str(v6);
    }
    return null;
  }
  const ipIsValid = (text) => !String(text).trim() || parseIp(text) !== null;
  function ipKey(text) {
    const ip = parseIp(text);
    if (ip !== null) return ip;
    return String(text).trim().split("/", 1)[0].trim().toLowerCase();
  }
  /** Doppelte IPs: Map IP → [Geräte] (Reihenfolge wie Python dict). */
  function duplicateIps(rack) {
    const seen = new Map();
    for (const d of rack.devices()) {
      for (const a of allIps(d)) {
        const k = ipKey(a);
        if (!seen.has(k)) seen.set(k, []);
        seen.get(k).push(d);
      }
    }
    const out = new Map();
    for (const [ip, devs] of seen) if (devs.length > 1) out.set(ip, devs);
    return out;
  }

  /* --- Vorlagen ----------------------------------------------------------------------- */
  /** Vorlage aus vorlagen.json vervollständigen (fehlende Felder mit Standardwerten). */
  function normalizeTemplate(t) {
    const rackmount = t.rackmount !== false;
    const heightCm = Number(t.height_cm || 0);
    return {
      group: String(t.group || ""), model: String(t.model || ""), category: String(t.category || CAT_OTHER),
      height_u: rackmount ? Math.max(1, Math.trunc(Number(t.height_u || 1))) : (t.height_u ? Math.trunc(Number(t.height_u)) : unitsForCm(heightCm)),
      rackmount, width_mm: Math.trunc(Number(t.width_mm || SHELF_WIDTH_MM)), power_w: Number(t.power_w || 0),
      note: String(t.note || ""), height_cm: rackmount ? 0 : heightCm, depth_mm: Math.trunc(Number(t.depth_mm || 0)),
      rails: !!t.rails, full_depth: !!t.full_depth,
    };
  }
  let TEMPLATES = [];
  const setTemplates = (list) => { TEMPLATES = list.map(normalizeTemplate); };
  const findTemplate = (model) => TEMPLATES.find((t) => t.model === model) || null;

  /* --- Dateiformat (wie rackcore/fileformat.py) ------------------------------------------ */
  function formatOf(data) {
    const v = Number.parseInt(data.format ?? data.version ?? 1, 10);
    return Number.isFinite(v) ? v : 1;
  }
  /** Ergänzt Werte, die ältere Dateien (Format 1) noch nicht kennen – in place. */
  function migrate(data, notes, fileDate = "") {
    if (formatOf(data) >= 2 && "depth_mm" in data) return;
    const items = data.items || [];
    let guessed = 0;
    for (const d of items) {
      if ("depth_mm" in d) continue;
      const t = findTemplate(String(d.model ?? ""));
      if (t) { d.depth_mm = t.depth_mm; d.rails = t.rails; guessed++; }
      else if (d.category === CAT_SHELF) d.depth_mm = SHELF_DEPTH_MM;
      if (!("mount_side" in d)) d.mount_side = FRONT;
    }
    if (!("depth_mm" in data)) {
      let depth = DEFAULT_DEPTH_MM;
      const deepest = items.length ? Math.max(...items.map((d) => Math.trunc(Number(d.depth_mm || 0)))) : 0;
      if (deepest > depth) depth = DEPTH_PRESETS.find((p) => p >= deepest) ?? deepest;
      data.depth_mm = depth;
      if (notes) notes.push(`Die Datei enthält noch keine Schranktiefe. Sie wurde auf ${depth} mm gesetzt – bitte unter „Schrank“ prüfen.`);
    }
    if (guessed && notes) notes.push(`Für ${guessed} Gerät(e) wurden Tiefe und Einbauschienen aus den Vorlagen ergänzt.`);
    if (!data.as_of) data.as_of = fileDate || todayIso();
  }
  const clone = (o) => JSON.parse(JSON.stringify(o));

  /** Projektdatei lesen → normalisiertes Dokument (wie RackDocument.from_dict().to_dict()). */
  function readDocument(data, fileDate = "") {
    if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Keine Rack-Planer-Projektdatei.");
    data = clone(data);
    const notes = [];
    migrate(data, notes, fileDate);
    let hist = data.history || {};
    if (Array.isArray(hist)) hist = { enabled: hist.length > 0, entries: hist };
    const rack = Rack.fromDict(data);
    const entries = (hist.entries || []).map((e) => {
      const r = clone(e.rack || {});
      migrate(r, null);
      return { saved_at: String(e.saved_at ?? ""), as_of: String(e.as_of || r.as_of || ""), note: String(e.note ?? ""), rack: r };
    });
    const doc = { app: APP_NAME, format: FORMAT_VERSION, version: FORMAT_VERSION, ...rack.toDict(),
      created: String(data.created || data.as_of || todayIso()), saved_at: String(data.saved_at ?? ""),
      history: { enabled: !!hist.enabled, declined: !!hist.declined, entries } };
    return { doc, notes };
  }
  function newDocument() {
    return { app: APP_NAME, format: FORMAT_VERSION, version: FORMAT_VERSION, ...new Rack().toDict(),
      created: todayIso(), saved_at: "", history: { enabled: false, declined: false, entries: [] } };
  }
  /** Projektdatei für einen einzelnen Stand (ohne Historie). */
  function documentForRack(rackDict) {
    const rack = Rack.fromDict(clone(rackDict));
    return { app: APP_NAME, format: FORMAT_VERSION, version: FORMAT_VERSION, ...rack.toDict(),
      created: todayIso(), saved_at: nowIso(), history: { enabled: false, declined: false, entries: [] } };
  }

  return {
    APP_NAME, CAT_NAS, CAT_FIREWALL, CAT_SERVER, CAT_USV, CAT_SWITCH, CAT_ROUTER, CAT_PATCH, CAT_ACCESSORY,
    CAT_OTHER, CAT_NVR, CAT_PBX, CAT_SHELF, CATEGORIES, CRITICAL_CATEGORIES, CATEGORY_COLORS,
    FRONT, REAR, SIDES, SIDE_LABEL, SIDE_SHORT, otherSide, SHELF_WIDTH_MM, U_MM, DEFAULT_DEPTH_MM,
    DEPTH_PRESETS, EPS, MAX_IPS, PLATE_U, SHELF_DEPTH_MM, FORMAT_VERSION, FILE_SUFFIX,
    pyround, fmtG, fmtNum, todayIso, nowIso, snapThird, fmtU, fmtRange, fmtDate, validIsoDate, splitIps,
    unitsForCm, ceilThird, newUid, makeItem, ITEM_FIELDS, isShelf, label, allIps, Rack,
    parseIp, ipIsValid, ipKey, duplicateIps,
    normalizeTemplate, setTemplates, findTemplate, get TEMPLATES() { return TEMPLATES; },
    migrate, readDocument, newDocument, documentForRack, clone,
  };
});
