/* Bearbeitungsschritte und Anzeigedaten der Webversion.
 *
 * ops:  Jeder Schritt bekommt den Schrank, ändert ihn und meldet, was passiert ist. Abläufe wie
 *       in der Desktop-Version (planer2d/mainwindow.py), Regeln aus core.js (= rackcore).
 * view: Alles, was die Oberfläche zur Anzeige braucht: SVG, Banner, Geräteliste, Eigenschaften,
 *       Statuszeile, erlaubte Ziele für Drag & Drop und die Daten der 3D-Ansicht.
 */
(function (root, factory) {
  const isNode = typeof module === "object" && module.exports;
  const api = factory(isNode ? require("./core.js") : root.RackCore, isNode ? require("./render.js") : root.RackRender);
  if (isNode) module.exports = api;
  else root.RackEngine = api;
})(typeof self !== "undefined" ? self : this, function (C, R) {
  "use strict";
  const { CAT_SHELF, CAT_USV, CAT_FIREWALL, CATEGORIES, EPS, FRONT, REAR, MAX_IPS, SHELF_DEPTH_MM, SHELF_WIDTH_MM,
    SIDE_LABEL, SIDE_SHORT, SIDES, U_MM, Rack, makeItem, isShelf, label, allIps, fmtU, fmtRange, snapThird,
    unitsForCm, otherSide, pyround, fmtG, fmtNum, ipIsValid, ipKey, duplicateIps } = C;

  const MAX_HEIGHT_U = 60, MAX_DEPTH_MM = 2000;

  class OpError extends Error {}
  const result = (o = {}) => ({ selected: null, side: null, message: "", ask: null, changed: true, ...o });

  function num(v, def = 0.0, lo = null, hi = null) {
    let x = typeof v === "boolean" ? Number(v) : (v === null || v === undefined || v === "" ? NaN : Number(v));
    if (!Number.isFinite(x)) x = Number.isNaN(x) ? def : x;
    if (Number.isNaN(x)) x = def;
    if (lo !== null) x = Math.max(lo, x);
    if (hi !== null) x = Math.min(hi, x);
    return x;
  }
  const sideOf = (v, def = FRONT) => (SIDES.includes(v) ? v : def);
  function item(rack, uid) {
    const it = rack.get(String(uid || ""));
    if (!it) throw new OpError("Das Gerät gibt es nicht mehr.");
    return it;
  }
  const noSpace = (span) => new OpError(`Im Schrank ist kein zusammenhängender Platz mit ${fmtU(span)} HE frei. ` +
    "Schrank vergrößern oder Geräte verschieben.");

  function itemFromTemplate(t) {
    return makeItem({ name: t.model, model: t.model, category: t.category, height_u: Math.trunc(Number(t.height_u)),
      rackmount: !!t.rackmount, width_mm: Math.trunc(Number(t.width_mm || SHELF_WIDTH_MM)), power_w: Number(t.power_w || 0),
      height_cm: Number(t.height_cm || 0), depth_mm: Math.trunc(Number(t.depth_mm || 0)), rails: !!t.rails });
  }
  function itemFromCustom(a, side, rackDepth) {
    const cat = CATEGORIES.includes(a.category) ? a.category : "Sonstiges";
    const rackmount = a.rackmount === undefined ? true : !!a.rackmount;
    const heightCm = num(a.height_cm, 5.0, 0.5, 250);
    const heightU = rackmount ? Math.trunc(num(a.height_u, 1, 1, 20)) : unitsForCm(heightCm);
    const ips = C.splitIps(String(a.ip ?? ""));
    return makeItem({ name: String(a.name ?? "").trim() || cat, category: cat, height_u: heightU,
      ip: ips.length ? ips[0] : "", ips: ips.slice(1, MAX_IPS), rackmount,
      width_mm: rackmount ? SHELF_WIDTH_MM : Math.trunc(num(a.width_mm, 200, 20, SHELF_WIDTH_MM)),
      height_cm: rackmount ? 0.0 : heightCm, power_w: num(a.power_w, 0, 0, 10000),
      depth_mm: Math.trunc(num(a.depth_mm, Math.min(300, rackDepth), 0, MAX_DEPTH_MM)),
      mount_side: sideOf(a.mount_side, side), rails: !!a.rails && rackmount });
  }
  function shelvesFitting(rack, it, side) {
    const res = [];
    for (const s of rack.topLevel(side).filter(isShelf)) {
      if (rack.shelfGap(s.uid, Math.min(it.width_mm, SHELF_WIDTH_MM)) < 0) continue;
      const newSpan = rack.shelfSpan(s, it);
      if (!rack.nearestFree(s.position, newSpan, s.uid, s.mount_side)) continue;
      res.push(s);
    }
    return res;
  }
  function placeOnShelf(rack, it, shelf) {
    it.shelf_id = shelf.uid; it.position = 0; it.mount_side = shelf.mount_side; it.rails = false;
    if (it.width_mm > SHELF_WIDTH_MM) it.width_mm = SHELF_WIDTH_MM;
    it.offset_mm = Math.max(0, rack.shelfGap(shelf.uid, it.width_mm, it.uid));
    rack.items.push(it);
    if (!rack.isFree(shelf.position, rack.span(shelf), shelf.uid, shelf.mount_side)) {
      shelf.position = rack.nearestFree(shelf.position, rack.span(shelf), shelf.uid, shelf.mount_side);
    }
  }
  function newShelf(rack, side, t = null, extra = null) {
    let depth;
    if (t && t.full_depth) depth = rack.depth_mm;
    else depth = t ? Math.trunc(Number(t.depth_mm || SHELF_DEPTH_MM)) : SHELF_DEPTH_MM;
    const shelf = makeItem({ name: "Fachboden", model: t ? t.model : "", category: CAT_SHELF, height_u: 1, rackmount: true,
      show_name: false, mount_side: side, depth_mm: Math.min(depth, rack.depth_mm), rails: !!(t && t.rails) });
    const span = rack.shelfSpan(shelf, extra);
    const pos = rack.findFree(span, side);
    if (!pos) throw noSpace(span);
    shelf.position = pos;
    rack.items.push(shelf);
    return shelf;
  }
  function addRackmount(rack, it) {
    const pos = rack.findFree(it.height_u, it.mount_side);
    if (!pos) throw noSpace(it.height_u);
    it.position = pos;
    rack.items.push(it);
    return result({ selected: it.uid, side: it.mount_side });
  }
  function addNonRack(rack, it, mode) {
    const shelves = shelvesFitting(rack, it, it.mount_side);
    if (!["new_shelf", "existing_shelf", "none"].includes(mode)) {
      return result({ changed: false, ask: { kind: "shelf", name: it.name, existing: shelves.length > 0 } });
    }
    if (mode === "new_shelf") placeOnShelf(rack, it, newShelf(rack, it.mount_side, null, it));
    else if (mode === "existing_shelf") {
      if (!shelves.length) throw new OpError("Auf keinem Fachboden ist genug Platz frei.");
      placeOnShelf(rack, it, shelves[0]);
    } else {
      const pos = rack.findFree(it.height_u, it.mount_side);
      if (!pos) throw noSpace(it.height_u);
      it.position = pos;
      rack.items.push(it);
    }
    return result({ selected: it.uid, side: it.mount_side });
  }
  function addItem(rack, it, side, mode = null) {
    it.mount_side = side;
    return it.rackmount ? addRackmount(rack, it) : addNonRack(rack, it, mode);
  }

  /* --- Schritte --- */
  function opSetRack(rack, a) {
    const field = a.field, v = a.value;
    if (field === "name") rack.name = String(v ?? "").slice(0, 200);
    else if (field === "height_u") {
      const value = Math.trunc(num(v, rack.height_u, 1, MAX_HEIGHT_U));
      const need = rack.requiredHeight();
      if (value < need) throw new OpError(`Der Schrank kann nicht auf ${value} HE verkleinert werden – es sind Geräte bis HE ${need} eingebaut. ` +
        "Bitte zuerst Geräte verschieben oder entfernen.");
      if (value === rack.height_u) return result({ changed: false });
      rack.height_u = value;
    } else if (field === "depth_mm") {
      const value = Math.trunc(num(v, rack.depth_mm, 100, MAX_DEPTH_MM));
      if (value === rack.depth_mm) return result({ changed: false });
      rack.depth_mm = value;
    } else if (field === "as_of") {
      const iso = C.validIsoDate(v);
      if (!iso) throw new OpError("Ungültiges Datum.");
      if (iso === rack.as_of) return result({ changed: false });
      rack.as_of = iso;
    } else throw new OpError("Unbekannte Eigenschaft.");
    return result();
  }
  function opAddTemplate(rack, a, ui) {
    const t = a.template;
    if (!t || typeof t !== "object" || !("model" in t)) throw new OpError("Bitte zuerst eine Vorlage auswählen.");
    const side = sideOf(ui.side);
    if (t.category === CAT_SHELF) return result({ selected: newShelf(rack, side, t).uid });
    return addItem(rack, itemFromTemplate(t), side, a.mode);
  }
  function opAddCustom(rack, a, ui) {
    const it = itemFromCustom(a.item || {}, sideOf(ui.side), rack.depth_mm);
    return addItem(rack, it, it.mount_side, a.mode);
  }
  function opAddUps(rack) {
    return addItem(rack, makeItem({ name: "USV", model: "USV 2 HE", category: CAT_USV, height_u: 2, power_w: 30, depth_mm: 480, rails: true }), FRONT);
  }
  const opAddShelf = (rack, a, ui) => result({ selected: newShelf(rack, sideOf(ui.side)).uid });
  function opPutOnShelf(rack, a) {
    const it = item(rack, a.uid);
    if (it.rackmount || it.shelf_id) return result({ changed: false });
    rack.items.splice(rack.items.indexOf(it), 1);
    let res;
    try { res = addNonRack(rack, it, a.mode); } catch (e) { rack.items.push(it); throw e; }
    if (res.ask) rack.items.push(it);
    return res;
  }
  function opDelete(rack, a) {
    const it = item(rack, a.uid);
    rack.remove(it.uid);
    return result({ selected: "", message: `„${label(it)}“ entfernt.` });
  }
  const asPos = (p) => (Math.abs(p - Math.round(p)) < EPS ? Math.round(p) : p);
  function opMove(rack, a) {
    const it = item(rack, a.uid);
    const top = rack.topOf(it);
    const pos = snapThird(num(a.pos, top.position));
    if (Math.abs(pos - top.position) < EPS) return result({ changed: false });
    if (!rack.isFree(pos, rack.span(top), top.uid, top.mount_side)) throw new OpError("Dort ist kein Platz frei.");
    top.position = asPos(pos);
    return result();
  }
  function opNudge(rack, a, ui) {
    const it = item(rack, a.uid);
    const top = rack.topOf(it);
    const span = rack.span(top);
    const fine = !!ui.fine;
    const delta = num(a.delta, 1) > 0 ? 1 : -1;
    const step = fine ? delta / 3 : delta;
    let pos = fine ? snapThird(top.position + step) : pyround(top.position + step);
    while (1 - EPS <= pos && pos + span - 1 <= rack.height_u + EPS) {
      if (rack.isFree(pos, span, top.uid, top.mount_side)) { top.position = asPos(pos); return result(); }
      pos = snapThird(pos + step);
    }
    throw new OpError("Kein freier Platz in dieser Richtung.");
  }
  function opMoveOnShelf(rack, a) {
    const dev = item(rack, a.uid);
    const shelf = item(rack, a.shelf);
    if (!isShelf(shelf)) throw new OpError("Das Ziel ist kein Fachboden.");
    const offset = Math.trunc(num(a.offset, 0, 0, SHELF_WIDTH_MM));
    if (!rack.canPlaceOnShelf(dev, shelf, offset)) throw new OpError("Dort ist auf dem Fachboden kein Platz frei.");
    if (dev.shelf_id === shelf.uid && dev.offset_mm === offset) return result({ changed: false });
    dev.shelf_id = shelf.uid; dev.offset_mm = offset; dev.mount_side = shelf.mount_side;
    return result();
  }
  function applyHeight(rack, it, units, heightCm) {
    const top = rack.topOf(it);
    const old = [it.height_u, it.height_cm];
    it.height_u = units; it.height_cm = heightCm;
    const newPos = rack.nearestFree(top.position, rack.span(top), top.uid, top.mount_side);
    if (newPos && it.shelf_id) top.position = newPos;
    else if (newPos !== top.position) {
      [it.height_u, it.height_cm] = old;
      throw new OpError(`Für ${units} HE ist an dieser Position nicht genug Platz.`);
    }
    return result();
  }
  function setSide(rack, it, side) {
    if (it.shelf_id || side === it.mount_side) return result({ changed: false });
    const span = rack.span(it);
    let pos = it.position;
    if (!rack.isFree(pos, span, it.uid, side)) pos = rack.nearestFree(pos, span, it.uid, side);
    if (!pos) throw new OpError(`Auf der ${SIDE_LABEL[side]} ist kein Platz mit ${fmtU(span)} HE frei.`);
    it.mount_side = side; it.position = pos;
    for (const d of rack.onShelf(it.uid)) d.mount_side = side;
    return result({ side, message: `„${label(it)}“ ist jetzt ${SIDE_SHORT[side]} montiert (ab HE ${fmtU(pos)}).` });
  }
  const cleanIp = (v) => String(v ?? "").trim().slice(0, 100);

  function opSetItem(rack, a, ui) {
    const it = item(rack, a.uid);
    const f = a.field, v = a.value;
    if (f === "name") it.name = String(v ?? "").slice(0, 200);
    else if (f === "show_name") it.show_name = !!v;
    else if (f === "ip") it.ip = cleanIp(v);
    else if (f === "ips") it.ips = (Array.isArray(v) ? v : []).map(cleanIp).slice(0, MAX_IPS - 1);
    else if (f === "category") {
      if (isShelf(it) || !CATEGORIES.includes(v)) return result({ changed: false });
      it.category = v;
    } else if (f === "power_w") {
      if (isShelf(it)) return result({ changed: false });
      it.power_w = num(v, it.power_w, 0, 10000);
    } else if (f === "depth_mm") it.depth_mm = Math.trunc(num(v, it.depth_mm, 0, MAX_DEPTH_MM));
    else if (f === "rails") {
      if (it.shelf_id || !(it.rackmount || isShelf(it))) return result({ changed: false });
      it.rails = !!v;
    } else if (f === "height_u") {
      const units = Math.trunc(num(v, it.height_u, 1, Math.max(1, rack.height_u)));
      if (units === it.height_u || (!it.rackmount && !isShelf(it))) return result({ changed: false });
      return applyHeight(rack, it, units, it.height_cm);
    } else if (f === "height_cm") {
      const value = pyround(num(v, it.height_cm, 0.5, 250), 1);
      if (it.rackmount || Math.abs(value - it.height_cm) < 0.05) return result({ changed: false });
      return applyHeight(rack, it, unitsForCm(value), value);
    } else if (f === "position") {
      const top = rack.topOf(it);
      let pos = num(v, top.position, 1, rack.height_u);
      pos = ui.fine ? snapThird(pos) : pyround(pos);
      return opMove(rack, { uid: top.uid, pos }, ui);
    } else if (f === "width_mm") {
      if (!it.shelf_id) return result({ changed: false });
      const value = Math.trunc(num(v, it.width_mm, 20, SHELF_WIDTH_MM));
      let offset = it.offset_mm;
      if (rack.shelfOverlaps(it.shelf_id, offset, value, it.uid)) offset = rack.shelfGap(it.shelf_id, value, it.uid);
      if (offset < 0) throw new OpError(`Auf dem Fachboden ist kein Platz für ${value} mm Breite.`);
      it.width_mm = value; it.offset_mm = offset;
    } else if (f === "offset_mm") {
      if (!it.shelf_id) return result({ changed: false });
      return opMoveOnShelf(rack, { uid: it.uid, shelf: it.shelf_id, offset: v }, ui);
    } else if (f === "mount_side") return setSide(rack, it, sideOf(v, it.mount_side));
    else throw new OpError("Unbekannte Eigenschaft.");
    return result();
  }

  const OPS = { set_rack: opSetRack, add_template: opAddTemplate, add_custom: opAddCustom, add_ups: opAddUps,
    add_shelf: opAddShelf, put_on_shelf: opPutOnShelf, delete: opDelete, move: opMove, nudge: opNudge,
    move_on_shelf: opMoveOnShelf, set_item: opSetItem };
  function apply(rack, op, args, ui) {
    const fn = OPS[op];
    if (!fn) throw new OpError(`Unbekannter Schritt „${op}“.`);
    return fn(rack, args || {}, ui || {});
  }

  /* ===================================================================================== */
  /* Anzeigedaten                                                                           */
  /* ===================================================================================== */
  const SHELF_HE_COLOR = "#95a5a6";
  const unique = (arr) => [...new Set(arr)];

  function bannerUps(missing) {
    if (!missing.length) return "";
    const parts = missing.map((m) => (m === CAT_FIREWALL ? "eine Firewall" : `ein ${m}`));
    const what = parts.length === 1 ? parts[0] : parts.slice(0, -1).join(", ") + " und " + parts[parts.length - 1];
    return `Im Schrank befindet sich ${what}, aber keine USV. Eine unterbrechungsfreie Stromversorgung schützt vor ` +
      "Datenverlust bei Stromausfall und ermöglicht ein sauberes Herunterfahren.";
  }
  function bannerDups(dups) {
    const out = [];
    for (const [ip, devs] of dups) {
      const names = unique(devs.map(label));
      out.push({ ip, who: names.length > 1 ? names.join(", ") : `${names[0]} (mehrfach eingetragen)` });
    }
    return out;
  }
  function bannerRails(rack, side) {
    const rails = rack.topLevel(otherSide(side)).filter((i) => i.rails);
    if (!rails.length) return null;
    const parts = rails.slice(0, 4).map((i) => `„${label(i)}“ (HE ${fmtRange(i.position, rack.span(i))})`);
    const more = rails.length > 4 ? ` und ${rails.length - 4} weitere` : "";
    const verb = rails.length === 1 ? "sitzt" : "sitzen";
    return { key: side + "|" + rails.map((i) => i.uid).sort().join(","),
      text: `${parts.join(", ")}${more} ${verb} auf der ${SIDE_LABEL[otherSide(side)]} auf Schienen. Diese HE sind auf der ` +
        `${SIDE_LABEL[side]} blockiert (orange schraffiert) – große Geräte wie USV, Server und Rack-NAS werden meist mit Schienen montiert.` };
  }
  function ipState(rack, it, text, dups) {
    text = String(text).trim();
    if (!text) return { state: "", tip: "" };
    if (!ipIsValid(text)) return { state: "bad", tip: "Keine gültige IP-Adresse" };
    const devs = dups.get(ipKey(text));
    if (devs) {
      const others = unique(devs.filter((d) => d.uid !== it.uid).map((d) => d.name || d.model));
      return { state: "dup", tip: others.length ? "Doppelt: auch bei " + others.join(", ") : "Doppelt: an diesem Gerät mehrfach eingetragen" };
    }
    return { state: "", tip: "" };
  }
  function listRows(rack, side, conflictUids, conflicts, dups) {
    const rows = [];
    const row = (it, level) => {
      let where, whereTip;
      if (it.shelf_id) { where = ""; whereTip = "steht auf dem Fachboden"; }
      else { where = fmtRange(it.position, rack.span(it)); whereTip = `HE ${where}`; }
      const ips = allIps(it);
      const ipText = ips.length ? ips[0] + (ips.length > 1 ? ` +${ips.length - 1}` : "") : "";
      const sd = rack.sideOf(it);
      let nameTip = it.name || it.model;
      if (it.model && it.model !== it.name) nameTip += `\n${it.model}`;
      const top = rack.topOf(it);
      const conflict = conflictUids.has(top.uid);
      if (conflict) nameTip += "\n\nTiefenkonflikt:\n" + conflicts.filter((c) => c.uids.includes(top.uid)).map((c) => c.text).join("\n");
      let ipTip = "", ipBad = false;
      if (ips.length) {
        const dup = ips.filter((a) => dups.has(ipKey(a)));
        const bad = ips.filter((a) => !ipIsValid(a));
        ipTip = ips.join("\n");
        if (dup.length) ipTip += "\n\nDoppelt vergeben: " + dup.join(", ");
        if (bad.length) ipTip += "\n\nUngültig: " + bad.join(", ");
        ipBad = !!(dup.length || bad.length);
      }
      rows.push({ uid: it.uid, level, name: it.name || it.model, name_tip: nameTip, where, where_tip: whereTip,
        side: it.shelf_id ? "" : SIDE_SHORT[sd], mount_side: sd, ip: ipText, ip_tip: ipTip, ip_bad: ipBad,
        power: it.power_w && !isShelf(it) ? fmtG(it.power_w) : "", color: R.catColor(it.category, "#888888"),
        muted: sd !== side, conflict });
    };
    const tops = rack.topLevel().slice().sort((a, b) => b.position - a.position);
    for (const it of tops) { row(it, 0); for (const d of rack.onShelf(it.uid)) row(d, 1); }
    return rows;
  }
  function depthInfo(rack, it) {
    const top = rack.topOf(it);
    const side = top.mount_side, span = rack.span(top);
    const free = rack.freeDepth(top.position, span, side, top.uid);
    const need = rack.depthOf(top);
    const blockers = rack.railBlockers(top.position, span, side, top.uid);
    const facing = rack.facing(top.position, span, side, top.uid);
    const other = SIDE_SHORT[otherSide(side)];
    if (blockers.length) return { bad: true, text: `Blockiert: „${label(blockers[0])}“ (${other}) sitzt auf Einbauschienen.` };
    if (top.rails && facing.length) return { bad: true, text: `Die Schienen blockieren „${label(facing[0])}“ (${other}).` };
    if (need > free) return { bad: true, text: `Zu tief: ${need} mm benötigt, hier sind nur ${free} mm frei.` };
    let txt = `Hier frei: ${free} von ${rack.depth_mm} mm`;
    if (facing.length) txt += ` (${other}: ` + facing.map((o) => `${label(o)} ${rack.depthOf(o)} mm`).join(", ") + ")";
    if (need) txt += ` · Reserve ${free - need} mm`;
    return { bad: false, text: txt };
  }
  function props(rack, it, dups) {
    const shelf = isShelf(it);
    const top = rack.topOf(it);
    const nonRack = !shelf && !it.rackmount;
    let mount;
    if (shelf) mount = `Fachboden mit ${rack.onShelf(it.uid).length} Gerät(en)`;
    else if (it.shelf_id) mount = "steht auf einem Fachboden (Position = Fachboden)";
    else if (it.rackmount) mount = "19\"-Rackmontage";
    else mount = "nicht rackfähig – ohne Fachboden eingesetzt";
    return {
      uid: it.uid, name: it.name, show_name: it.show_name, model: it.model || "–", category: it.category,
      is_shelf: shelf, on_shelf: !!it.shelf_id, rackmount: it.rackmount, non_rack: nonRack,
      height_u: it.height_u, height_cm: pyround(nonRack ? it.height_cm : it.height_u * U_MM / 10, 1),
      position: pyround(top.position, 4), position_text: fmtU(top.position),
      width_mm: it.width_mm, offset_mm: it.shelf_id ? Math.max(0, it.offset_mm) : 0,
      power_w: it.power_w, mount_side: rack.sideOf(it), depth_mm: it.depth_mm,
      rails: it.rails, rails_enabled: !it.shelf_id && (it.rackmount || shelf),
      ip: it.ip, ips: it.ips.slice(), ip_state: ipState(rack, it, it.ip, dups),
      ips_state: it.ips.map((a) => ipState(rack, it, a, dups)),
      mount_text: mount, mount_warn: nonRack && !it.shelf_id, can_put_on_shelf: nonRack && !it.shelf_id,
      shelf_devices: shelf ? rack.onShelf(it.uid).length : 0, depth_info: depthInfo(rack, it), label: label(it),
    };
  }
  /** Erlaubte Positionen je Element (in Dritteln einer HE) und erlaubte Abstände (5-mm-Raster)
   *  für Geräte auf Fachböden – für die grün/rot-Vorschau beim Ziehen. */
  function moveTargets(rack) {
    const tops = {};
    for (const it of rack.topLevel()) {
      const span = rack.span(it);
      const ok = [];
      const last = pyround(3 * (rack.height_u - span + 1));
      for (let k = 3; k <= last; k++) if (rack.isFree(k / 3, span, it.uid, it.mount_side)) ok.push(k);
      tops[it.uid] = { span, pos: it.position, side: it.mount_side, ok, shelf: isShelf(it), height_u: it.height_u };
    }
    const devs = {};
    const shelves = rack.topLevel().filter(isShelf);
    for (const d of rack.items.filter((i) => i.shelf_id)) {
      const targets = {};
      for (const s of shelves) {
        const ok = [];
        for (let off = 0; off <= SHELF_WIDTH_MM - d.width_mm; off += 5) if (rack.canPlaceOnShelf(d, s, off)) ok.push(off);
        targets[s.uid] = ok;
      }
      devs[d.uid] = { width_mm: d.width_mm, height_u: d.height_u, height_cm: d.height_cm, targets };
    }
    return { tops, devs };
  }
  function scene3d(rack, conflictUids) {
    const labels = (it) => [it.show_name ? label(it) : "", ...allIps(it)];
    const dev = (it, defColor) => {
      const col = R.catColor(it.category, defColor);
      return { uid: it.uid, color: col, fg: R.textColor(col), lines: labels(it), depth: it.depth_mm, width: it.width_mm,
        height_u: it.height_u, height_cm: it.height_cm, rackmount: it.rackmount, rails: it.rails };
    };
    const items = [];
    for (const it of rack.topLevel()) {
      const d = dev(it, isShelf(it) ? SHELF_HE_COLOR : "#2e86c1");
      Object.assign(d, { side: it.mount_side, pos: it.position, span: rack.span(it), shelf: isShelf(it),
        conflict: conflictUids.has(it.uid), depth: it.depth_mm });
      if (isShelf(it)) {
        d.devices = rack.onShelf(it.uid).map((x) => Object.assign(dev(x, "#2e86c1"), { offset: Math.max(0, x.offset_mm), load_u: Rack.loadU(x) }));
      }
      items.push(d);
    }
    return { height_u: rack.height_u, depth_mm: rack.depth_mm, name: rack.name, as_of: rack.as_of, shelf_width_mm: SHELF_WIDTH_MM, items };
  }
  function buildView(rack, ui) {
    const side = [FRONT, REAR].includes(ui.side) ? ui.side : FRONT;
    let selected = String(ui.selected || "");
    if (!rack.get(selected)) selected = "";
    const readOnly = !!ui.read_only;
    const showOther = ui.show_other !== false;
    const showProfile = ui.show_profile !== false;
    const conflicts = rack.conflicts();
    const conflictUids = new Set(conflicts.flatMap((c) => c.uids));
    const dups = duplicateIps(rack);
    const [svg, geo] = R.render(rack, { side, selected: readOnly ? "" : selected, showOther, profile: showProfile });
    const power = rack.totalPower();
    const status = `${SIDE_LABEL[side]}   |   Belegt vorne ${fmtU(rack.usedU(FRONT))} HE, hinten ${fmtU(rack.usedU(REAR))} HE von ` +
      `${rack.height_u} HE   |   Tiefe ${fmtNum(rack.depth_mm)} mm   |   Leistung: ${fmtNum(power)} W   |   Wärmelast: ` +
      `${fmtNum(power)} W ≈ ${fmtNum(power * 3.412)} BTU/h`;
    const sel = rack.get(selected);
    const view = {
      svg, geo, side, selected, status,
      banners: { ups: bannerUps(rack.missingUps()), dups: bannerDups(dups),
        conflicts: conflicts.map((c) => ({ text: c.text, uid: c.uids[c.uids.length - 1] })), rails: bannerRails(rack, side) },
      list: listRows(rack, side, conflictUids, conflicts, dups),
      props: sel ? props(rack, sel, dups) : null,
      sides_used: unique(rack.topLevel().map((i) => i.mount_side)).sort(),
      required_height: rack.requiredHeight(),
      devices: rack.items.filter((i) => i.category !== CAT_SHELF).length,
      power_summary: rack.powerSummary(),
      scene3d: scene3d(rack, conflictUids),
    };
    if (!readOnly) view.targets = moveTargets(rack);
    return view;
  }

  /** Wie POST /api/state der früheren Python-Version: optional einen Schritt ausführen, dann die Ansicht liefern. */
  function state(body) {
    const original = body.rack;
    if (!original || typeof original !== "object") throw new Error("Kein Schrank übergeben.");
    let rack = Rack.fromDict(C.clone(original));
    const ui = { ...(body.ui && typeof body.ui === "object" ? body.ui : {}) };
    const out = { ok: true, changed: false };
    if (body.op) {
      try {
        const res = apply(rack, String(body.op), body.args || {}, ui);
        out.changed = res.changed && !res.ask;
        if (res.ask) out.ask = res.ask;
        if (res.message) out.message = res.message;
        if (res.selected !== null) ui.selected = res.selected;
        if (res.side !== null) ui.side = res.side;
      } catch (e) {
        if (!(e instanceof OpError)) throw e;
        rack = Rack.fromDict(C.clone(original));
        out.ok = false; out.error = e.message;
      }
    }
    out.rack = rack.toDict();
    out.view = buildView(rack, ui);
    return out;
  }

  return { OpError, apply, state, buildView, itemFromTemplate, OPS };
});
