/* Schnittstelle der Oberfläche (app.js) zu Rechenkern und Server.
 *
 * Die Oberfläche spricht weiter die Adressen /api/… an. Alles, was gerechnet wird (Schritte,
 * Zeichnung, Exporte, Prüfung importierter Dateien), erledigt der Browser selbst mit core.js,
 * engine.js und export.js. Nur das Speichern (Schränke, eigene Vorlagen) und das Update gehen
 * an den Server: api.php im selben Ordner. Antworten werden als Response-Objekte geliefert,
 * damit app.js nicht unterscheiden muss, woher sie kommen.
 */
(function (root) {
  "use strict";
  const C = root.RackCore, E = root.RackEngine, X = root.RackExport;

  const INFO = { version: "", zip: false, update_allowed: false, server_save: true, auto_update: null };
  const OWN_GROUP = "Eigene Vorlagen";
  let ready = null;

  /** Adresse von api.php (relativ, damit der Ordner beliebig heißen darf). */
  function phpUrl(path, method) {
    const q = `api.php?p=${encodeURIComponent(path)}`;
    return method && method !== "GET" && method !== "POST" ? `${q}&m=${method}` : q;
  }
  async function php(method, path, body) {
    const opt = { method: method === "GET" ? "GET" : "POST", headers: { "Cache-Control": "no-cache" } };
    if (body instanceof FormData) opt.body = body;
    else if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    let res;
    try { res = await fetch(phpUrl(path, method), opt); } catch (e) { throw new Error("Der Server ist nicht erreichbar."); }
    return res;
  }
  async function phpJSON(method, path, body) {
    const res = await php(method, path, body);
    let j = null;
    try { j = await res.json(); } catch (e) { /* */ }
    if (!res.ok || j === null) {
      const err = new Error(j && j.detail ? j.detail : res.status === 404 && j === null ?
        "api.php wurde nicht gefunden – ist PHP für diesen Ordner aktiviert?" : `Fehler ${res.status} – PHP liefert keine gültige Antwort.`);
      err.status = res.status; err.body = j;
      throw err;
    }
    return j;
  }

  const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
  function fileName(name, suffix) {
    const base = String(name || "Rack").trim().replace(/[\\/:*?"<>|\x00-\x1f]+/g, "_") || "Rack";
    return base.slice(0, 120) + suffix;
  }
  const download = (blob, name) => new Response(blob, { headers: {
    "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(name)}`, "Content-Type": blob.type || "application/octet-stream" } });
  const docBlob = (doc) => new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });

  async function loadFonts() {
    const get = async (f) => {
      const r = await fetch(`app/fonts/${f}`);
      if (!r.ok) throw new Error(`Schrift ${f} fehlt`);
      return r.arrayBuffer();
    };
    const [reg, bold] = await Promise.all([get("DejaVuSans.ttf"), get("DejaVuSans-Bold.ttf")]);
    root.RackText.setFontData(reg, bold);
    X.setFonts(reg, bold);
  }
  function init() {
    if (!ready) {
      ready = (async () => {
        const [info] = await Promise.all([phpJSON("GET", "info"), loadFonts()]);
        Object.assign(INFO, info);
        // Automatisches Update fällig (nachts im Zeitfenster)? Im Hintergrund anstoßen – die Seite wartet nicht darauf.
        if (info.auto_update && info.auto_update.faellig) fetch(phpUrl("autoupdate"), { cache: "no-store" }).catch(() => {});
        // eingebaute Vorlagen für die Migration älterer Dateien
        const tpls = await phpJSON("GET", "templates");
        C.setTemplates(tpls.filter((t) => t.builtin));
      })();
      ready.catch(() => { ready = null; });
    }
    return ready;
  }

  function meta() {
    return { app: C.APP_NAME, version: INFO.version, format: C.FORMAT_VERSION, categories: C.CATEGORIES,
      colors: C.CATEGORY_COLORS, depth_presets: C.DEPTH_PRESETS, height_presets: [6, 9, 12, 15, 22, 42, 47],
      max_ips: C.MAX_IPS, shelf_width_mm: C.SHELF_WIDTH_MM, file_suffix: C.FILE_SUFFIX, own_group: OWN_GROUP,
      new_document: C.newDocument(), update_allowed: !!INFO.update_allowed, zip: !!INFO.zip,
      server_save: INFO.server_save !== false, auto_update: INFO.auto_update || null };
  }

  async function exportFile(body) {
    let rack;
    try { rack = C.Rack.fromDict(C.clone(body.rack)); } catch (e) { throw new Error(`Ungültiger Schrank: ${e.message}`); }
    const base = fileName(String(body.basename || rack.name), "");
    if (body.kind === "pdf") return download(await X.exportPdf(rack, body.sides || [C.FRONT], !!body.power, !!body.separate, INFO.version), `${base}.pdf`);
    const side = C.SIDES.includes(body.side) ? body.side : C.FRONT;
    const suffix = side === C.FRONT ? " Vorderseite" : " Rückseite";
    if (body.kind === "png") return download(await X.exportPng(rack, side, Number(body.scale) || 2, !!body.transparent, !!body.power), `${base}${suffix}.png`);
    if (body.kind === "svg") return download(X.exportSvg(rack, side, !!body.power, INFO.version), `${base}${suffix}.svg`);
    throw new Error("Unbekanntes Exportformat.");
  }

  /** Anfrage beantworten; liefert eine Response (auch für Fehler des Servers). */
  async function handle(method, url, body) {
    await init();
    const path = url.replace(/^\/api\//, "");
    try {
      if (path === "meta") return json(meta());
      if (path === "state" && method === "POST") return json(E.state(body));
      if (path === "export" && method === "POST") return await exportFile(body);
      if (path === "file" && method === "POST") {
        const doc = C.documentForRack(body.rack);
        const name = String(body.filename || "") || fileName(doc.name, C.FILE_SUFFIX);
        return download(docBlob(doc), fileName(name.replace(/\.rack\.json$/, ""), C.FILE_SUFFIX));
      }
      if (path === "racks" && method === "POST") {
        // Neuer Schrank oder Import: Datei hier prüfen und ergänzen (ältere Formate), dann speichern
        let res;
        try { res = C.readDocument(body.document); } catch (e) { throw new Error(`Die Datei konnte nicht gelesen werden: ${e.message}`); }
        const rec = await phpJSON("POST", "racks", { document: res.doc });
        return json({ ...rec, notes: res.notes });
      }
      const fileMatch = /^racks\/([\w-]+)\/file$/.exec(path);
      if (fileMatch) {
        const rec = await phpJSON("GET", `racks/${fileMatch[1]}`);
        const { doc } = C.readDocument(rec.document);
        return download(docBlob(doc), fileName(doc.name, C.FILE_SUFFIX));
      }
      if (path === "racks" && method === "GET") return json(await phpJSON("GET", "racks"));
      if (path === "templates" && method === "GET") {
        const list = await phpJSON("GET", "templates");
        C.setTemplates(list.filter((t) => t.builtin));
        return json(list);
      }
      // übrige Adressen (Schränke, Vorlagen, Update) unverändert an api.php
      const res = await php(method, path, body);
      return res;
    } catch (e) {
      if (e.status) return json(e.body || { detail: e.message }, e.status);
      return json({ detail: e.message || String(e) }, e instanceof E.OpError ? 400 : 500);
    }
  }

  root.RackLocal = { init, handle, phpJSON, INFO };
})(typeof self !== "undefined" ? self : this);
