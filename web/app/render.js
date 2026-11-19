/* Zeichnung des Schranks als SVG – gleiche Optik wie die Desktop-Version (planer2d/scene.py).
 *
 * Dieselbe Funktion liefert die Ansicht im Browser (dunkle Farben, mit Auswahl, Gegenseite und
 * Seitenansicht) und die Exporte (helle, druckfreundliche Farben, nur Schrank und Beschriftung).
 * Elemente tragen data-Attribute, damit der Browser Auswahl und Drag & Drop umsetzen kann.
 */
(function (root, factory) {
  const isNode = typeof module === "object" && module.exports;
  const api = factory(isNode ? require("./core.js") : root.RackCore, isNode ? require("./textfit.js") : root.RackText);
  if (isNode) module.exports = api;
  else root.RackRender = api;
})(typeof self !== "undefined" ? self : this, function (C, T) {
  "use strict";
  const { FRONT, SHELF_WIDTH_MM, SIDE_LABEL, SIDE_SHORT, U_MM, EPS, fmtDate, fmtRange, otherSide, label, allIps, isShelf, fmtG } = C;
  const { font, px, FONT_FAMILY } = T;

  const U_PX = 32.0, INNER_W = 440.0, RAIL_W = 34.0, FRAME = 14.0, TITLE_H = 54.0;
  const RACK_W = INNER_W + 2 * RAIL_W + 2 * FRAME;
  const PROFILE_GAP = 34.0, PROFILE_W = 150.0, EAR_W = 10, PLATE_H = U_PX / 3;
  const SHELF_SCALE = (INNER_W - 8) / SHELF_WIDTH_MM;
  const UI_ACCENT = "#e8800c", CONFLICT_RED = "#e5413a";

  const RACK_INK = {
    screen: {
      title: "#ececec", frame: "#3d3d3d", frame_edge: "#1a1a1a", inner: "#212121",
      rail: "#a9adb0", grid: "#2d2d2d", rail_line: "#7b7f82", hole: "#4b4e51",
      number: "#1c1c1c", feet: "#1a1a1a", plate: "#8c9093", plate_edge: "#55585b",
      slot: "#6d7073", bracket: "#6d7073", shelf_text: "#c9ccce",
      select: UI_ACCENT, subtitle: "#a9adb0", ghost: "#9aa0a6", profile_bg: "#1b1b1b",
    },
    print: {
      title: "#222222", frame: "#2b2f36", frame_edge: "#1c1f24", inner: "#f4f5f7",
      rail: "#9aa0a8", grid: "#d9dce1", rail_line: "#6f757d", hole: "#555b63",
      number: "#1d1f22", feet: "#1c1f24", plate: "#aab3b5", plate_edge: "#5f6a6a",
      slot: "#7f8c8d", bracket: "#7f8c8d", shelf_text: "#2c3e50",
      select: UI_ACCENT, subtitle: "#555b63", ghost: "#6f757d", profile_bg: "#ffffff",
    },
  };

  /* --- Farben (wie QColor.darker/lighter) --- */
  const rgb = (c) => { c = c.replace("#", ""); return [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16) / 255); };
  const hex = (r, g, b) => "#" + [r, g, b].map((x) => Math.max(0, Math.min(255, C.pyround(x * 255))).toString(16).padStart(2, "0")).join("");
  function rgbToHsv(r, g, b) {
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
    const v = mx;
    if (mn === mx) return [0, 0, v];
    const s = (mx - mn) / mx;
    const rc = (mx - r) / (mx - mn), gc = (mx - g) / (mx - mn), bc = (mx - b) / (mx - mn);
    let h;
    if (r === mx) h = bc - gc; else if (g === mx) h = 2 + rc - bc; else h = 4 + gc - rc;
    h = ((h / 6) % 1 + 1) % 1;
    return [h, s, v];
  }
  function hsvToRgb(h, s, v) {
    if (s === 0) return [v, v, v];
    const i = Math.floor(h * 6), f = h * 6 - i;
    const p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
    switch (((i % 6) + 6) % 6) {
      case 0: return [v, t, p]; case 1: return [q, v, p]; case 2: return [p, v, t];
      case 3: return [p, q, v]; case 4: return [t, p, v]; default: return [v, p, q];
    }
  }
  function darker(c, factor) { const [h, s, v] = rgbToHsv(...rgb(c)); return hex(...hsvToRgb(h, s, v * 100 / factor)); }
  function lighter(c, factor) {
    let [h, s, v] = rgbToHsv(...rgb(c));
    let v2 = v * factor / 100;
    if (v2 > 1) { s = Math.max(0, s - (v2 - 1)); v2 = 1; }
    return hex(...hsvToRgb(h, s, v2));
  }
  function textColor(bg) {
    const [r, g, b] = rgb(bg).map((x) => x * 255);
    return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#1b1b1b" : "#ffffff";
  }
  const catColor = (cat, def = "#2e86c1") => C.CATEGORY_COLORS[cat] ?? def;

  /* --- Geometrie --- */
  class Rect {
    constructor(x, y, w, h) { this.x = x; this.y = y; this.w = w; this.h = h; }
    get right() { return this.x + this.w; }
    get bottom() { return this.y + this.h; }
    adjusted(dx1, dy1, dx2, dy2) { return new Rect(this.x + dx1, this.y + dy1, this.w - dx1 + dx2, this.h - dy1 + dy2); }
    asList() { return [this.x, this.y, this.w, this.h].map((v) => C.pyround(v, 2)); }
  }
  class Geometry {
    constructor(rack) { this.rack = rack; this.top = TITLE_H + FRAME; this.left = FRAME + RAIL_W; }
    yFor(pos, span) { return this.top + (this.rack.height_u - (pos + span - 1)) * U_PX; }
    totalHeight() { return TITLE_H + 2 * FRAME + this.rack.height_u * U_PX + 30; }
  }
  function deviceHeightPx(d) {
    if (d.height_cm > 0) return Math.min(d.height_u * U_PX, d.height_cm * 10 / U_MM * U_PX);
    return d.height_u * U_PX;
  }
  function shelfDeviceRect(geo, shelfRect, d, offset) {
    const w = Math.max(16.0, d.width_mm * SHELF_SCALE);
    const h = deviceHeightPx(d);
    const bottom = shelfRect.bottom - PLATE_H;
    return new Rect(geo.left + 4 + offset * SHELF_SCALE, bottom - h, w - 2, h);
  }
  function depthTooltip(rack, item) {
    const top = rack.topOf(item);
    const side = top.mount_side;
    const d = item.depth_mm;
    const out = [d ? `Montiert ${SIDE_SHORT[side]}, Tiefe ${d} mm` : `Montiert ${SIDE_SHORT[side]}, Tiefe unbekannt`];
    if (item.rails) out.push("Auf Einbauschienen (blockiert die Gegenseite)");
    const span = rack.span(top);
    const facing = rack.facing(top.position, span, side, top.uid);
    if (facing.length) out.push(`${SIDE_LABEL[otherSide(side)]}: ` + facing.map((o) => `${label(o)} (${rack.depthOf(o)} mm)`).join(", "));
    out.push(`Freie Tiefe hier: ${rack.freeDepth(top.position, span, side, top.uid)} mm von ${rack.depth_mm} mm`);
    return out;
  }

  /* --- SVG-Bausteine --- */
  function f(v) {
    let s = C.pyround(Number(v), 2).toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    return s === "-0" || s === "" ? "0" : s;
  }
  const escape = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");

  class Svg {
    constructor() { this.parts = []; }
    add(s) { this.parts.push(s); }
    rect(r, fill = "none", stroke = "none", sw = 1, rx = 0, extra = "") {
      let a = `<rect x="${f(r.x)}" y="${f(r.y)}" width="${f(Math.max(0, r.w))}" height="${f(Math.max(0, r.h))}"`;
      if (rx) a += ` rx="${f(rx)}"`;
      a += ` fill="${fill}"`;
      if (stroke !== "none") a += ` stroke="${stroke}" stroke-width="${f(sw)}"`;
      if (extra) a += " " + extra;
      this.add(a + "/>");
    }
    line(x1, y1, x2, y2, stroke, sw = 1, extra = "") {
      this.add(`<line x1="${f(x1)}" y1="${f(y1)}" x2="${f(x2)}" y2="${f(y2)}" stroke="${stroke}" stroke-width="${f(sw)}"${extra ? " " + extra : ""}/>`);
    }
    /** Text in einem Rechteck (align: left/center/right, valign: center/bottom). */
    text(r, txt, fnt, color, align = "left", valign = "center", extra = "") {
      if (!txt) return;
      let x, anchor;
      if (align === "left") { x = r.x; anchor = "start"; }
      else if (align === "right") { x = r.right; anchor = "end"; }
      else { x = r.x + r.w / 2; anchor = "middle"; }
      const h = fnt.height();
      const y = valign === "bottom" ? r.bottom - fnt.descent : r.y + (r.h - h) / 2 + fnt.ascent;
      const weight = fnt.bold ? ' font-weight="bold"' : "";
      txt = txt.replace(/ {2}/g, "  ");      // Mehrfach-Leerzeichen erhalten (wie Qt)
      this.add(`<text x="${f(x)}" y="${f(y)}" font-size="${fnt.size}"${weight} fill="${color}" text-anchor="${anchor}"${extra ? " " + extra : ""}>${escape(txt)}</text>`);
    }
  }

  const DEFS = `<defs>
<pattern id="pConflict" patternUnits="userSpaceOnUse" width="8" height="8">
<path d="M-2,2 l4,-4 M0,8 l8,-8 M6,10 l4,-4" stroke="#ef5a53" stroke-width="1.2"/></pattern>
<pattern id="pNonRack" patternUnits="userSpaceOnUse" width="8" height="8">
<path d="M-2,6 l4,4 M0,0 l8,8 M6,-2 l4,4" stroke="#ffffff" stroke-opacity="0.28" stroke-width="1"/>
</pattern>
<pattern id="pRails" patternUnits="userSpaceOnUse" width="8" height="8">
<path d="M-2,6 l4,4 M0,0 l8,8 M6,-2 l4,4" stroke="#e8800c" stroke-width="1"/></pattern>
<pattern id="pGhostOther" patternUnits="userSpaceOnUse" width="8" height="8">
<path d="M-2,6 l4,4 M0,0 l8,8 M6,-2 l4,4" stroke="#ffffff" stroke-opacity="0.24" stroke-width="1"/>
</pattern>
<pattern id="pCross" patternUnits="userSpaceOnUse" width="8" height="8">
<path d="M-2,2 l4,-4 M0,8 l8,-8 M6,10 l4,-4 M-2,6 l4,4 M0,0 l8,8 M6,-2 l4,4"
 stroke="#e5413a" stroke-width="1"/></pattern>
</defs>`;

  /* --- Zeichnen --- */
  class Painter {
    constructor(rack, ink, interactive) {
      this.rack = rack; this.ink = ink; this.geo = new Geometry(rack); this.svg = new Svg(); this.interactive = interactive;
    }

    frame(side, sideLabel, footer) {
      const g = this.geo, rack = this.rack, ink = this.ink, s = this.svg;
      const h = rack.height_u * U_PX;
      const ft = font(px(13), true);
      let title = `${rack.name}  (${rack.height_u} HE)`;
      if (sideLabel) title += ` – ${SIDE_LABEL[side]}`;
      s.text(new Rect(-60, 0, RACK_W + 120, 26), ft.elide(title, RACK_W + 120), ft, ink.title, "center", "bottom", 'class="rack-title"');
      if (rack.as_of) s.text(new Rect(0, 27, RACK_W, 18), `Stand: ${fmtDate(rack.as_of)}`, font(px(8.5)), ink.subtitle, "center");
      s.rect(new Rect(0, TITLE_H, RACK_W, h + 2 * FRAME), ink.frame, ink.frame_edge, 1.5, 6);
      s.rect(new Rect(g.left, g.top, INNER_W, h), ink.inner);
      for (const x of [FRAME, FRAME + RAIL_W + INNER_W]) s.rect(new Rect(x, g.top, RAIL_W, h), ink.rail);
      const fn = font(px(7.5));
      const holes = [], lines = [], nums = [];
      for (let i = 0; i < rack.height_u; i++) {
        const u = rack.height_u - i;
        const y = g.top + i * U_PX;
        lines.push(`<line x1="${f(g.left)}" y1="${f(y)}" x2="${f(g.left + INNER_W)}" y2="${f(y)}" stroke="${ink.grid}" stroke-width="0.8"/>`);
        for (const [x1, x2] of [[FRAME, FRAME + RAIL_W], [FRAME + RAIL_W + INNER_W, RACK_W - FRAME]]) {
          lines.push(`<line x1="${f(x1)}" y1="${f(y)}" x2="${f(x2)}" y2="${f(y)}" stroke="${ink.rail_line}" stroke-width="0.8"/>`);
        }
        for (const k of [0.2, 0.5, 0.8]) {
          for (const x of [FRAME + RAIL_W - 7, FRAME + RAIL_W + INNER_W + 4]) holes.push(`M${f(x)},${f(y + U_PX * k - 1.5)}h3v3h-3z`);
        }
        for (const x of [FRAME + 2, FRAME + RAIL_W + INNER_W + 9]) nums.push([new Rect(x, y, RAIL_W - 12, U_PX), String(u)]);
      }
      s.add(lines.join(""));
      s.add(`<path d="${holes.join("")}" fill="${ink.hole}"/>`);
      for (const [r, t] of nums) s.text(r, t, fn, ink.number, "center");
      const fy = TITLE_H + h + 2 * FRAME;
      s.rect(new Rect(10, fy, 26, 8), ink.feet);
      s.rect(new Rect(RACK_W - 36, fy, 26, 8), ink.feet);
      if (footer) s.text(new Rect(-60, fy + 10, RACK_W + 120, 20), footer, font(px(8.5)), ink.title, "center");
    }

    element(it, r, selected, conflict) {
      const s = this.svg;
      const top = this.rack.topOf(it);
      let attrs = "";
      if (this.interactive) {
        const kind = it.shelf_id ? "shelfdev" : (isShelf(it) ? "shelf" : "device");
        attrs = ` class="el" data-uid="${it.uid}" data-top="${top.uid}" data-kind="${kind}" data-rect="${r.asList().map(f).join(",")}"`;
      }
      s.add(`<g${attrs}>`);
      if (this.interactive) {
        const tip = [it.name || it.model];
        if (it.model && it.model !== it.name) tip.push(it.model);
        const ips = allIps(it);
        if (ips.length) tip.push((ips.length === 1 ? "IP: " : "IPs: ") + ips.join(", "));
        tip.push(`${it.category}, ${it.height_u} HE`);
        if (it.power_w) tip.push(`${fmtG(it.power_w)} W`);
        tip.push(...depthTooltip(this.rack, it));
        s.add(`<title>${escape(tip.join("\n"))}</title>`);
      }
      if (isShelf(it)) this.shelf(it, r); else this.device(it, r);
      if (conflict) s.rect(r.adjusted(0.5, 0.5, -0.5, -0.5), "url(#pConflict)", CONFLICT_RED, 2.5, 3, 'stroke-dasharray="7.5 5"');
      if (selected) s.rect(r.adjusted(-1, -1, 1, 1), "none", this.ink.select, 3, 4);
      s.add("</g>");
    }

    shelf(it, r) {
      const s = this.svg, ink = this.ink;
      const plate = new Rect(r.x - EAR_W, r.bottom - PLATE_H, r.w + 2 * EAR_W, PLATE_H);
      if (this.interactive) s.rect(r, "transparent");      // Trefferfläche über die ganze HE
      s.rect(plate, ink.plate, ink.plate_edge, 1);
      let x = plate.x + 40;
      const slots = [];
      while (x < plate.right - 40) { slots.push(`M${f(x)},${f(plate.y + 2)}h10`); x += 18; }
      if (slots.length) s.add(`<path d="${slots.join("")}" stroke="${ink.slot}" stroke-width="1"/>`);
      s.rect(new Rect(plate.x, r.y + 2, 5, r.h - 2), ink.bracket);
      s.rect(new Rect(plate.right - 5, r.y + 2, 5, r.h - 2), ink.bracket);
      if (it.show_name) {
        const ft = font(px(7));
        const tr = r.adjusted(8, 0, -8, -PLATE_H - 1);
        s.text(tr, ft.elide(it.name || "Fachboden", tr.w), ft, ink.shelf_text, "right");
      }
    }

    device(it, r) {
      const s = this.svg;
      const base = catColor(it.category);
      const fg = textColor(base);
      const body = r.adjusted(1, 1, -1, -1);
      if (it.rackmount && !it.shelf_id) {
        const ear = darker(base, 130);
        s.rect(new Rect(body.x - EAR_W, body.y, EAR_W, body.h), ear);
        s.rect(new Rect(body.right, body.y, EAR_W, body.h), ear);
      }
      s.rect(body, base, darker(base, 160), 1, 3);
      if (!it.rackmount && !it.shelf_id) s.rect(body, "url(#pNonRack)", "none", 1, 3);
      s.add(`<circle cx="${f(body.right - 10)}" cy="${f(body.y + 7)}" r="2.2" fill="#7CFC00"/>`);
      const tr = body.adjusted(8, 2, -18, -2);
      const narrow = tr.w < 140;
      const fName = font(px(narrow ? 8 : 9.5), true);
      const fSmall = font(px(narrow ? 7 : 8));
      const name = it.name || it.model || it.category;
      const ips = allIps(it);
      if (ips.length > 1) { this.ipGrid(it, tr, name, ips, fName, fSmall, fg); return; }
      const lines = it.show_name ? [[name, fName]] : [];
      if (ips.length) lines.push([ips[0], fSmall]);
      if (it.model && (it.model !== name || !it.show_name)) lines.push([it.model, fSmall]);
      if (it.height_u === 1 && !narrow && lines.length > 1 && it.show_name) {
        const right = (ips.length ? ips[0] : "") || it.model;
        const rw = Math.min(fSmall.width(right) + 4, tr.w * 0.45);
        s.text(tr, fSmall.elide(right, rw), fSmall, fg, "right");
        s.text(tr, fName.elide(name, tr.w - rw - 8), fName, fg, "left");
        return;
      }
      const heights = lines.map(([, fn]) => fn.height());
      while (lines.length && heights.reduce((a, b) => a + b, 0) > tr.h) { lines.pop(); heights.pop(); }
      let y = tr.y + (tr.h - heights.reduce((a, b) => a + b, 0)) / 2;
      lines.forEach(([txt, fn], i) => {
        s.text(new Rect(tr.x, y, tr.w, heights[i]), fn.elide(txt, tr.w), fn, fg);
        y += heights[i];
      });
    }

    ipGrid(it, rect, name, ips, fName, fSmall, fg) {
      const s = this.svg;
      const heads = it.show_name ? [[name, fName]] : [];
      if (it.model && (it.model !== name || !it.show_name)) heads.push([it.model, fSmall]);
      const gap = 10.0;
      const sum = (a) => a.reduce((x, y) => x + y, 0);
      const drawHeads = (area, hs) => {
        let hh = hs.map(([, fn]) => fn.height());
        while (hs.length && sum(hh) > area.h + 0.5) { hs = hs.slice(0, -1); hh = hh.slice(0, -1); }
        let y = area.y + (area.h - sum(hh)) / 2;
        hs.forEach(([txt, fn], i) => { s.text(new Rect(area.x, y, area.w, hh[i]), fn.elide(txt, area.w), fn, fg); y += hh[i]; });
      };
      const grid = (fm, items, maxRows) => {
        const n = items.length;
        const cols = Math.ceil(n / Math.max(1, Math.min(maxRows, n)));
        const rows = Math.ceil(n / cols);
        const widths = [];
        for (let c = 0; c < cols; c++) widths.push(Math.max(...items.slice(c * rows, (c + 1) * rows).map((a) => fm.width(a))) + gap);
        return [rows, widths, sum(widths) - gap];
      };
      const drawGrid = (x0, y0, rows, widths, fs, items) => {
        const lh = fs.height();
        let x = x0;
        widths.forEach((w, c) => {
          items.slice(c * rows, (c + 1) * rows).forEach((txt, r) => s.text(new Rect(x, y0 + r * lh, w, lh), txt, fs, fg));
          x += w;
        });
      };
      for (let size = fSmall.size; size > 6; size--) {
        const fs = fSmall.withSize(size);
        const lh = fs.height();
        const rowsFit = Math.floor(rect.h / lh);
        if (rowsFit < 1) continue;
        let [rows, widths, gridW] = grid(fs, ips, rowsFit);
        const nameW = rect.w - gridW - 12;
        if (gridW <= rect.w && (!heads.length || nameW >= Math.min(90.0, rect.w * 0.35))) {
          const x0 = heads.length ? rect.right - gridW : rect.x;
          drawGrid(x0, rect.y + (rect.h - rows * lh) / 2, rows, widths, fs, ips);
          if (heads.length) drawHeads(new Rect(rect.x, rect.y, nameW, rect.h), heads);
          return;
        }
        const hs = heads.slice(0, 1);
        const hh = sum(hs.map(([, fn]) => fn.height()));
        const rowsB = Math.floor((rect.h - hh) / lh);
        if (rowsB >= 1) {
          [rows, widths, gridW] = grid(fs, ips, rowsB);
          if (gridW <= rect.w) {
            const y0 = rect.y + (rect.h - hh - rows * lh) / 2;
            if (hs.length) drawHeads(new Rect(rect.x, y0, rect.w, hh), hs);
            drawGrid(rect.x, y0 + hh, rows, widths, fs, ips);
            return;
          }
        }
      }
      // Zu wenig Platz: Name und so viele IPs wie passen, Rest als "+N"
      const fs = fSmall.withSize(7);
      const lh = fs.height();
      const hs = heads.length ? [[heads[0][0], font(7, true)]] : [];
      const hh = hs.length && rect.h >= 2 * lh ? lh : 0.0;
      const rows = Math.max(1, Math.floor((rect.h - hh) / lh));
      let shown = ips.slice();
      while (shown.length > 1) {
        const [, , gw] = grid(fs, shown, rows);
        if (gw <= rect.w) break;
        const rest = ips.length - (shown.length - 1) + 1;
        shown = [...ips.slice(0, shown.length - 2), `+${rest}`];
      }
      const [r_, widths] = grid(fs, shown, rows);
      const y0 = rect.y + (rect.h - hh - r_ * lh) / 2;
      if (hh) drawHeads(new Rect(rect.x, y0, rect.w, hh), hs);
      drawGrid(rect.x, y0 + hh, r_, widths, fs, shown);
    }

    ghost(it, rect, side) {
      const s = this.svg, ink = this.ink, rack = this.rack;
      const span = rack.span(it);
      const free = Math.max(0, rack.depth_mm - rack.depthOf(it));
      const blocked = it.rails;
      const lines = [`${SIDE_LABEL[it.mount_side]}: ${label(it)}`, `HE ${fmtRange(it.position, span)} · Tiefe ${rack.depthOf(it)} mm`];
      lines.push(blocked ? `Einbauschienen: auf der ${SIDE_LABEL[side]} ist hier nichts montierbar.` : `Auf der ${SIDE_LABEL[side]} frei: ${free} mm Tiefe`);
      lines.push("Doppelklick: zur anderen Seite wechseln");
      s.add(`<g class="ghost" data-uid="${it.uid}"><title>${escape(lines.join("\n"))}</title>`);
      const r = rect.adjusted(2, 2, -2, -2);
      const base = catColor(it.category, "#888888");
      s.rect(r, base, ink.ghost, 1.2, 3, 'fill-opacity="0.18" stroke-dasharray="4.8 3.6"');
      if (blocked) s.rect(r, "url(#pRails)", "none", 1, 3);
      const ft = font(px(7));
      const main = `${SIDE_SHORT[it.mount_side]}: ${label(it)} (${rack.depthOf(it)} mm)`;
      const hint = blocked ? "Schienen – hier blockiert" : `frei: ${free} mm`;
      const hintCol = blocked ? UI_ACCENT : ink.ghost;
      const tr = r.adjusted(8, 1, -8, -1);
      const lh = ft.height();
      if (tr.h >= 2 * lh) {
        const cy = tr.y + tr.h / 2;
        s.text(new Rect(tr.x, cy - lh, tr.w, lh), ft.elide(main, tr.w), ft, ink.ghost);
        s.text(new Rect(tr.x, cy, tr.w, lh), hint, ft, hintCol);
      } else {
        const hw = ft.width(hint) + 4;
        s.text(tr, hint, ft, hintCol, "right");
        s.text(new Rect(tr.x, tr.y, tr.w - hw - 6, tr.h), ft.elide(main, tr.w - hw - 6), ft, ink.ghost);
      }
      s.add("</g>");
    }

    profile(side, conflicts) {
      const s = this.svg, ink = this.ink, rack = this.rack, g = this.geo;
      const x0 = RACK_W + PROFILE_GAP;
      const h = rack.height_u * U_PX;
      s.add('<g class="profile"><title>' + escape(`Seitenansicht: Einbautiefe ${rack.depth_mm} mm, links vorne, rechts hinten.\n` +
        "Rote Bereiche: Tiefe reicht nicht oder Einbauschienen blockieren.") + "</title>");
      s.text(new Rect(x0 - 20, 0, PROFILE_W + 40, 26), "Seitenansicht (Tiefe)", font(px(7.5), true), ink.title, "center", "bottom");
      const ft = font(px(7));
      const hr = new Rect(x0, 30, PROFILE_W, 16);
      s.text(hr, "vorne", ft, ink.subtitle, "left");
      s.text(hr, "hinten", ft, ink.subtitle, "right");
      s.text(hr, `${rack.depth_mm} mm`, ft, ink.subtitle, "center");
      s.rect(new Rect(x0, g.top, PROFILE_W, h), ink.profile_bg, ink.frame_edge, 1);
      let gridPath = "";
      for (let i = 1; i < rack.height_u; i++) gridPath += `M${f(x0)},${f(g.top + i * U_PX)}h${f(PROFILE_W)}`;
      if (gridPath) s.add(`<path d="${gridPath}" stroke="${ink.grid}" stroke-width="0.6"/>`);
      const scale = PROFILE_W / Math.max(1, rack.depth_mm);
      const hrect = (sd, depth, top, height) => {
        const w = Math.min(PROFILE_W, depth * scale);
        const x = sd === FRONT ? x0 : x0 + PROFILE_W - w;
        return new Rect(x, top, w, height);
      };
      const box = (it, rect, viewed, bad) => {
        const base = catColor(it.category, "#888888");
        s.rect(rect, base, bad ? CONFLICT_RED : darker(base, 150), bad ? 2 : 0.8, 0, `fill-opacity="${viewed ? 0.9 : 0.51}"`);
        if (!viewed) s.rect(rect, "url(#pGhostOther)");
      };
      const rails = [];
      for (const it of rack.topLevel()) {
        const span = rack.span(it);
        const y = g.yFor(it.position, span);
        const viewed = it.mount_side === side;
        const bad = conflicts.has(it.uid);
        const sd = it.mount_side;
        if (isShelf(it)) {
          const bottom = y + span * U_PX;
          const plate = hrect(sd, Math.max(it.depth_mm, 1), bottom - PLATE_H, PLATE_H - 1);
          const pc = catColor(it.category);
          s.rect(plate, pc, bad ? CONFLICT_RED : darker(pc, 160), bad ? 1.5 : 0.8, 0, `fill-opacity="${viewed ? 1 : 0.59}"`);
          for (const d of rack.onShelf(it.uid)) {
            const dh = deviceHeightPx(d);
            box(d, hrect(sd, d.depth_mm || 1, bottom - PLATE_H - dh, dh), viewed, bad);
          }
        } else {
          const d = it.depth_mm;
          const rect = hrect(sd, d, y + 1.5, span * U_PX - 3);
          if (d > 0) box(it, rect, viewed, bad);
          else {
            const xm = sd === FRONT ? x0 + 1.5 : x0 + PROFILE_W - 1.5;
            s.line(xm, rect.y, xm, rect.bottom, catColor(it.category, "#888888"), 3);
          }
        }
        if (rack.depthOf(it) > rack.depth_mm) {
          const xe = sd === FRONT ? x0 + PROFILE_W : x0;
          s.line(xe, y + 1.5, xe, y + span * U_PX - 1.5, CONFLICT_RED, 3);
        }
        if (it.rails) rails.push([y, span, catColor(it.category, "#888888"), bad]);
      }
      for (const [y, span, base, bad] of rails) {
        const col = bad ? CONFLICT_RED : lighter(base, 130);
        for (const yy of [y + 3, y + span * U_PX - 3]) s.line(x0 + 2, yy, x0 + PROFILE_W - 2, yy, col, 1.6, 'stroke-dasharray="6.4 4.8"');
      }
      for (const c of rack.conflicts()) {
        if (c.kind === "too_deep") continue;
        const y = g.yFor(c.pos, c.span);
        s.rect(new Rect(x0 + 1, y + 1, PROFILE_W - 2, c.span * U_PX - 2), "url(#pCross)", CONFLICT_RED, 1.5);
      }
      s.add("</g>");
    }
  }

  /** SVG des Schranks und Geometrie-Daten für den Browser.
   *  Für Exporte: showOther=false, profile=false, ink="print", interactive=false. */
  function render(rack, { side = FRONT, selected = "", showOther = true, profile = true, sideLabel = true, footer = "",
    ink = "screen", interactive = true, fontFamily = FONT_FAMILY } = {}) {
    const p = new Painter(rack, RACK_INK[ink], interactive);
    const geo = p.geo;
    p.frame(side, sideLabel, footer);
    const bad = showOther || profile ? rack.conflictUids() : new Set();
    if (showOther) {
      for (const it of rack.topLevel(otherSide(side))) {
        const span = rack.span(it);
        p.ghost(it, new Rect(geo.left, geo.yFor(it.position, span), INNER_W, span * U_PX), side);
      }
    }
    for (const it of rack.topLevel(side)) {
      const span = rack.span(it);
      const top = geo.yFor(it.position, span);
      const conflict = bad.has(it.uid);
      if (isShelf(it)) {
        const srect = new Rect(geo.left, top + (span - it.height_u) * U_PX, INNER_W, it.height_u * U_PX);
        p.element(it, srect, it.uid === selected, conflict);
        for (const d of rack.onShelf(it.uid)) p.element(d, shelfDeviceRect(geo, srect, d, Math.max(0, d.offset_mm)), d.uid === selected, conflict);
      } else {
        p.element(it, new Rect(geo.left, top + 1, INNER_W, span * U_PX - 2), it.uid === selected, conflict);
      }
    }
    const width = RACK_W + (profile ? PROFILE_GAP + PROFILE_W : 0);
    const totalH = geo.totalHeight();
    if (profile) p.profile(side, bad);
    let vb;
    if (interactive) vb = [-20.0, -10.0, width + 40, totalH + 20];
    else {
      // Export: Schrank plus Rand; Titel/Fußzeile dürfen breiter sein als der Schrank
      const ft = font(px(13), true);
      const title = `${rack.name}  (${rack.height_u} HE)` + (sideLabel ? ` – ${SIDE_LABEL[side]}` : "");
      const tw = Math.min(RACK_W + 120, ft.width(title));
      const fw = footer ? font(px(8.5)).width(footer) : 0;
      const extra = Math.max(0.0, (Math.max(tw, fw) - RACK_W) / 2 + 4);
      vb = [-6 - extra, -6.0, RACK_W + 12 + 2 * extra, totalH - 12 + (footer ? 22 : 0)];
    }
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb.map(f).join(" ")}" width="${f(vb[2])}" height="${f(vb[3])}" ` +
      `font-family="${escape(fontFamily)}">${DEFS}${p.svg.parts.join("")}</svg>`;
    return [svg, { viewbox: vb, u_px: U_PX, top: geo.top, left: geo.left, inner_w: INNER_W, height_u: rack.height_u,
      shelf_scale: SHELF_SCALE, plate_h: PLATE_H, eps: EPS }];
  }

  return { render, catColor, textColor, darker, lighter, escape, RACK_W };
});
