/* Rack-Planer Web – Oberfläche im Browser.
 *
 * Der Browser hält den Schrank, an dem gearbeitet wird. Jeder Bearbeitungsschritt geht an
 * /api/state – das beantwortet local-api.js direkt im Browser mit dem Rechenkern (core.js,
 * engine.js: gleiche Regeln wie rackcore der Desktop-Version) und liefert den neuen Schrank,
 * die Zeichnung (SVG) und alle Anzeigedaten zurück. Die Oberfläche selbst rechnet nichts aus –
 * auch die grün/rot-Vorschau beim Ziehen beruht auf Listen erlaubter Positionen.
 * Gespeichert wird auf dem Server (api.php): Schränke, eigene Vorlagen, Update.
 *
 * Ansichten: Vorderseite und Rückseite (SVG) sowie die frei drehbare 3D-Ansicht
 * (view3d.js, zeichnet im Browser aus view.scene3d).
 */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false)
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return el;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SIDE_LABEL = { front: "Vorderseite", rear: "Rückseite" };
const OTHER = { front: "rear", rear: "front" };
const UNDO_LIMIT = 200;
const U_MM = 44.45;

function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${m[3]}.${m[2]}.${m[1]}` : (iso || "");
}
function fmtDateTime(iso) {
  const [d, t] = String(iso || "").replace("T", " ").slice(0, 16).split(" ");
  return d ? `${fmtDate(d)} ${t || ""}`.trim() : "";
}
const rackKeys = ["name", "height_u", "depth_mm", "as_of", "items"];
function rackOf(doc) { const r = {}; for (const k of rackKeys) r[k] = doc[k]; return r; }
const canon = (rack) => JSON.stringify(rack);

/* ------------------------------------------------------------------------------------ */
/* Zustand                                                                                */
/* ------------------------------------------------------------------------------------ */
const S = {
  meta: null, templates: [],
  doc: null,            // {id, revision, created, saved_at, history: [...], history_enabled, history_declined}
  rack: null,           // aktueller Schrank (wie Rack.to_dict)
  savedState: "",       // Schrank beim letzten Speichern/Laden (für „ungespeichert“)
  ui: { side: "front", selected: "", show_other: true, show_profile: true, fine: false },
  mode3d: false,        // 3D-Ansicht statt Vorder-/Rückseite
  v3d: null,            // 3D-Ansicht (view3d.js)
  view: null,
  undo: [], redo: [], merge: null,
  preview: null,        // Index des angezeigten Historien-Stands
  previewView: null,
  historyOffered: false,
  railDismissed: new Set(),
  zoom: 1, autoFit: true,
  tplSel: null, tplCollapsed: new Set(),
  extraIpRows: 0, extraIpUid: "",
  tab: "list",
  bannersCollapsed: false,
};
const dirty = () => S.rack && canon(S.rack) !== S.savedState;
/** Speichert der Server Schränke? (einstellungen.ini: server_speichern) – sonst „Datei-Modus“. */
const serverSave = () => S.meta?.server_save !== false;
/** Wurde der Schrank schon gespeichert (auf dem Server oder als Datei)? */
const persisted = () => !!(S.doc?.id || S.doc?.fileSaved);

/* ------------------------------------------------------------------------------------ */
/* Server                                                                                 */
/* ------------------------------------------------------------------------------------ */
async function api(method, url, body) {
  let res;
  try { res = await RackLocal.handle(method, url, body); } catch (e) { throw new Error(e.message || "Der Server ist nicht erreichbar."); }
  if (res.status === 409) { const j = await res.json(); const err = new Error(j.detail); err.conflict = j; throw err; }
  if (!res.ok) {
    let msg = `Fehler ${res.status}`;
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) { /* */ }
    throw new Error(msg);
  }
  return res;
}
const getJSON = async (url) => (await api("GET", url)).json();
const sendJSON = async (method, url, body) => (await api(method, url, body)).json();

async function download(method, url, body, fallbackName) {
  const res = await api(method, url, body);
  const blob = await res.blob();
  let name = fallbackName;
  const cd = res.headers.get("Content-Disposition") || "";
  const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
  if (m) name = decodeURIComponent(m[1]);
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 30000);
  return name;
}

// Schritte strikt nacheinander ausführen (jeder baut auf dem Ergebnis des vorigen auf)
let queue = Promise.resolve();
function enqueue(fn) {
  const p = queue.then(fn, fn);
  queue = p.catch(() => {});
  return p;
}

/** Bearbeitungsschritt ausführen. merge: gleichartige Schritte (Tippen) zu einem Undo-Schritt. */
function op(name, args = {}, opts = {}) {
  return enqueue(async () => {
    if (S.preview !== null) return { ok: false };
    const before = canon(S.rack);
    let r;
    for (;;) {
      try {
        r = await sendJSON("POST", "/api/state", { rack: S.rack, op: name, args, ui: uiPayload() });
      } catch (e) { await alertBox(e.message); return { ok: false }; }
      if (!r.ask) break;
      const mode = await askShelf(r.ask);      // Rückfrage (z. B. Fachboden) – dann erneut
      if (!mode) { applyView(r.view); return r; }
      args = { ...args, mode };
    }
    if (!r.ok) {
      applyView(r.view, { force: true });
      if (opts.quiet) status(r.error); else await alertBox(r.error);
      return r;
    }
    if (r.changed) pushUndo(before, opts.merge);
    S.rack = r.rack;
    applyView(r.view);
    if (r.message) status(r.message);
    if (r.changed) afterChange();
    return r;
  });
}

function uiPayload(extra = {}) {
  return { side: S.ui.side, selected: S.ui.selected, show_other: S.ui.show_other, show_profile: S.ui.show_profile, fine: S.ui.fine, ...extra };
}

/** Nur neu anzeigen (Auswahl, Seite, Ansicht geändert). */
function refresh() {
  return enqueue(async () => {
    if (S.preview !== null) return showPreview(S.preview);
    try {
      const r = await sendJSON("POST", "/api/state", { rack: S.rack, ui: uiPayload() });
      S.rack = r.rack;
      applyView(r.view);
    } catch (e) { status(e.message); }
  });
}

function pushUndo(before, merge) {
  const now = Date.now();
  if (merge && S.merge && S.merge.key === merge && now - S.merge.time < 4000) {
    S.merge.time = now;            // gleicher Schritt (z. B. weiter getippt): kein neuer Eintrag
  } else {
    S.undo.push(before);
    if (S.undo.length > UNDO_LIMIT) S.undo.shift();
    S.merge = merge ? { key: merge, time: now } : null;
  }
  S.redo = [];
}

function undo() {
  if (!S.undo.length || S.preview !== null) return;
  S.redo.push(canon(S.rack));
  S.rack = JSON.parse(S.undo.pop());
  S.merge = null;
  refresh().then(updateChrome);
}
function redo() {
  if (!S.redo.length || S.preview !== null) return;
  S.undo.push(canon(S.rack));
  S.rack = JSON.parse(S.redo.pop());
  S.merge = null;
  refresh().then(updateChrome);
}

function afterChange() {
  updateChrome();
  maybeOfferHistory();
}

/* ------------------------------------------------------------------------------------ */
/* Anzeige                                                                                */
/* ------------------------------------------------------------------------------------ */
function applyView(v, { force = false } = {}) {
  S.view = v;
  S.ui.side = v.side;
  S.ui.selected = v.selected;
  renderSvg(v);
  renderBanners();
  renderList(v.list);
  renderRackBox(force);
  renderProps(v.props, force);
  $("#status").textContent = v.status;
  updateChrome();
  if (S.tab === "history") renderHistory();
}

function renderSvg(v) {
  const box = $("#rackview");
  box.innerHTML = v.svg;
  $("#loading").hidden = true;
  applyZoom();
  if (S.v3d) S.v3d.update(v, { readOnly: S.preview !== null });
}

/* --- 3D-Ansicht ---------------------------------------------------------------------- */
function init3d() {
  S.v3d = View3D.create($("#view3d"), {
    select: (uid) => select(uid),
    move: (uid, pos) => op("move", { uid, pos }, { quiet: true }),
    shelfMove: (uid, shelf, offset) => op("move_on_shelf", { uid, shelf, offset }, { quiet: true }),
    side: (side) => {          // Kamera schaut jetzt auf die andere Seite: neue Geräte kommen dorthin
      if (!S.mode3d || side === S.ui.side) return;
      S.ui.side = side;
      status(`Blick auf die ${SIDE_LABEL[side]} – neue Geräte werden ${side === "front" ? "vorne" : "hinten"} montiert.`, 4000);
      refresh();
    },
    fine: () => S.ui.fine,
  });
}
function setMode3d(on) {
  const first = on && !S.mode3d && !S.v3dShown;
  S.mode3d = on;
  $("#view3d").hidden = !on;
  $("#rackview").hidden = on;
  $("#viewwrap").classList.toggle("mode3d", on);
  $("#banners").classList.toggle("in3d", on);   // in 3D unter der 3D-Leiste
  if (on) {
    S.v3dShown = true;
    const v = S.previewView || S.view;
    if (v) S.v3d.update(v, { readOnly: S.preview !== null });
    if (first) { S.v3d.fit(false); S.v3d.showSide(S.ui.side, false); }
    S.v3d.draw();
    S.v3d.focus();
  }
  updateChrome();
}
async function export3d() {
  if (!S.mode3d) setMode3d(true);
  const r = S.rack;
  const blob = await S.v3d.toPng(r.name, `Stand: ${fmtDate(r.as_of)}   ·   ${S.view.power_summary}`);
  const a = h("a", { href: URL.createObjectURL(blob), download: `${r.name} 3D.png` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  status(`Bild exportiert: ${r.name} 3D.png`);
}

function applyZoom() {
  if (S.mode3d && S.v3d) return;
  const svg = $("#rackview svg");
  const v = S.previewView || S.view;
  if (!svg || !v) return;
  const [, , w, hh] = v.geo.viewbox;
  if (S.autoFit) {
    const wrap = $("#viewwrap");
    const s = Math.min((wrap.clientHeight - 8) / hh, (wrap.clientWidth - 8) / w);
    S.zoom = Math.max(0.35, Math.min(s, 1.6));
  }
  svg.setAttribute("width", Math.round(w * S.zoom));
  svg.setAttribute("height", Math.round(hh * S.zoom));
}
function zoomBy(f) { if (S.mode3d) return S.v3d.zoom(f); S.autoFit = false; S.zoom = Math.max(0.25, Math.min(S.zoom * f, 4)); applyZoom(); }
function fit() { if (S.mode3d) return S.v3d.fit(); S.autoFit = true; applyZoom(); }

// Symbole als Inline-SVG (keine Schriftzeichen – auf manchen Systemen löst ⓘ/⚠/🕘 eine langsame Schriftsuche aus)
const ICONS = {
  info: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="9" y="8.4" width="2" height="6.2" rx="1" fill="currentColor"/><circle cx="10" cy="5.9" r="1.25" fill="currentColor"/></svg>',
  warn: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.2 L18.6 17.2 H1.4 Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><rect x="9" y="7.4" width="2" height="5.4" rx="1" fill="currentColor"/><circle cx="10" cy="14.9" r="1.2" fill="currentColor"/></svg>',
  history: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M10 5.2 V10.4 L13.4 12.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};
function banner(cls, icon, html, buttons = []) {
  const b = h("div", { class: `banner ${cls}` }, h("span", { class: "ic", html: ICONS[icon] || "" }), h("div", { class: "tx", html }));
  for (const [label, fn, kind] of buttons) b.append(h("button", { class: `btn ${kind || "fill"}`, onclick: fn, text: label }));
  return b;
}

function renderBanners() {
  const box = $("#banners");
  box.innerHTML = "";
  const list = [];
  if (S.preview !== null) {
    const snap = S.doc.history[S.preview];
    list.push(banner("", "history", `<b>Historie:</b> Du siehst den Stand vom ${esc(fmtDate(snap.as_of))}` +
      (snap.saved_at ? `, gespeichert am ${esc(fmtDateTime(snap.saved_at))}` : "") +
      " – nur zum Ansehen. Bearbeitet wird weiterhin der aktuelle Stand.",
      [["Wiederherstellen", restorePreview], ["Zurück zum aktuellen Stand", endPreview, "plain"]]));
  } else {
    const b = S.view.banners;
    if (b.conflicts.length) {
      const n = b.conflicts.length;
      const lines = b.conflicts.slice(0, 4).map((c) => esc(c.text));
      if (n > 4) lines.push(`… und ${n - 4} weitere (rot markiert)`);
      list.push(banner("red", "warn", `<b>${n === 1 ? "Tiefenkonflikt" : n + " Tiefenkonflikte"}:</b><br>${lines.join("<br>")}`,
        [["Zeigen", () => showItem(b.conflicts[0].uid)]]));
    }
    if (b.dups.length) {
      const parts = b.dups.map((d) => `<b>${esc(d.ip)}</b>: ${esc(d.who)}`);
      list.push(banner("err", "warn", `<b>${b.dups.length === 1 ? "Doppelte IP-Adresse" : "Doppelte IP-Adressen"}:</b> ${parts.join("; ")}`));
    }
    if (b.ups) list.push(banner("", "info", `<b>Hinweis:</b> ${esc(b.ups)}`, [["USV hinzufügen", () => op("add_ups")]]));
    if (b.rails && !S.railDismissed.has(b.rails.key)) {
      const key = b.rails.key;
      list.push(banner("", "info", `<b>Einbauschienen:</b> ${esc(b.rails.text)}`,
        [["Ausblenden", () => { S.railDismissed.add(key); renderBanners(); }, "plain"]]));
    }
  }
  if (!list.length) return;
  // Kopfzeile zum Ein-/Ausklappen: Die Hinweise liegen über der Zeichnung und lassen sich wegklappen
  const worst = list.some((x) => x.classList.contains("red")) ? "red" : list.some((x) => x.classList.contains("err")) ? "err" : "";
  const n = list.length;
  const head = h("button", { class: `bn-head ${worst}`, title: S.bannersCollapsed ? "Hinweise anzeigen" : "Hinweise einklappen" },
    h("span", { class: "ic", html: ICONS[S.preview !== null ? "history" : worst ? "warn" : "info"] }),
    `${n} ${n === 1 ? "Hinweis" : "Hinweise"} ${S.bannersCollapsed ? "▸ anzeigen" : "▾ einklappen"}`);
  head.addEventListener("click", () => { S.bannersCollapsed = !S.bannersCollapsed; renderBanners(); });
  box.classList.toggle("collapsed", !!S.bannersCollapsed);
  box.append(head, ...list);
}

function renderList(rows) {
  const tb = $("#devlist");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = h("tr", { class: [r.uid === S.ui.selected ? "sel" : "", r.muted ? "muted" : ""].join(" "), "data-uid": r.uid },
      h("td", { title: r.name_tip, class: r.conflict ? "c" : "", style: r.level ? "padding-left:22px" : "" },
        h("span", { class: "sw", style: `background:${r.color}` }), r.name),
      h("td", { title: r.where_tip, text: r.where }),
      h("td", { text: r.side }),
      h("td", { title: r.ip_tip, class: r.ip_bad ? "ipbad" : "", text: r.ip }),
      h("td", { class: "num", text: r.power }));
    tr.addEventListener("click", () => selectFromList(r.uid, r.mount_side));
    tb.append(tr);
  }
  const sel = tb.querySelector("tr.sel");
  if (sel) sel.scrollIntoView({ block: "nearest" });
}

function setVal(el, value, force) {
  if (document.activeElement === el && !force) return;
  if (el.type === "checkbox") el.checked = !!value;
  else if (String(el.value) !== String(value ?? "")) el.value = value ?? "";
}

function renderRackBox(force) {
  const r = S.rack;
  setVal($("#r-name"), r.name, force);
  setVal($("#r-height"), r.height_u, force);
  setVal($("#r-depth"), r.depth_mm, force);
  setVal($("#r-asof"), r.as_of, force);
}

function ipClass(el, st) {
  el.classList.toggle("bad", st.state === "bad");
  el.classList.toggle("dup", st.state === "dup");
  el.title = st.tip || "";
}

function renderProps(p, force) {
  const box = $("#props");
  const enabled = !!p && S.preview === null;
  box.classList.toggle("disabled", !enabled);
  if (!p) {
    for (const id of ["p-name", "p-ip"]) setVal($("#" + id), "", true);
    $("#p-model").textContent = "–";
    $("#p-mount").textContent = "";
    $("#p-depth-info").textContent = "";
    $("#p-shelf-btn").hidden = true;
    renderExtraIps(null);
    return;
  }
  if (S.extraIpUid !== p.uid) { S.extraIpUid = p.uid; S.extraIpRows = 0; }
  setVal($("#p-name"), p.name, force);
  setVal($("#p-show-name"), p.show_name, force);
  setVal($("#p-ip"), p.ip, force);
  ipClass($("#p-ip"), p.ip_state);
  $("#p-ip").disabled = p.is_shelf;
  renderExtraIps(p, force);
  $("#p-model").textContent = p.model;
  const cat = $("#p-cat");
  cat.disabled = p.is_shelf;
  if (!p.is_shelf) setVal(cat, p.category, force); else cat.value = "";
  const ht = $("#p-height");
  ht.max = Math.max(1, S.rack.height_u);
  setVal(ht, p.height_u, force);
  ht.disabled = p.non_rack;
  const hc = $("#p-height-cm");
  setVal(hc, p.height_cm, force);
  hc.disabled = !p.non_rack;
  const pos = $("#p-pos");
  pos.max = Math.max(1, S.rack.height_u);
  pos.step = S.ui.fine ? "0.01" : "1";
  setVal(pos, Number(p.position.toFixed(2)), force);
  const w = $("#p-width");
  setVal(w, p.width_mm, force);
  w.disabled = !p.on_shelf;
  const off = $("#p-offset");
  setVal(off, p.offset_mm, force);
  off.disabled = !p.on_shelf;
  const pw = $("#p-power");
  setVal(pw, p.power_w, force);
  pw.disabled = p.is_shelf;
  const sd = $("#p-side");
  setVal(sd, p.mount_side, force);
  sd.disabled = p.on_shelf;
  sd.title = p.on_shelf ? "Geräte auf einem Fachboden: Seite des Fachbodens" : "Seite, an der das Gerät montiert ist. Von dort aus belegt es seine Tiefe.";
  setVal($("#p-depth"), p.depth_mm, force);
  const rails = $("#p-rails");
  setVal(rails, p.rails, force);
  rails.disabled = !p.rails_enabled;
  const di = $("#p-depth-info");
  di.textContent = p.depth_info.text;
  di.className = "small-text " + (p.depth_info.bad ? "bad-text" : "hint");
  const mt = $("#p-mount");
  mt.textContent = p.mount_text;
  mt.className = p.mount_warn ? "warn-text" : "";
  $("#p-shelf-btn").hidden = !p.can_put_on_shelf;
  $("#p-save-tpl").disabled = p.is_shelf || !serverSave();
  $("#p-save-tpl").title = serverSave() ? "" : "Eigene Vorlagen brauchen das Speichern auf dem Server (in einstellungen.ini abgeschaltet).";
}

function renderExtraIps(p, force) {
  const box = $("#p-ips");
  $$(".iprow, .ipadd", box).forEach((e) => e.remove());
  if (!p || p.is_shelf) return;
  const max = (S.meta?.max_ips || 5) - 1;
  const n = Math.min(max, Math.max(p.ips.length, S.extraIpRows));
  for (let i = 0; i < n; i++) {
    const inp = h("input", { type: "text", placeholder: `${i + 2}. IP-Adresse`, autocomplete: "off", "data-ip": i });
    inp.value = p.ips[i] ?? "";
    if (p.ips_state[i]) ipClass(inp, p.ips_state[i]);
    inp.addEventListener("input", () => onExtraIp(i, inp.value));
    const x = h("button", { class: "btn x", title: "Diese IP-Adresse entfernen", text: "✕", onclick: () => removeExtraIp(i) });
    box.append(h("div", { class: "iprow" }, inp, x));
  }
  const add = h("button", { class: "btn ipadd", text: "+ Weitere IP-Adresse", onclick: addExtraIp });
  add.disabled = n >= max;
  box.append(add);
  // Fokus nach dem Neuaufbau wiederherstellen
  if (S.focusIp !== undefined && S.focusIp !== null) {
    const el = box.querySelector(`[data-ip="${S.focusIp}"]`);
    if (el) { el.focus(); const l = el.value.length; el.setSelectionRange(l, l); }
  }
}

function updateChrome() {
  const name = S.rack?.name || "Unbenannt";
  const title = `${dirty() ? "*" : ""}${name}${persisted() ? "" : " (neu)"} – Rack-Planer ${S.meta?.version || ""} (Webversion)`;
  document.title = title;
  $("#doc-title").textContent = (dirty() ? "● " : "") + (persisted() ? name : `${name} (noch nicht gespeichert)`);
  $("#doc-title").title = dirty() ? "Ungespeicherte Änderungen" : "";
  const ro = S.preview !== null;
  $("#tb-undo").disabled = ro || !S.undo.length;
  $("#tb-redo").disabled = ro || !S.redo.length;
  $("#tb-front").classList.toggle("checked", !S.mode3d && S.ui.side === "front");
  $("#tb-rear").classList.toggle("checked", !S.mode3d && S.ui.side === "rear");
  $("#tb-3d").classList.toggle("checked", S.mode3d);
  $("#cb-profile").checked = S.ui.show_profile;
  $("#cb-profile").disabled = S.mode3d;                 // Seitenansicht gibt es nur in 2D
  $("#tb-profile").classList.toggle("disabled", S.mode3d);
  $("#left-panel").style.pointerEvents = ro ? "none" : "";
  $("#left-panel").style.opacity = ro ? ".55" : "";
  $("#viewwrap").classList.toggle("readonly", ro);
}

let statusTimer = 0;
function status(msg, ms = 5000) {
  const el = $("#status-msg");
  el.textContent = msg || "";
  clearTimeout(statusTimer);
  if (msg) statusTimer = setTimeout(() => { el.textContent = ""; }, ms);
}

/* ------------------------------------------------------------------------------------ */
/* Dialoge                                                                                */
/* ------------------------------------------------------------------------------------ */
function modal({ title, body, buttons, wide = false, onOpen }) {
  return new Promise((resolve) => {
    const back = h("div", { class: "modal-back" });
    const box = h("div", { class: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true" });
    const content = typeof body === "string" ? h("div", { class: "body", html: body }) : h("div", { class: "body" }, body);
    const btns = h("div", { class: "buttons" });
    const close = (v) => { back.remove(); document.removeEventListener("keydown", onKey, true); resolve(v); };
    for (const b of buttons || [{ label: "OK", value: true, primary: true }]) {
      const el = h("button", { class: "btn" + (b.primary ? " primary" : "") + (b.danger ? " danger" : ""), text: b.label });
      el.addEventListener("click", () => {
        if (b.validate && !b.validate()) return;
        close(typeof b.value === "function" ? b.value() : b.value);
      });
      if (b.disabled) el.disabled = true;
      btns.append(el);
      b.el = el;
    }
    const onKey = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); close(null); }
      if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !(e.target instanceof HTMLButtonElement)) {
        const prim = (buttons || []).find((b) => b.primary);
        if (prim && !prim.el.disabled) { e.preventDefault(); e.stopPropagation(); prim.el.click(); }
      }
    };
    document.addEventListener("keydown", onKey, true);
    box.append(h("h2", { text: title }), content, btns);
    back.append(box);
    back.addEventListener("mousedown", (e) => { if (e.target === back) close(null); });
    document.body.append(back);
    const first = box.querySelector("input, select") || btns.querySelector(".primary") || btns.querySelector("button");
    if (first) first.focus();
    if (onOpen) onOpen(box, close);
  });
}
const alertBox = (msg, title = "Rack-Planer") => modal({ title, body: h("p", { text: msg }), buttons: [{ label: "OK", value: true, primary: true }] });
const confirmBox = (msg, ok = "OK", title = "Rack-Planer", danger = false) =>
  modal({ title, body: h("p", { text: msg }), buttons: [{ label: "Abbrechen", value: false }, { label: ok, value: true, primary: !danger, danger }] });

async function askShelf(ask) {
  const body = h("div", {}, h("p", {}, h("b", { text: `„${ask.name}“ ist nicht für den Rackeinbau vorgesehen.` })),
    h("p", { text: "Soll ein Fachboden eingebaut werden, auf dem das Gerät steht?" + (ask.existing ? " Es gibt bereits einen Fachboden mit genügend Platz." : "") }));
  const buttons = [{ label: "Abbrechen", value: null }, { label: "Ohne Fachboden", value: "none" },
    { label: "Neuen Fachboden einbauen", value: "new_shelf", primary: !ask.existing }];
  if (ask.existing) buttons.push({ label: "Auf vorhandenen Fachboden", value: "existing_shelf", primary: true });
  return modal({ title: "Fachboden einbauen?", body, buttons });
}

/* ------------------------------------------------------------------------------------ */
/* Schrank laden / speichern                                                              */
/* ------------------------------------------------------------------------------------ */
function loadDocument(doc, rec = null, fileName = "") {
  S.doc = {
    id: rec?.id || null, revision: rec?.revision || null,
    fileSaved: !!fileName, fileName,      // Datei-Modus: aus einer Datei geöffnet bzw. als Datei gespeichert
    created: doc.created || todayIso(), saved_at: doc.saved_at || "",
    history: (doc.history?.entries || []).slice(),
    history_enabled: !!doc.history?.enabled, history_declined: !!doc.history?.declined,
  };
  S.rack = rackOf(doc);
  S.savedState = "";               // wird nach der ersten Antwort gesetzt (normalisiert)
  S.undo = []; S.redo = []; S.merge = null;
  S.preview = null; S.previewView = null;
  S.historyOffered = false;
  S.ui.selected = "";
  S.autoFit = true;
  if (rec) { try { localStorage.setItem("rackplaner.last", rec.id); } catch (e) { /* */ } }
  history.replaceState(null, "", rec ? `#/rack/${rec.id}` : "#/neu");
  return enqueue(async () => {
    const r = await sendJSON("POST", "/api/state", { rack: S.rack, ui: uiPayload() });
    S.rack = r.rack;
    S.savedState = canon(r.rack);
    applyView(r.view, { force: true });
    renderHistory();
    updateChrome();
  });
}

async function newRack(skipAsk = false) {
  if (!skipAsk && !(await maybeSave())) return;
  await loadDocument(structuredClone(S.meta.new_document));
  status(serverSave() ? "Neuer Schrank – zum Speichern auf dem Server: Speichern (Strg + S)."
    : "Neuer Schrank – Speichern (Strg + S) lädt ihn als .rack.json-Datei herunter.");
}

async function openRack(id, skipAsk = false) {
  if (!skipAsk && !(await maybeSave())) return false;
  let rec;
  try { rec = await getJSON(`/api/racks/${encodeURIComponent(id)}`); } catch (e) { await alertBox(e.message); return false; }
  await loadDocument(rec.document, rec);
  status(`Geöffnet: ${rec.document.name}`);
  return true;
}

/** Ungespeicherte Änderungen? true = weiter, false = abbrechen. */
async function maybeSave() {
  if (!dirty()) return true;
  const v = await modal({ title: "Rack-Planer", body: h("p", { text: `Änderungen an „${S.rack.name}“ speichern?` }),
    buttons: [{ label: "Abbrechen", value: null }, { label: "Verwerfen", value: "discard", danger: true }, { label: "Speichern", value: "save", primary: true }] });
  if (v === "save") return save();
  return v === "discard";
}

function documentPayload() {
  return { app: "Rack-Planer", format: S.meta.format, version: S.meta.format, ...S.rack, created: S.doc.created,
    saved_at: S.doc.saved_at, history: { enabled: S.doc.history_enabled, declined: S.doc.history_declined, entries: S.doc.history } };
}

function adoptSaved(rec) {
  const d = rec.document;
  S.doc.id = rec.id; S.doc.revision = rec.revision;
  S.doc.created = d.created; S.doc.saved_at = d.saved_at;
  S.doc.history = (d.history?.entries || []).slice();
  S.doc.history_enabled = !!d.history?.enabled; S.doc.history_declined = !!d.history?.declined;
  S.savedState = canon(rackOf(d));
  S.rack = rackOf(d);
  try { localStorage.setItem("rackplaner.last", rec.id); } catch (e) { /* */ }
  history.replaceState(null, "", `#/rack/${rec.id}`);
}

function nowIso() {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  return `${todayIso()}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function saveBlob(blob, name) {
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 30000);
}
function rackFileName(name) {
  return (String(name || "Rack").trim().replace(/[\\/:*?"<>|\x00-\x1f]+/g, "_") || "Rack").slice(0, 120) + ".rack.json";
}

/**
 * Datei-Modus (Speichern auf dem Server abgeschaltet): Schrank inkl. Historie als .rack.json
 * herunterladen – wie „Speichern“ in der Desktop-Version. Ist die Historie aktiv, wandert der
 * zuletzt gespeicherte Stand in die Historie.
 */
async function saveToFile({ asNew = false } = {}) {
  if (S.preview !== null) endPreview();
  await queue;
  const d = S.doc;
  if (asNew) { d.history = []; d.created = todayIso(); d.fileName = ""; }
  else if (d.fileSaved && d.history_enabled && S.savedState && canon(S.rack) !== S.savedState) {
    const old = JSON.parse(S.savedState);
    const last = d.history.length ? canon(d.history[d.history.length - 1].rack) : "";
    if (last !== S.savedState) d.history.push({ saved_at: d.saved_at || "", as_of: old.as_of || "", note: "", rack: old });
  }
  d.saved_at = nowIso();
  let doc;
  try { doc = RackCore.readDocument(documentPayload()).doc; } catch (e) { await alertBox(`Speichern fehlgeschlagen:\n${e.message}`); return false; }
  const name = d.fileName && !asNew ? d.fileName : rackFileName(S.rack.name);
  saveBlob(new Blob([JSON.stringify(doc, null, 2) + "\n"], { type: "application/json" }), name);
  d.fileSaved = true; d.fileName = name;
  S.savedState = canon(S.rack);
  updateChrome();
  renderHistory();
  status(`Gespeichert als Datei „${name}“ (Download-Ordner des Browsers).`, 7000);
  return true;
}

async function save({ force = false, asNew = false } = {}) {
  if (!serverSave()) return saveToFile({ asNew });
  if (S.preview !== null) endPreview();
  await queue;
  try {
    let rec;
    if (!S.doc.id || asNew) {
      const doc = documentPayload();
      if (asNew) { doc.history = { enabled: S.doc.history_enabled, declined: S.doc.history_declined, entries: [] }; doc.created = todayIso(); }
      rec = await sendJSON("POST", "/api/racks", { document: doc });
      adoptSaved(rec);
      status(`Gespeichert: „${S.rack.name}“ liegt jetzt auf dem Server.`);
    } else {
      rec = await sendJSON("PUT", `/api/racks/${S.doc.id}`, { rack: S.rack, history_enabled: S.doc.history_enabled,
        history_declined: S.doc.history_declined, base_revision: S.doc.revision, force });
      adoptSaved(rec);
      status(`Gespeichert: „${S.rack.name}“` + (rec.history_added ? `  ·  bisheriger Stand in der Historie (${S.doc.history.length} Einträge)` : ""));
    }
    updateChrome();
    renderHistory();
    return true;
  } catch (e) {
    if (e.conflict) {
      const c = e.conflict.current;
      const v = await modal({ title: "Schrank wurde inzwischen geändert",
        body: h("div", {}, h("p", { text: `„${c.name}“ wurde am ${fmtDateTime(c.saved_at)} an einem anderen Gerät gespeichert, nachdem du ihn geöffnet hast.` }),
          h("p", { text: "Überschreiben ersetzt den anderen Stand (er landet in der Historie, falls sie aktiv ist). Alternativ kannst du deine Fassung als neuen Schrank speichern." })),
        buttons: [{ label: "Abbrechen", value: null }, { label: "Als neuen Schrank speichern", value: "new" }, { label: "Überschreiben", value: "force", danger: true }] });
      if (v === "force") return save({ force: true });
      if (v === "new") return save({ asNew: true });
      return false;
    }
    await alertBox(`Speichern fehlgeschlagen:\n${e.message}`);
    return false;
  }
}

async function saveAsNew() {
  const name = await promptBox("Als neuen Schrank speichern", "Bezeichnung:", `${S.rack.name} (Kopie)`);
  if (name === null) return;
  await op("set_rack", { field: "name", value: name });
  await save({ asNew: true });
}

function promptBox(title, label, value) {
  const inp = h("input", { type: "text", value });
  return modal({ title, body: h("div", { class: "form" }, h("label", { text: label }), inp),
    buttons: [{ label: "Abbrechen", value: null }, { label: "OK", primary: true, value: () => inp.value.trim() || value }] });
}

async function downloadFile() {
  if (!serverSave()) { await saveToFile(); return; }
  if (!S.doc.id || dirty()) {
    const ok = await confirmBox("Heruntergeladen wird der gespeicherte Stand. Jetzt speichern und dann herunterladen?", "Speichern und herunterladen");
    if (!ok || !(await save())) return;
  }
  const name = await download("GET", `/api/racks/${S.doc.id}/file`, undefined, `${S.rack.name}.rack.json`);
  status(`Heruntergeladen: ${name} – lässt sich in der Desktop-Version öffnen.`);
}

async function importFile(file) {
  if (!(await maybeSave())) return;
  let data;
  try { data = JSON.parse(await file.text()); } catch (e) { await alertBox(`Die Datei „${file.name}“ ist keine gültige Projektdatei.`); return; }
  if (!serverSave()) {
    // Datei-Modus: nur im Browser öffnen, nichts auf dem Server ablegen
    let res;
    try { res = RackCore.readDocument(data, file.lastModified ? new Date(file.lastModified).toISOString().slice(0, 10) : ""); }
    catch (e) { await alertBox(`Die Datei „${file.name}“ konnte nicht gelesen werden:\n${e.message}`); return; }
    await loadDocument(res.doc, null, file.name);
    status(`Geöffnet: ${file.name}`);
    if (res.notes?.length) await alertBox(`„${file.name}“ stammt aus einer älteren Version.\n\n${res.notes.join("\n\n")}`);
    return;
  }
  let rec;
  try { rec = await sendJSON("POST", "/api/racks", { document: data }); } catch (e) { await alertBox(`Die Datei „${file.name}“ konnte nicht importiert werden:\n${e.message}`); return; }
  await openRack(rec.id, true);
  status(`Importiert: ${file.name}`);
  if (rec.notes?.length) await alertBox(`„${file.name}“ stammt aus einer älteren Version.\n\n${rec.notes.join("\n\n")}`);
}

async function showRackList() {
  if (!serverSave()) { $("#file-input").click(); return; }
  let racks;
  try { racks = await getJSON("/api/racks"); } catch (e) { await alertBox(e.message); return; }
  const tbody = h("tbody");
  const table = h("table", { class: "racks" }, h("thead", {}, h("tr", {}, h("th", { text: "Bezeichnung" }), h("th", { text: "HE" }),
    h("th", { text: "Geräte" }), h("th", { text: "Stand" }), h("th", { text: "Gespeichert" }), h("th", { text: "Historie" }), h("th"))), tbody);
  let closeFn;
  const fill = (list) => {
    tbody.innerHTML = "";
    for (const r of list) {
      const tr = h("tr", { class: r.id === S.doc?.id ? "cur" : "" },
        h("td", { class: "name", text: r.name }), h("td", { text: r.height_u }), h("td", { text: r.devices }),
        h("td", { text: fmtDate(r.as_of) }), h("td", { text: fmtDateTime(r.saved_at) }), h("td", { text: r.history ? `${r.history} Stände` : "–" }),
        h("td", {}, h("div", { class: "acts" },
          h("button", { class: "btn small primary", text: "Öffnen", onclick: async () => { closeFn(null); await openRack(r.id); } }),
          h("button", { class: "btn small", text: "Datei", title: "Als .rack.json herunterladen (für die Desktop-Version)",
            onclick: () => download("GET", `/api/racks/${r.id}/file`, undefined, `${r.name}.rack.json`) }),
          h("button", { class: "btn small danger", text: "Löschen", onclick: async () => {
            if (!(await confirmBox(`„${r.name}“ mit allen früheren Ständen endgültig vom Server löschen?`, "Löschen", "Schrank löschen", true))) return;
            await api("DELETE", `/api/racks/${r.id}`);
            if (r.id === S.doc?.id) { S.doc.id = null; S.doc.revision = null; S.savedState = ""; updateChrome(); }
            fill(await getJSON("/api/racks"));
          } }))));
      tr.addEventListener("dblclick", async () => { closeFn(null); await openRack(r.id); });
      tbody.append(tr);
    }
    if (!list.length) tbody.append(h("tr", {}, h("td", { colspan: 7, class: "empty", text: "Noch keine Schränke gespeichert. Lege einen neuen an oder importiere eine Datei aus der Desktop-Version." })));
  };
  fill(racks);
  const v = await modal({ title: "Schränke auf dem Server", wide: true, body: table,
    onOpen: (_box, close) => { closeFn = close; },
    buttons: [{ label: "Datei importieren …", value: "import" }, { label: "Neuer Schrank", value: "new" }, { label: "Schließen", value: null, primary: true }] });
  if (v === "import") $("#file-input").click();
  if (v === "new") newRack();
}

/* ------------------------------------------------------------------------------------ */
/* Historie                                                                               */
/* ------------------------------------------------------------------------------------ */
async function maybeOfferHistory() {
  const d = S.doc;
  if (!persisted() || !dirty() || d.history_enabled || d.history_declined || S.historyOffered) return;
  S.historyOffered = true;
  await new Promise((r) => setTimeout(r, 0));
  const old = JSON.parse(S.savedState || "{}").as_of || "";
  const v = await modal({ title: "Historie anlegen?", body: h("div", {}, h("p", {}, h("b", { text: "Du änderst einen gespeicherten Schrank." })),
    h("p", { text: "Soll eine Historie angelegt werden? Dann bleibt der bisherige Stand" + (old ? ` vom ${fmtDate(old)}` : "") +
      " beim Speichern erhalten und lässt sich jederzeit im Tab „Historie“ ansehen oder wiederherstellen." })),
    buttons: [{ label: "Ohne Historie weiter", value: false }, { label: "Historie anlegen (empfohlen)", value: true, primary: true }] });
  if (v) enableHistory(); else { d.history_declined = true; }
}

async function enableHistory() {
  S.doc.history_enabled = true;
  S.doc.history_declined = false;
  $("#hist-on").checked = true;
  let msg = "Historie aktiviert: Beim Speichern bleibt der bisherige Stand erhalten.";
  if ((S.rack.as_of || "") < todayIso()) {
    await op("set_rack", { field: "as_of", value: todayIso() });
    msg += " Der aktuelle Stand wurde auf heute gesetzt.";
  }
  renderHistory();
  status(msg, 7000);
}

function renderHistory() {
  if (!S.doc) return;
  const d = S.doc;
  setVal($("#hist-on"), d.history_enabled, true);
  const list = $("#hist-list");
  list.innerHTML = "";
  const cur = h("div", { class: "hist-item cur" + (S.preview === null ? " sel" : "") },
    `Aktueller Stand (${fmtDate(S.rack.as_of)})` + (dirty() ? " – ungespeichert" : ""));
  cur.addEventListener("click", endPreview);
  list.append(cur);
  for (let i = d.history.length - 1; i >= 0; i--) {
    const s = d.history[i];
    const n = (s.rack.items || []).filter((it) => it.category !== "Fachboden").length;
    const el = h("div", { class: "hist-item" + (S.preview === i ? " sel" : "") },
      h("div", { text: `Stand ${fmtDate(s.as_of)}` }),
      h("div", { class: "sub", text: `gespeichert ${fmtDateTime(s.saved_at)} · ${n} Gerät(e)` }));
    el.addEventListener("click", () => startPreview(i));
    list.append(el);
  }
  let info;
  if (!persisted()) info = serverSave() ? "Die Historie wird mit dem Schrank auf dem Server gespeichert – zuerst speichern."
    : "Die Historie wird in der .rack.json-Datei des Schranks gespeichert – zuerst speichern.";
  else if (!d.history.length) info = "Noch keine früheren Stände. " + (d.history_enabled ?
    "Beim nächsten Speichern wird der bisherige Stand hier abgelegt." : "Aktiviere die Historie, dann bleibt bei jedem Speichern der bisherige Stand erhalten.");
  else info = "Klicke einen Stand an, um ihn im Schrank anzusehen.";
  $("#hist-info").textContent = info;
  const on = S.preview !== null;
  $("#hist-restore").disabled = !on; $("#hist-copy").disabled = !on; $("#hist-new").disabled = !on;
}

function showPreview(i) {
  const snap = S.doc.history[i];
  return sendJSON("POST", "/api/state", { rack: snap.rack, ui: uiPayload({ read_only: true, selected: "" }) }).then((r) => {
    S.previewView = r.view;
    $("#rackview").innerHTML = r.view.svg;
    applyZoom();
    if (S.v3d) S.v3d.update(r.view, { readOnly: true });
    renderBanners();
    renderProps(null);
    updateChrome();
    renderHistory();
  });
}
function startPreview(i) { S.preview = i; return enqueue(() => showPreview(i)); }
function endPreview() {
  if (S.preview === null) return;
  S.preview = null; S.previewView = null;
  refresh();
}
async function restorePreview() {
  if (S.preview === null) return;
  const snap = S.doc.history[S.preview];
  const before = canon(S.rack);
  S.preview = null; S.previewView = null;
  S.rack = structuredClone(snap.rack);
  pushUndo(before);
  S.ui.selected = "";
  await refresh();
  afterChange();
  renderHistory();
  status(`Stand vom ${fmtDate(snap.as_of)} wiederhergestellt (Strg + Z macht es rückgängig).`, 7000);
}
async function previewCopy() {
  if (S.preview === null) return;
  const snap = S.doc.history[S.preview];
  const name = await download("POST", "/api/file", { rack: snap.rack, filename: `${S.rack.name} Stand ${snap.as_of}` }, "Stand.rack.json");
  status(`Heruntergeladen: ${name}`);
}
async function previewAsNew() {
  if (S.preview === null) return;
  if (!serverSave()) return previewCopy();
  const snap = S.doc.history[S.preview];
  const doc = { ...structuredClone(snap.rack), name: `${snap.rack.name} (Stand ${fmtDate(snap.as_of)})`, created: todayIso() };
  const rec = await sendJSON("POST", "/api/racks", { document: doc });
  if (await confirmBox(`Als neuer Schrank „${doc.name}“ gespeichert. Jetzt öffnen?`, "Öffnen")) await openRack(rec.id);
}

/* ------------------------------------------------------------------------------------ */
/* Auswahl, Seiten                                                                        */
/* ------------------------------------------------------------------------------------ */
function select(uid) {
  if (uid === S.ui.selected) return;
  S.ui.selected = uid;
  S.focusIp = null;
  refresh();
}
function selectFromList(uid, side) {
  if (S.preview !== null) return;
  S.ui.selected = uid;
  if (side && side !== S.ui.side) S.ui.side = side;
  refresh();
}
function showItem(uid) {
  const row = S.view.list.find((r) => r.uid === uid);
  if (S.mode3d) { select(uid); S.v3d.focusItem(uid); return; }
  selectFromList(uid, row?.mount_side);
}
function setSide(side) { if (S.mode3d) setMode3d(false); S.ui.side = side; refresh(); }

/* ------------------------------------------------------------------------------------ */
/* Drag & Drop in der Zeichnung                                                           */
/* ------------------------------------------------------------------------------------ */
let drag = null;
let lastGhost = { uid: "", time: 0 };
function svgPoint(evt) {
  const svg = $("#rackview svg");
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX; pt.y = evt.clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}
function unitAt(y) { const g = S.view.geo; return g.height_u + 1 - (y - g.top) / g.u_px; }

function ghostRect(x, y, w, hh, ok) {
  const svg = $("#rackview svg");
  let r = svg.querySelector("#dragghost");
  if (!r) {
    r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.id = "dragghost";
    r.setAttribute("stroke-width", "2");
    r.setAttribute("stroke-dasharray", "6 4");
    r.setAttribute("pointer-events", "none");
    svg.append(r);
  }
  r.setAttribute("x", x); r.setAttribute("y", y); r.setAttribute("width", Math.max(0, w)); r.setAttribute("height", Math.max(0, hh));
  r.setAttribute("fill", ok ? "rgba(46,204,113,.35)" : "rgba(231,76,60,.35)");
  r.setAttribute("stroke", ok ? "#1e8449" : "#a93226");
}
function rectOf(el) { return el.getAttribute("data-rect").split(",").map(Number); }

function onPointerDown(e) {
  if (e.button !== 0 || S.preview !== null || !S.view) return;
  if (document.activeElement && document.activeElement.matches("input, select")) document.activeElement.blur();
  const el = e.target.closest(".el");
  if (!el) {
    const gh = e.target.closest(".ghost");
    if (gh) {
      // Doppelklick auf ein Gerät der Gegenseite: zur anderen Seite wechseln
      const now = Date.now();
      if (lastGhost.uid === gh.dataset.uid && now - lastGhost.time < 450) { lastGhost.uid = ""; showItem(gh.dataset.uid); }
      else lastGhost = { uid: gh.dataset.uid, time: now };
    } else if (S.ui.selected) select("");
    return;
  }
  const uid = el.dataset.uid;
  if (uid !== S.ui.selected) select(uid);
  const p = svgPoint(e);
  const t = S.view.targets;
  if (el.dataset.kind === "shelfdev") {
    const [x] = rectOf(el);
    drag = { kind: "dev", uid, start: [e.clientX, e.clientY], grabX: p.x - x, info: t.devs[uid], moved: false };
  } else {
    const top = el.dataset.top;
    const info = t.tops[top];
    drag = { kind: "top", uid: top, start: [e.clientX, e.clientY], offset: unitAt(p.y) - info.pos, info, moved: false };
  }
  $("#rackview").setPointerCapture(e.pointerId);
  e.preventDefault();
}

function onPointerMove(e) {
  if (!drag) return;
  if (!drag.moved && Math.hypot(e.clientX - drag.start[0], e.clientY - drag.start[1]) < 4) return;
  drag.moved = true;
  $("#viewwrap").classList.add("dragging");
  const p = svgPoint(e);
  const g = S.view.geo;
  if (drag.kind === "top") {
    const info = drag.info;
    let raw = unitAt(p.y) - drag.offset;
    raw = S.ui.fine ? Math.round(raw * 3) / 3 : Math.round(raw);
    const pos = Math.max(1, Math.min(raw, g.height_u - info.span + 1));
    const k = Math.round(pos * 3);
    const same = Math.abs(pos - info.pos) < 1e-6;
    const ok = same || info.ok.includes(k);
    drag.target = ok && !same ? pos : null;
    ghostRect(g.left, g.top + (g.height_u - (pos + info.span - 1)) * g.u_px, g.inner_w, info.span * g.u_px, ok);
  } else {
    const info = drag.info;
    const hpx = info.height_cm > 0 ? Math.min(info.height_u * g.u_px, info.height_cm * 10 / U_MM * g.u_px) : info.height_u * g.u_px;
    const wpx = Math.max(16, info.width_mm * g.shelf_scale);
    let best = null;
    for (const el of $$('#rackview .el[data-kind="shelf"]')) {
      const sid = el.dataset.uid;
      if (!(sid in info.targets)) continue;
      const [, sy, , sh] = rectOf(el);
      const st = S.view.targets.tops[sid];
      const reach = Math.max(st.span - st.height_u, info.height_u) * g.u_px;
      if (sy - reach <= p.y && p.y <= sy + sh) { best = { sid, sy, sh }; break; }
    }
    if (!best) {
      drag.target = null;
      ghostRect(p.x - drag.grabX, p.y - hpx / 2, wpx, hpx, false);
      return;
    }
    const xmm = (p.x - drag.grabX - g.left - 4) / g.shelf_scale;
    let off = Math.round(xmm / 5) * 5;
    off = Math.max(0, Math.min(off, S.meta.shelf_width_mm - info.width_mm));
    const ok = info.targets[best.sid].includes(off);
    drag.target = ok ? { shelf: best.sid, offset: off } : null;
    const bottom = best.sy + best.sh - g.plate_h;
    ghostRect(g.left + 4 + off * g.shelf_scale, bottom - hpx, wpx - 2, hpx, ok);
  }
}

function onPointerUp() {
  if (!drag) return;
  const d = drag;
  drag = null;
  $("#viewwrap").classList.remove("dragging");
  const gh = $("#dragghost");
  if (gh) gh.remove();
  if (!d.moved || !d.target) return;
  if (d.kind === "top") op("move", { uid: d.uid, pos: d.target }, { quiet: true });
  else op("move_on_shelf", { uid: d.uid, shelf: d.target.shelf, offset: d.target.offset }, { quiet: true });
}

/* ------------------------------------------------------------------------------------ */
/* Vorlagen                                                                               */
/* ------------------------------------------------------------------------------------ */
function tplMatches(t, q) {
  const hay = `${t.group} ${t.model} ${t.category} ${t.note}`.toLowerCase();
  return q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
}
function tplTip(t) {
  let tip = `${t.category} · ${t.height_u} HE`;
  if (t.height_cm) tip += ` (Höhe ${t.height_cm} cm)`;
  tip += t.rackmount ? " · Rackmontage" : " · nicht rackfähig (Fachboden)";
  if (t.note) tip += `\nMaße (B × T × H): ${t.note}`;
  if (t.power_w) tip += `\nca. ${t.power_w} W`;
  if (t.depth_mm) tip += `\nTiefe ${t.depth_mm} mm`;
  if (t.rails) tip += " · auf Einbauschienen (blockiert die Gegenseite)";
  if (!t.builtin) tip += "\nEigene Vorlage";
  return tip;
}
function renderTemplates() {
  const tree = $("#tpl-tree");
  const q = $("#tpl-search").value.trim();
  tree.innerHTML = "";
  tree.append(h("div", { class: "tpl-head" }, h("span", { text: "Gerät" }), h("span", { text: "HE" })));
  const groups = new Map();
  for (const t of S.templates) {
    if (q && !tplMatches(t, q)) continue;
    if (!groups.has(t.group)) groups.set(t.group, []);
    groups.get(t.group).push(t);
  }
  let first = null;
  for (const [g, list] of groups) {
    const collapsed = !q && S.tplCollapsed.has(g);
    const head = h("div", { class: "tpl-group" }, h("span", { class: "tw", text: collapsed ? "▶" : "▼" }), g);
    head.addEventListener("click", () => { if (S.tplCollapsed.has(g)) S.tplCollapsed.delete(g); else S.tplCollapsed.add(g); renderTemplates(); });
    tree.append(head);
    if (collapsed) continue;
    for (const t of list) {
      first = first || t;
      const row = h("div", { class: "tpl" + (t.rackmount ? "" : " nonrack") + (S.tplSel === t.id ? " sel" : ""), title: tplTip(t), "data-id": t.id },
        h("span", { class: "name" }, h("span", { text: t.model }),
          t.builtin ? null : h("button", { class: "del", title: "Eigene Vorlage löschen", text: "✕", onclick: (e) => { e.stopPropagation(); deleteTemplate(t); } })),
        h("span", { text: t.height_u }));
      row.addEventListener("click", () => { S.tplSel = t.id; renderTemplates(); });
      row.addEventListener("dblclick", () => { S.tplSel = t.id; addTemplate(t); });
      tree.append(row);
    }
  }
  const none = groups.size === 0;
  $("#tpl-none").hidden = !none;
  if (q && first && !S.templates.some((t) => t.id === S.tplSel && tplMatches(t, q))) {
    S.tplSel = first.id;
    const el = tree.querySelector(`[data-id="${first.id}"]`);
    if (el) el.classList.add("sel");
  }
  const sel = tree.querySelector(".tpl.sel");
  if (sel) sel.scrollIntoView({ block: "nearest" });
}
function addTemplate(t) {
  t = t || S.templates.find((x) => x.id === S.tplSel);
  if (!t) { alertBox("Bitte zuerst eine Vorlage auswählen."); return; }
  op("add_template", { template: t });
}
async function deleteTemplate(t) {
  if (!(await confirmBox(`Die eigene Vorlage „${t.model}“ löschen? Sie verschwindet für alle im Netzwerk.`, "Löschen", "Vorlage löschen", true))) return;
  try { await api("DELETE", `/api/templates/${t.id}`); } catch (e) { await alertBox(e.message); }
  await loadTemplates();
}
async function loadTemplates() {
  S.templates = await getJSON("/api/templates");
  renderTemplates();
}
async function saveAsTemplate() {
  const p = S.view.props;
  if (!p || p.is_shelf) return;
  const it = S.rack.items.find((i) => i.uid === p.uid);
  const name = await promptBox("Als Vorlage speichern", "Name der Vorlage:", it.model && it.model !== it.name ? `${it.name} (${it.model})` : it.name || it.model);
  if (name === null) return;
  try {
    await sendJSON("POST", "/api/templates", { group: S.meta.own_group, model: name, category: it.category, height_u: it.height_u,
      rackmount: it.rackmount, width_mm: it.width_mm, power_w: it.power_w, height_cm: it.height_cm, depth_mm: it.depth_mm, rails: it.rails,
      note: it.depth_mm ? `Tiefe ${it.depth_mm} mm` : "" });
  } catch (e) { await alertBox(e.message); return; }
  S.tplCollapsed.delete(S.meta.own_group);
  await loadTemplates();
  status(`Vorlage „${name}“ gespeichert (Gruppe „${S.meta.own_group}“).`);
}

/* ------------------------------------------------------------------------------------ */
/* Eigenes Gerät, Export                                                                  */
/* ------------------------------------------------------------------------------------ */
async function addCustom() {
  const cats = S.meta.categories.map((c) => h("option", { value: c, text: c, selected: c === "Sonstiges" }));
  const f = {
    name: h("input", { type: "text", placeholder: "z. B. Hypervisor 01" }),
    ip: h("input", { type: "text", placeholder: "z. B. 192.168.1.10, 10.0.0.10 (bis zu 5)" }),
    category: h("select", {}, cats),
    rackmount: h("input", { type: "checkbox", checked: true }),
    height_u: h("input", { type: "number", min: 1, max: 20, value: 1 }),
    height_cm: h("input", { type: "number", min: 0.5, max: 250, step: 0.5, value: 5, disabled: true }),
    width_mm: h("input", { type: "number", min: 20, max: S.meta.shelf_width_mm, value: 200, disabled: true }),
    power_w: h("input", { type: "number", min: 0, max: 10000, value: 0 }),
    depth_mm: h("input", { type: "number", min: 0, max: 2000, step: 10, value: Math.min(300, S.rack.depth_mm) }),
    mount_side: h("select", {}, h("option", { value: "front", text: "Vorderseite (vorne montiert)", selected: S.ui.side === "front" }),
      h("option", { value: "rear", text: "Rückseite (hinten montiert)", selected: S.ui.side === "rear" })),
    rails: h("input", { type: "checkbox" }),
  };
  const sync = () => {
    const r = f.rackmount.checked;
    f.width_mm.disabled = r; f.height_cm.disabled = r; f.height_u.disabled = !r; f.rails.disabled = !r;
    if (!r) f.height_u.value = Math.max(1, Math.ceil(Number(f.height_cm.value || 0) * 10 / U_MM - 1e-6));
  };
  f.rackmount.addEventListener("change", sync);
  f.height_cm.addEventListener("input", sync);
  const unit = (el, u) => h("span", { class: "unit", "data-unit": u }, el);
  const body = h("div", { class: "form" },
    h("label", { text: "Gerätename:" }), f.name, h("label", { text: "IP-Adresse(n):" }), f.ip,
    h("label", { text: "Kategorie:" }), f.category, h("span"), h("label", { class: "check" }, f.rackmount, "Für den Rackeinbau (19\") geeignet"),
    h("label", { text: "Höhe:" }, ), unit(f.height_u, "HE"), h("label", { text: "Höhe (non-Rack):" }), unit(f.height_cm, "cm"),
    h("label", { text: "Breite (auf Fachboden):" }), unit(f.width_mm, "mm"), h("label", { text: "Leistungsaufnahme:" }), unit(f.power_w, "W"),
    h("label", { text: "Tiefe:" }), unit(f.depth_mm, "mm"), h("label", { text: "Montage:" }), f.mount_side,
    h("span"), h("label", { class: "check" }, f.rails, "Auf Einbauschienen (blockiert die Gegenseite)"));
  const v = await modal({ title: "Eigenes Gerät hinzufügen", body,
    buttons: [{ label: "Abbrechen", value: null }, { label: "Hinzufügen", primary: true, value: () => ({
      name: f.name.value, ip: f.ip.value, category: f.category.value, rackmount: f.rackmount.checked,
      height_u: Number(f.height_u.value), height_cm: Number(f.height_cm.value), width_mm: Number(f.width_mm.value),
      power_w: Number(f.power_w.value), depth_mm: Number(f.depth_mm.value), mount_side: f.mount_side.value, rails: f.rails.checked }) }] });
  if (v) op("add_custom", { item: v });
}

let pdfSeparate = false;
async function exportPdf() {
  const used = new Set(S.view.sides_used);
  const cb = {}; const row = h("div", { class: "row" });
  for (const sd of ["front", "rear"]) {
    cb[sd] = h("input", { type: "checkbox", checked: sd === S.ui.side || used.has(sd) });
    row.append(h("label", { class: "check" }, cb[sd], SIDE_LABEL[sd]));
  }
  const sep = h("input", { type: "checkbox", checked: pdfSeparate });
  const hint = h("div", { class: "hint" });
  const power = h("input", { type: "checkbox" });
  const buttons = [{ label: "Abbrechen", value: null }, { label: "Exportieren …", primary: true, value: () => ({
    sides: ["front", "rear"].filter((s) => cb[s].checked), separate: sep.checked, power: power.checked }) }];
  const validate = () => {
    const n = Object.values(cb).filter((c) => c.checked).length;
    sep.disabled = n < 2;
    if (buttons[1].el) buttons[1].el.disabled = n === 0;
    hint.textContent = n < 2 ? "Eine Seite des Schranks auf einer A4-Seite." : sep.checked ?
      "Vorder- und Rückseite auf je einer eigenen A4-Seite." : "Beide Seiten stehen nebeneinander auf einer A4-Seite.";
  };
  [...Object.values(cb), sep].forEach((c) => c.addEventListener("change", validate));
  validate();
  const body = h("div", { class: "form" }, h("span", { class: "lbl", text: "Seiten:" }), row,
    h("span"), h("label", { class: "check", title: "Aus: Vorder- und Rückseite nebeneinander auf einer A4-Seite. An: Vorderseite auf Seite 1, Rückseite auf Seite 2 (jeweils größer)." }, sep, "Jede Seite auf eine eigene PDF-Seite"),
    h("span"), hint,
    h("span", { class: "lbl", text: "Zusatz:" }), h("label", { class: "check", title: "Summe der Leistungsaufnahme aller Geräte (W, A bei 230 V) und Wärmelast (W, BTU/h) unter dem Schrank" }, power, "Max. Stromlast und Wärmelast anzeigen"));
  const v = await modal({ title: "Als PDF exportieren", body, buttons, onOpen: validate });
  if (!v) return;
  pdfSeparate = v.separate;
  try {
    const name = await download("POST", "/api/export", { rack: S.rack, kind: "pdf", ...v }, `${S.rack.name}.pdf`);
    status(`PDF exportiert: ${name}`);
  } catch (e) { await alertBox(`PDF-Export fehlgeschlagen:\n${e.message}`); }
}

async function exportImage() {
  const fmt = h("select", {}, h("option", { value: "png", text: "PNG (Rastergrafik)", selected: true }), h("option", { value: "svg", text: "SVG (Vektorgrafik, beliebig skalierbar)" }));
  const radios = {}; const row = h("div", { class: "row" });
  for (const sd of ["front", "rear"]) {
    radios[sd] = h("input", { type: "radio", name: "imgside", checked: sd === S.ui.side });
    row.append(h("label", { class: "check" }, radios[sd], SIDE_LABEL[sd]));
  }
  const scale = h("select", {}, h("option", { value: 1, text: "Normal (1×)" }), h("option", { value: 2, text: "Hoch (2×)", selected: true }), h("option", { value: 4, text: "Sehr hoch (4×)" }));
  const transparent = h("input", { type: "checkbox" });
  const power = h("input", { type: "checkbox" });
  const sync = () => { const png = fmt.value === "png"; scale.disabled = !png; transparent.disabled = !png; };
  fmt.addEventListener("change", sync);
  const body = h("div", { class: "form" }, h("label", { text: "Format:" }), fmt, h("span", { class: "lbl", text: "Seite:" }), row,
    h("label", { text: "Auflösung:" }), scale, h("span"), h("label", { class: "check" }, transparent, "Transparenter Hintergrund"),
    h("span", { class: "lbl", text: "Zusatz:" }), h("label", { class: "check" }, power, "Max. Stromlast und Wärmelast anzeigen"));
  const v = await modal({ title: "Als Bild exportieren", body, buttons: [{ label: "Abbrechen", value: null }, { label: "Exportieren …", primary: true,
    value: () => ({ kind: fmt.value, side: radios.rear.checked ? "rear" : "front", scale: Number(scale.value), transparent: transparent.checked, power: power.checked }) }] });
  if (!v) return;
  try {
    const name = await download("POST", "/api/export", { rack: S.rack, ...v }, `${S.rack.name}.${v.kind}`);
    status(`Bild exportiert: ${name}`);
  } catch (e) { await alertBox(`Bildexport fehlgeschlagen:\n${e.message}`); }
}

/* ------------------------------------------------------------------------------------ */
/* Eigenschaften bearbeiten                                                               */
/* ------------------------------------------------------------------------------------ */
const debouncers = {};
function debounce(key, fn, ms = 350) {
  clearTimeout(debouncers[key]);
  debouncers[key] = setTimeout(fn, ms);
}
const selUid = () => S.view?.props?.uid;
function setItem(field, value, opts) { const uid = selUid(); if (uid) return op("set_item", { uid, field, value }, opts); }

function onExtraIp(i, value) {
  const p = S.view.props;
  const ips = p.ips.slice();
  while (ips.length <= i) ips.push("");
  ips[i] = value.trim();
  S.focusIp = i;
  S.extraIpRows = Math.max(S.extraIpRows, i + 1);
  debounce("ips", () => setItem("ips", ips, { merge: `ips${i}:${p.uid}` }));
}
function addExtraIp() {
  const p = S.view.props;
  S.extraIpRows = Math.min((S.meta.max_ips || 5) - 1, Math.max(p.ips.length, S.extraIpRows) + 1);
  S.focusIp = S.extraIpRows - 1;
  renderExtraIps(p);
}
function removeExtraIp(i) {
  const p = S.view.props;
  S.extraIpRows = Math.max(0, Math.max(p.ips.length, S.extraIpRows) - 1);
  S.focusIp = null;
  const ips = p.ips.filter((_, k) => k !== i);
  if (i < p.ips.length) setItem("ips", ips); else renderExtraIps(p);
}

async function deleteSelected() {
  const p = S.view?.props;
  if (!p || S.preview !== null) return;
  if (p.is_shelf && p.shelf_devices && !(await confirmBox(`Den Fachboden mit ${p.shelf_devices} Gerät(en) darauf entfernen?`, "Entfernen", "Rack-Planer", true))) return;
  op("delete", { uid: p.uid });
}

function bindInputs() {
  // Schrank
  $("#r-name").addEventListener("input", (e) => debounce("rname", () => op("set_rack", { field: "name", value: e.target.value }, { merge: "rack_name" })));
  $("#r-height").addEventListener("change", (e) => op("set_rack", { field: "height_u", value: e.target.value }).then(() => { S.autoFit = true; applyZoom(); }));
  $("#r-depth").addEventListener("change", (e) => op("set_rack", { field: "depth_mm", value: e.target.value }, { merge: "rack_depth" }));
  $("#r-asof").addEventListener("change", (e) => e.target.value && op("set_rack", { field: "as_of", value: e.target.value }));
  $("#r-today").addEventListener("click", () => op("set_rack", { field: "as_of", value: todayIso() }));
  $("#r-fine").addEventListener("change", (e) => { S.ui.fine = e.target.checked; status(S.ui.fine ? "Feinraster ⅓ HE aktiv" : "Raster: ganze HE", 3000); renderProps(S.view.props, true); });
  for (const n of S.meta.height_presets) {
    $("#r-height-presets").append(h("button", { class: "btn", title: `${n} HE`, text: n, onclick: () => op("set_rack", { field: "height_u", value: n }).then(() => { S.autoFit = true; applyZoom(); }) }));
  }
  for (const n of S.meta.depth_presets) {
    $("#r-depth-presets").append(h("button", { class: "btn", title: `${n} mm`, text: n / 10, onclick: () => op("set_rack", { field: "depth_mm", value: n }) }));
  }
  // Vorlagen
  $("#tpl-search").addEventListener("input", renderTemplates);
  $("#tpl-search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addTemplate(); }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); moveTplSel(e.key === "ArrowDown" ? 1 : -1); }
  });
  $("#tpl-tree").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addTemplate(); }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); moveTplSel(e.key === "ArrowDown" ? 1 : -1); }
  });
  $("#tpl-add").addEventListener("click", () => addTemplate());
  $("#add-custom").addEventListener("click", addCustom);
  $("#add-shelf").addEventListener("click", () => op("add_shelf"));
  // Eigenschaften
  $("#p-name").addEventListener("input", (e) => { const uid = selUid(); debounce("pname", () => uid && op("set_item", { uid, field: "name", value: e.target.value }, { merge: `name:${uid}` })); });
  $("#p-show-name").addEventListener("change", (e) => setItem("show_name", e.target.checked));
  $("#p-ip").addEventListener("input", (e) => { const uid = selUid(); debounce("pip", () => uid && op("set_item", { uid, field: "ip", value: e.target.value }, { merge: `ip:${uid}` })); });
  $("#p-cat").addEventListener("change", (e) => setItem("category", e.target.value));
  $("#p-height").addEventListener("change", (e) => setItem("height_u", e.target.value));
  $("#p-height-cm").addEventListener("change", (e) => setItem("height_cm", e.target.value));
  $("#p-pos").addEventListener("change", (e) => setItem("position", e.target.value));
  $("#p-width").addEventListener("change", (e) => setItem("width_mm", e.target.value));
  $("#p-offset").addEventListener("change", (e) => setItem("offset_mm", e.target.value));
  $("#p-power").addEventListener("change", (e) => setItem("power_w", e.target.value, { merge: `power:${selUid()}` }));
  $("#p-side").addEventListener("change", (e) => setItem("mount_side", e.target.value));
  $("#p-depth").addEventListener("change", (e) => setItem("depth_mm", e.target.value, { merge: `depth:${selUid()}` }));
  $("#p-rails").addEventListener("change", (e) => setItem("rails", e.target.checked));
  $("#p-shelf-btn").addEventListener("click", () => op("put_on_shelf", { uid: selUid() }));
  $("#p-up").addEventListener("click", () => op("nudge", { uid: selUid(), delta: 1 }, { quiet: true }));
  $("#p-down").addEventListener("click", () => op("nudge", { uid: selUid(), delta: -1 }, { quiet: true }));
  $("#p-del").addEventListener("click", deleteSelected);
  $("#p-save-tpl").addEventListener("click", saveAsTemplate);
  // Historie
  $("#hist-on").addEventListener("change", (e) => {
    if (e.target.checked) enableHistory();
    else { S.doc.history_enabled = false; renderHistory(); if (S.doc.history.length) status("Historie pausiert – vorhandene Einträge bleiben erhalten (nach dem Speichern)."); }
  });
  $("#hist-restore").addEventListener("click", restorePreview);
  $("#hist-copy").addEventListener("click", previewCopy);
  $("#hist-new").addEventListener("click", previewAsNew);
  $$(".tabbar button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
  // Datei
  $("#file-input").addEventListener("change", (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) importFile(f); });
  // Zeichnung
  const rv = $("#rackview");
  rv.addEventListener("pointerdown", onPointerDown);
  rv.addEventListener("pointermove", onPointerMove);
  rv.addEventListener("pointerup", onPointerUp);
  rv.addEventListener("pointercancel", onPointerUp);
  $("#viewwrap").addEventListener("wheel", (e) => { if (e.ctrlKey) { e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15); } }, { passive: false });
  $("#viewwrap").addEventListener("mousedown", (e) => { if (e.target.id === "viewwrap" || e.target.id === "rackview") { if (S.ui.selected && S.preview === null) select(""); } });
  window.addEventListener("resize", () => { if (S.autoFit) applyZoom(); });
  window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
}

function moveTplSel(dir) {
  const rows = $$("#tpl-tree .tpl");
  if (!rows.length) return;
  let i = rows.findIndex((r) => Number(r.dataset.id) === S.tplSel);
  i = Math.max(0, Math.min(rows.length - 1, i + dir));
  S.tplSel = Number(rows[i].dataset.id);
  rows.forEach((r) => r.classList.toggle("sel", r === rows[i]));
  rows[i].scrollIntoView({ block: "nearest" });
}

function setTab(tab) {
  S.tab = tab;
  $$(".tabbar button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  $("#page-list").hidden = tab !== "list";
  $("#page-history").hidden = tab !== "history";
  if (tab === "history") renderHistory(); else endPreview();
}

/* ------------------------------------------------------------------------------------ */
/* Menüs, Tastenkürzel                                                                    */
/* ------------------------------------------------------------------------------------ */
const ACTIONS = {
  open: () => showRackList(),
  new: () => newRack(),
  save: () => save(),
  saveAsNew: () => saveAsNew(),
  importFile: () => $("#file-input").click(),
  downloadFile: () => downloadFile(),
  pdf: () => exportPdf(),
  image: () => exportImage(),
  image3d: () => export3d(),
  view3d: () => setMode3d(true),
  undo, redo,
  front: () => setSide("front"),
  rear: () => setSide("rear"),
  flip: () => (S.mode3d ? S.v3d.showSide(OTHER[S.v3d.facing()]) : setSide(OTHER[S.ui.side])),
  profile: () => { S.ui.show_profile = !S.ui.show_profile; S.autoFit = true; refresh(); },
  other: () => { S.ui.show_other = !S.ui.show_other; refresh(); },
  "zoom-in": () => zoomBy(1.2), "zoom-out": () => zoomBy(1 / 1.2), fit,
  search: () => { $("#tpl-search").focus(); $("#tpl-search").select(); },
  history: () => setTab("history"),
  tutorial: () => startTutorial(),
  about: () => showAbout(),
  update: () => showUpdate(),
};

const MENUS = {
  save: () => serverSave()
    ? [["Speichern", "save", "Strg + S"], ["Als neuen Schrank speichern …", "saveAsNew"], null,
      ["Datei importieren (.rack.json) …", "importFile"], ["Als Datei herunterladen (.rack.json)", "downloadFile"]]
    : [["Speichern (als .rack.json-Datei)", "save", "Strg + S"], ["Als neuen Schrank speichern …", "saveAsNew"], null,
      ["Datei öffnen (.rack.json) …", "importFile"]],
  export: () => [["als PDF …", "pdf", "Strg + P"], ["als Bild (PNG/SVG) …", "image", "Strg + E"], null,
    ["3D-Ansicht als Bild (PNG) …", "image3d", "Strg + Umschalt + E"]],
  view: () => [["Seite wechseln", "flip", "Strg + R"], [(S.ui.show_other ? "✓" : "") + "Gegenseite andeuten", "other", "", S.ui.show_other],
    [(S.ui.show_profile ? "✓" : "") + "Seitenansicht", "profile", "", S.ui.show_profile], null,
    ["Vergrößern", "zoom-in", "Strg + Mausrad"], ["Verkleinern", "zoom-out"], ["Anpassen", "fit", "Strg + 0"], null,
    ["Vorlage suchen", "search", "Strg + F"], ["Historie anzeigen", "history", "Strg + H"]],
  help: () => [["Tutorial", "tutorial", "F1"], ["Infos über Rack-Planer", "about"], null, ["Programm aktualisieren …", "update"]],
};

function openMenu(btn, name) {
  closeMenu();
  const pop = h("div", { class: "menu-pop", id: "menu-pop" });
  for (const entry of MENUS[name]()) {
    if (!entry) { pop.append(h("hr")); continue; }
    let [label, act, key, checked] = entry;
    const isCheck = checked !== undefined;
    if (isCheck) label = label.replace(/^✓/, "");
    const b = h("button", {}, h("span", { class: isCheck ? (checked ? "check" : "nocheck") : "", text: label }), h("span", { class: "key", text: key || "" }));
    b.addEventListener("click", () => { closeMenu(); ACTIONS[act](); });
    pop.append(b);
  }
  document.body.append(pop);
  const r = btn.getBoundingClientRect();
  pop.style.left = Math.min(r.left, window.innerWidth - pop.offsetWidth - 8) + "px";
  pop.style.top = r.bottom + 2 + "px";
  setTimeout(() => document.addEventListener("mousedown", outsideMenu, true));
}
function outsideMenu(e) { if (!e.target.closest("#menu-pop") && !e.target.closest("[data-menu]")) closeMenu(); }
function closeMenu() { $("#menu-pop")?.remove(); document.removeEventListener("mousedown", outsideMenu, true); }

function bindToolbar() {
  $$("[data-act]").forEach((b) => b.addEventListener("click", () => ACTIONS[b.dataset.act]()));
  $("#cb-profile").addEventListener("change", (e) => { if (e.target.checked !== S.ui.show_profile) ACTIONS.profile(); });
  $$("[data-menu]").forEach((b) => b.addEventListener("click", () => {
    if ($("#menu-pop")) { closeMenu(); return; }
    openMenu(b, b.dataset.menu);
  }));
  document.addEventListener("keydown", (e) => {
    if (document.querySelector(".modal-back") || document.querySelector(".tut-back")) return;
    const inField = e.target.matches("input, select, textarea");
    const ctrl = e.ctrlKey || e.metaKey;
    const k = e.key.toLowerCase();
    if (e.key === "F1") { e.preventDefault(); return ACTIONS.tutorial(); }
    if (e.key === "Escape") { closeMenu(); if (S.preview !== null) endPreview(); return; }
    if (ctrl && k === "s") { e.preventDefault(); return save(); }
    if (ctrl && k === "o") { e.preventDefault(); return showRackList(); }
    if (ctrl && k === "p") { e.preventDefault(); return exportPdf(); }
    if (ctrl && k === "e" && e.shiftKey) { e.preventDefault(); return export3d(); }
    if (ctrl && k === "e") { e.preventDefault(); return exportImage(); }
    if (ctrl && k === "3") { e.preventDefault(); return setMode3d(true); }
    if (ctrl && k === "r") { e.preventDefault(); return ACTIONS.flip(); }
    if (ctrl && k === "f") { e.preventDefault(); return ACTIONS.search(); }
    if (ctrl && k === "h") { e.preventDefault(); return ACTIONS.history(); }
    if (ctrl && k === "0") { e.preventDefault(); return fit(); }
    if (inField) return;
    if (ctrl && k === "z" && !e.shiftKey) { e.preventDefault(); return undo(); }
    if (ctrl && (k === "y" || (k === "z" && e.shiftKey))) { e.preventDefault(); return redo(); }
    if (e.key === "Delete" && S.ui.selected) { e.preventDefault(); return deleteSelected(); }
  });
}

/* ------------------------------------------------------------------------------------ */
/* Hilfe: Infos und Tutorial                                                              */
/* ------------------------------------------------------------------------------------ */
function showAbout() {
  modal({ title: "Infos über Rack-Planer", body:
    `<h3 style="margin:4px 0 2px">Rack-Planer ${esc(S.meta.version)}</h3>` +
    `<p style="margin-top:0"><b>Webversion</b> · Dateiformat ${esc(S.meta.format)}<br>Entwickler: DAHpublic</p>` +
    "<p>Serverschränke planen: Höheneinheiten, Vorder- und Rückseite, frei drehbare 3D-Ansicht, Einbautiefe, Geräte, Fachböden, " +
    "Beschriftung mit IP-Adressen, Leistung und Wärmelast, Export als PDF, PNG und SVG, Historie früherer Stände.</p>" +
    "<p>Die Schränke liegen auf dem Server (NAS, PHP) und stehen allen im Netzwerk zur Verfügung. Dateien der Desktop-Version " +
    "(<b>.rack.json</b>) lassen sich importieren und wieder herunterladen – das Format ist in allen Versionen gleich.</p>" +
    "<p>Kurze Einführung: <b>Hilfe → Tutorial</b> (F1).</p>" });
}

const RELEASES_URL = "https://github.com/DAHpublic/Rack-Planer/releases";
/**
 * Hilfe → Programm aktualisieren: Stand des automatischen Updates und – nur mit
 * web_update = true in einstellungen.ini – Update von Hand (von GitHub oder per ZIP).
 * Die Daten (Ordner „daten“) und einstellungen.ini bleiben immer unberührt.
 */
async function showUpdate() {
  let info = RackLocal.INFO;
  try { info = Object.assign(RackLocal.INFO, await RackLocal.phpJSON("GET", "info")); } catch (e) { /* letzter Stand */ }
  const au = info.auto_update || {};
  const file = h("input", { type: "file", accept: ".zip,application/zip" });
  const can = info.update_allowed && info.zip && info.app_writable !== false;
  const why = !info.update_allowed ? "Das Update von Hand ist abgeschaltet (einstellungen.ini: web_update = false)." :
    !info.zip ? "Auf dem Server fehlt die PHP-Erweiterung „zip“ (Web Station → PHP-Profil → Erweiterungen)." :
    info.app_writable === false ? "Der Webserver darf den Programmordner nicht ändern (Schreibrechte fehlen)." : "";
  const last = (au.protokoll || [])[0];
  const autoText = !au.installiert ? "Entwicklungsumgebung – kein automatisches Update." :
    au.auto ? `<b>an</b> – jede Nacht zwischen ${esc(au.von)} und ${esc(au.bis)} Uhr (Serverzeit) wird auf GitHub nach einer neuen Version gesucht und sie eingespielt.` :
      "<b>aus</b> (einstellungen.ini: auto_update = false).";
  const warn = [];
  if (au.installiert && au.auto && !info.zip) warn.push("Es fehlt die PHP-Erweiterung „zip“ – das automatische Update kann nichts einspielen.");
  if (au.installiert && au.auto && !au.curl) warn.push("Es fehlt die PHP-Erweiterung „curl“ – GitHub ist nicht erreichbar.");
  if (au.installiert && au.auto && info.app_writable === false) warn.push("Der Webserver darf den Programmordner nicht ändern (Schreibrechte fehlen).");
  const body = h("div", {},
    h("p", { html: `Installiert: <b>Rack-Planer ${esc(S.meta.version)}</b> (Webversion)` }),
    h("p", { html: `Automatisches Update: ${autoText}` }),
    last ? h("p", { class: "hint", text: `Zuletzt: ${fmtDateTime(last.zeit)} – ${last.text}` }) :
      au.installiert && au.auto ? h("p", { class: "hint", text: "Noch nicht geprüft. Damit die Prüfung jede Nacht sicher läuft, im Aufgabenplaner der Synology eine Aufgabe anlegen (Anleitung: web/SYNOLOGY.md)." }) : "",
    ...warn.map((w) => h("p", { class: "warn-text", text: w })),
    can ? h("div", {},
      h("p", { html: `Von Hand: <b>Jetzt aktualisieren</b> holt die neueste Version von GitHub. Oder auf der <a href="${RELEASES_URL}" target="_blank" rel="noopener">Release-Seite</a> ` +
        "<b>Rack-Planer-Web_v…zip</b> herunterladen und hier auswählen. Gespeicherte Schränke, eigene Vorlagen (Ordner <b>daten</b>) und einstellungen.ini bleiben erhalten." }),
      h("div", { class: "form" }, h("label", { text: "Update-Datei:" }), file)) :
      h("p", { class: "hint", text: `${why} Neue Versionen gibt es auf der Release-Seite; von Hand: Inhalt des ZIP in den Rack-Planer-Ordner kopieren und vorhandene Dateien ersetzen – den Ordner „daten“ und einstellungen.ini nicht ersetzen.` }));
  const buttons = [{ label: "Schließen", value: null }];
  if (can && au.installiert) buttons.push({ label: "Jetzt aktualisieren", value: "github" });
  if (can) buttons.push({ label: "ZIP einspielen", primary: true, value: () => file.files[0] || "nofile" });
  const v = await modal({ title: "Programm aktualisieren", body, buttons });
  if (!v) return;
  if (v === "nofile") { await alertBox("Bitte zuerst die Update-Datei (ZIP) auswählen."); return; }
  if (dirty() && !(await confirmBox("Es gibt ungespeicherte Änderungen. Nach dem Update lädt die Seite neu – vorher speichern?", "Speichern und fortfahren"))) return;
  if (dirty() && !(await save())) return;
  let r;
  if (v === "github") {
    status("Suche auf GitHub nach einer neuen Version …", 120000);
    try { r = await RackLocal.phpJSON("POST", "update/jetzt"); } catch (e) { status(""); await alertBox(`Update fehlgeschlagen:\n${e.message}`); return; }
    status("");
    if (r.status !== "aktualisiert") { await alertBox(r.text); return; }
  } else {
    const fd = new FormData();
    fd.append("datei", v);
    status("Update wird eingespielt …", 60000);
    try { r = await RackLocal.phpJSON("POST", "update", fd); } catch (e) { await alertBox(`Update fehlgeschlagen:\n${e.message}`); return; }
  }
  await alertBox(`Update eingespielt: ${r.old_version} → ${r.new_version}${r.files ? ` (${r.files} Dateien)` : ""}. Die Seite wird jetzt neu geladen.`);
  location.reload();
}

const TUTORIAL = [
  ["Willkommen beim Rack-Planer! 👋", "In wenigen Schritten lernst du alle wichtigen Funktionen kennen.<br><br>Weiter mit <b>Enter</b> oder <b>→</b>, zurück mit <b>←</b>, beenden mit <b>Esc</b>.", null],
  ["Deine Schränke", "Alle Schränke liegen zentral auf dem NAS. Unter <b>Schränke …</b> öffnest, löschst oder importierst du sie – jeder im Netzwerk sieht dieselben Schränke.", '[data-act="open"]'],
  ["Dein Schrank", "Hier legst du <b>Bezeichnung</b>, <b>Höhe</b> in HE, die nutzbare <b>Einbautiefe</b> und den <b>aktuellen Stand</b> fest. Das Datum erscheint auf jedem Export unter dem Titel.", "#rack-box"],
  ["Geräte-Vorlagen", "Über 70 Geräte mit echten Maßen, Leistung und Tiefe. <b>Strg + F</b> sucht, <b>Doppelklick</b> baut ein. <span style='color:#e8800c'>Orange</span> = nicht rackfähig, kommt auf einen Fachboden. Eigene Geräte kannst du über „Als Vorlage speichern“ für alle hinterlegen.", "#tpl-box"],
  ["Bauen per Drag & Drop", "Ziehe Geräte mit der Maus an ihren Platz: <span style='color:#2ecc71'>grün</span> = frei, <span style='color:#e74c3c'>rot</span> = belegt. <b>Strg + Mausrad</b> zoomt, <b>Entf</b> entfernt.", "#viewwrap"],
  ["Vorder- und Rückseite", "Schalte zwischen den Seiten um (<b>Strg + R</b>). Neue Geräte werden auf der Seite montiert, die du gerade siehst. Geräte der Gegenseite sind <i>gestrichelt</i> angedeutet – mit der freien Tiefe. Doppelklick darauf wechselt die Seite.", ["#tb-front", "#tb-rear"]],
  ["Tiefe im Blick", "Die <b>Seitenansicht</b> rechts neben dem Schrank zeigt die Tiefe als Kapazität – immer vorne links, hinten rechts. Beispiel: 800 mm Schrank, hinten 50 mm Steckdosenleiste – vorne bleiben 750 mm.", "#rackview .profile"],
  ["Seitenansicht ein- und ausblenden ☑", "Mit dem Häkchen <b>„Seitenansicht“</b> oben in der Leiste blendest du die Seitenansicht ein oder aus – zum Beispiel, wenn du mehr Platz für den Schrank möchtest. Dasselbe geht über <b>Ansicht → Seitenansicht</b>.", "#tb-profile"],
  ["Die 3D-Ansicht 🧊", "Mit <b>3D</b> in der Leiste (<b>Strg + 3</b>) siehst du deinen Schrank räumlich; <b>Vorderseite</b> und <b>Rückseite</b> bringen dich zurück. In 3D dreht die <b>linke Maustaste</b>, auf einem Gerät verschiebt sie es nach oben oder unten – Geräte auf einem Fachboden auch auf einen anderen Fachboden. <b>Mausrad</b> zoomt, <b>mittlere Maustaste</b> oder <b>Umschalt</b> verschiebt die Ansicht, <b>Doppelklick</b> holt ein Gerät heran.", "#tb-3d"],
  ["Konflikte erkennen ⚠", "Reicht die Tiefe nicht oder blockieren <b>Einbauschienen</b> (USV, Server, Rack-NAS) die Gegenseite, wird das betroffene Gerät <span style='color:#e5413a'>rot</span> markiert und ein Banner erklärt das Problem.", "#viewwrap"],
  ["Eigenschaften", "Name, bis zu 5 IP-Adressen, Höhe, <b>Tiefe</b>, <b>Montageseite</b> und <b>Schienen</b> des ausgewählten Geräts.", "#props"],
  ["Alle Geräte auf einen Blick", "Die Liste zeigt jedes Gerät mit HE, Seite, IP und Leistung. Unten in der Statusleiste stehen Belegung, Leistung und Wärmelast.", "#list-box"],
  ["Zeitreise mit der Historie 🕘", "Im Tab <b>„Historie“</b> findest du frühere Stände. Ein Klick zeigt den Stand im Schrank an (nur ansehen), „Wiederherstellen“ übernimmt ihn, „Als eigene Datei“ lädt ihn separat herunter.", "#list-box"],
  ["Exportieren", "Unter <b>Exportieren</b>: <b>als PDF</b> mit Vorder- und/oder Rückseite (nebeneinander oder je auf einer eigenen Seite) oder <b>als Bild</b> einer Seite (PNG oder SVG) – mit Titel und Stand, auf Wunsch mit maximaler Strom- und Wärmelast. Die <b>3D-Ansicht</b> lässt sich als PNG exportieren.", "#tb-export"],
  ["Speichern", "<b>Strg + S</b> speichert den Schrank auf dem NAS – alles zu einem Schrank steckt in einem Datensatz, auch die Historie. Änderst du einen gespeicherten Schrank, fragt der Planer, ob eine Historie angelegt werden soll. Im Menü findest du Import und Download der <b>.rack.json</b>-Datei für die Desktop-Version. <b>Strg + Z</b> macht jeden Schritt rückgängig.", "#tb-save"],
  ["Geschafft! 🎉", "Viel Spaß beim Planen. Das Tutorial findest du jederzeit unter <b>Hilfe → Tutorial</b> (F1).", null],
];

function startTutorial() {
  if ($(".tut-back")) return;
  if (S.mode3d) setMode3d(false);            // Tutorial beginnt in der 2D-Ansicht
  let i = 0;
  const back = h("div", { class: "tut-back" });
  const hole = h("div", { class: "tut-hole none" });
  const bubble = h("div", { class: "tut-bubble" });
  back.append(hole);
  document.body.append(back, bubble);
  const finish = () => { back.remove(); bubble.remove(); document.removeEventListener("keydown", onKey, true); window.removeEventListener("resize", show); };
  const show = () => {
    const [title, text, target] = TUTORIAL[i];
    const sels = Array.isArray(target) ? target : target ? [target] : [];
    const rects = sels.map((s) => $(s)?.getBoundingClientRect()).filter((r) => r && r.width > 0);
    let r = null;
    if (rects.length) {
      const l = Math.min(...rects.map((x) => x.left)), t = Math.min(...rects.map((x) => x.top));
      const rr = Math.max(...rects.map((x) => x.right)), b = Math.max(...rects.map((x) => x.bottom));
      r = { left: Math.max(4, l - 6), top: Math.max(4, t - 6), right: Math.min(window.innerWidth - 4, rr + 6), bottom: Math.min(window.innerHeight - 4, b + 6) };
    }
    if (r) {
      hole.className = "tut-hole";
      Object.assign(hole.style, { left: r.left + "px", top: r.top + "px", width: r.right - r.left + "px", height: r.bottom - r.top + "px" });
    } else { hole.className = "tut-hole none"; hole.removeAttribute("style"); }
    bubble.innerHTML = "";
    bubble.append(h("h3", { text: title }), h("div", { html: text }),
      h("div", { class: "nav" }, h("span", { class: "count", text: `${i + 1} / ${TUTORIAL.length}` }),
        h("button", { class: "btn", text: "Beenden", onclick: finish }),
        i > 0 ? h("button", { class: "btn", text: "Zurück", onclick: () => { i--; show(); } }) : null,
        h("button", { class: "btn primary", text: i === TUTORIAL.length - 1 ? "Fertig" : "Weiter", onclick: next })));
    const bw = bubble.offsetWidth, bh = bubble.offsetHeight, W = window.innerWidth, H = window.innerHeight;
    let x = (W - bw) / 2, y = (H - bh) / 2;
    if (r) {
      if (r.right + 16 + bw < W) { x = r.right + 16; y = r.top; }
      else if (r.left - 16 - bw > 0) { x = r.left - 16 - bw; y = r.top; }
      else if (r.bottom + 16 + bh < H) { x = Math.min(Math.max(8, r.left), W - bw - 8); y = r.bottom + 16; }
      else { x = Math.min(Math.max(8, r.left), W - bw - 8); y = Math.max(8, r.top - 16 - bh); }
      y = Math.min(Math.max(8, y), H - bh - 8);
    }
    bubble.style.left = x + "px"; bubble.style.top = y + "px";
  };
  const next = () => { if (i >= TUTORIAL.length - 1) finish(); else { i++; show(); } };
  const onKey = (e) => {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(); }
    else if (e.key === "Enter" || e.key === "ArrowRight") { e.preventDefault(); e.stopPropagation(); next(); }
    else if (e.key === "ArrowLeft" && i > 0) { e.preventDefault(); e.stopPropagation(); i--; show(); }
  };
  back.addEventListener("click", next);
  document.addEventListener("keydown", onKey, true);
  window.addEventListener("resize", show);
  show();
}

/* ------------------------------------------------------------------------------------ */
/* Start                                                                                  */
/* ------------------------------------------------------------------------------------ */
async function main() {
  try {
    await RackLocal.init();
    S.meta = await getJSON("/api/meta");
  } catch (e) {
    $("#loading").textContent = `Der Rack-Planer kann nicht starten: ${e.message || e}`;
    return;
  }
  $("#p-cat").append(...S.meta.categories.map((c) => h("option", { value: c, text: c })));
  bindInputs();
  bindToolbar();
  init3d();
  await loadTemplates();
  if (!serverSave()) {
    await newRack(true);
    status("Speichern auf dem Server ist abgeschaltet: Speichern lädt den Schrank als .rack.json-Datei herunter, Öffnen liest eine solche Datei ein.", 12000);
    return;
  }
  const m = /^#\/rack\/([\w-]+)/.exec(location.hash);
  let last = null;
  try { last = localStorage.getItem("rackplaner.last"); } catch (e) { /* */ }
  let opened = false;
  if (m) opened = await openRack(m[1], true);
  else if (last) {
    try { await getJSON(`/api/racks/${last}`); opened = await openRack(last, true); } catch (e) { opened = false; }
  }
  if (!opened) {
    await newRack(true);
    const racks = await getJSON("/api/racks").catch(() => []);
    if (racks.length) showRackList();
    else status("Neu hier? Hilfe → Tutorial (F1) stellt alle Funktionen kurz vor.", 10000);
  }
}

main();
