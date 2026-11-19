/* Export im Browser: PDF (A4, Vorder- und/oder Rückseite), PNG und SVG (eine Seite).
 *
 * Wie in der Desktop-Version wird nur der Schrank mit Geräten und Beschriftung exportiert
 * (helle, druckfreundliche Farben, ohne Hinweise, Auswahl, Gegenseite und Seitenansicht).
 * Unter dem Titel steht der „Aktuelle Stand“, auf Wunsch unter dem Schrank die maximale
 * Strom- und Wärmelast. PDF über jsPDF + svg2pdf.js (Vektor, Schrift DejaVu Sans eingebettet),
 * PNG über ein Canvas aus derselben SVG-Zeichnung.
 */
(function (root) {
  "use strict";
  const C = root.RackCore, R = root.RackRender;
  const EXPORT_FONT = "DejaVu Sans";
  const A4_PT = [595.28, 841.89];
  const MARGIN_PT = 12 * 72 / 25.4;
  const GAP = 40.0;
  const PNG_SCALES = [1, 2, 4];
  const fonts = { regular: null, bold: null };      // ArrayBuffer der TTF-Dateien

  function b64(buf) {
    const bytes = new Uint8Array(buf);
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  }

  function sideSvg(rack, side, power) {
    const [svg, geo] = R.render(rack, { side, selected: "", showOther: false, profile: false, sideLabel: true,
      footer: power ? rack.powerSummary() : "", ink: "print", interactive: false, fontFamily: EXPORT_FONT });
    return [svg, geo.viewbox[2], geo.viewbox[3]];
  }

  function exportSvg(rack, side, power, version) {
    let [svg] = sideSvg(rack, side, power);
    const vb = /viewBox="([^"]+)"/.exec(svg)[1].split(" ");
    const head = `<title>${R.escape(rack.name)} – ${C.SIDE_LABEL[side]}</title><desc>Erstellt mit Rack-Planer ${R.escape(version)} (Webversion)</desc>` +
      `<rect x="${vb[0]}" y="${vb[1]}" width="${vb[2]}" height="${vb[3]}" fill="#ffffff"/>`;
    svg = svg.replace("<defs>", head + "<defs>");
    return new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n' + svg], { type: "image/svg+xml" });
  }

  function exportPng(rack, side, scale, transparent, power) {
    let [svg, w, h] = sideSvg(rack, side, power);
    if (!PNG_SCALES.includes(scale)) scale = 2;
    // Schrift in die Grafik einbetten – ein als Bild geladenes SVG darf keine Dateien nachladen
    const style = `<style>@font-face{font-family:"${EXPORT_FONT}";src:url(data:font/ttf;base64,${b64(fonts.regular)}) format("truetype");font-weight:normal}` +
      `@font-face{font-family:"${EXPORT_FONT}";src:url(data:font/ttf;base64,${b64(fonts.bold)}) format("truetype");font-weight:bold}</style>`;
    svg = svg.replace("<defs>", style + "<defs>");
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(w * scale);
        canvas.height = Math.round(h * scale);
        const ctx = canvas.getContext("2d");
        if (!transparent) { ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, canvas.width, canvas.height); }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG konnte nicht erzeugt werden."))), "image/png");
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Die Zeichnung konnte nicht gerastert werden.")); };
      img.src = url;
    });
  }

  /** Lage der Schrankseiten auf einer A4-Seite (hoch oder quer – je nachdem, wo der Inhalt größer wird). */
  function pageLayout(group) {
    const totalW = group.reduce((s, [, w]) => s + w, 0) + GAP * (group.length - 1);
    const totalH = Math.max(...group.map(([, , h]) => h));
    let best = null;
    for (const [pw, ph] of [A4_PT, [A4_PT[1], A4_PT[0]]]) {
      const aw = pw - 2 * MARGIN_PT, ah = ph - 2 * MARGIN_PT;
      const scale = Math.min(aw / totalW, ah / totalH);
      if (best === null || scale > best[0] + 1e-9) best = [scale, pw, ph];
    }
    const [scale, pw, ph] = best;
    let x = MARGIN_PT + (pw - 2 * MARGIN_PT - totalW * scale) / 2;
    const y = MARGIN_PT;
    const places = [];
    for (const [svg, w, h] of group) {
      places.push({ svg, x, y, w: w * scale, h: h * scale });
      x += (w + GAP) * scale;
    }
    return { pw, ph, places };
  }

  async function exportPdf(rack, sides, power, separate, version) {
    const { jsPDF } = root.jspdf;
    sides = (sides || []).filter((s) => C.SIDES.includes(s));
    if (!sides.length) sides = [C.FRONT];
    const drawings = sides.map((s) => sideSvg(rack, s, power));
    const groups = separate ? drawings.map((d) => [d]) : [drawings];
    const pages = groups.map(pageLayout);
    const first = pages[0];
    const doc = new jsPDF({ unit: "pt", format: [first.pw, first.ph], orientation: first.pw > first.ph ? "landscape" : "portrait", compress: true });
    doc.addFileToVFS("DejaVuSans.ttf", b64(fonts.regular));
    doc.addFont("DejaVuSans.ttf", EXPORT_FONT, "normal");
    doc.addFileToVFS("DejaVuSans-Bold.ttf", b64(fonts.bold));
    doc.addFont("DejaVuSans-Bold.ttf", EXPORT_FONT, "bold");
    doc.setFont(EXPORT_FONT, "normal");
    doc.setProperties({ title: `${rack.name} – Rackplan`, creator: `Rack-Planer ${version} (Webversion)` });
    const parser = new DOMParser();
    for (let i = 0; i < pages.length; i++) {
      const p = pages[i];
      if (i) doc.addPage([p.pw, p.ph], p.pw > p.ph ? "landscape" : "portrait");
      for (const pl of p.places) {
        const el = parser.parseFromString(pl.svg, "image/svg+xml").documentElement;
        // svg2pdf braucht das Element im Dokument (für Stil-Berechnungen)
        const holder = document.createElement("div");
        holder.style.cssText = "position:absolute;left:-10000px;top:0;width:0;height:0;overflow:hidden";
        holder.append(el);
        document.body.append(holder);
        try { await doc.svg(el, { x: pl.x, y: pl.y, width: pl.w, height: pl.h }); }
        finally { holder.remove(); }
      }
    }
    return doc.output("blob");
  }

  root.RackExport = {
    setFonts(regular, bold) { fonts.regular = regular; fonts.bold = bold; },
    sideSvg, exportSvg, exportPng, exportPdf, pageLayout,
  };
})(typeof self !== "undefined" ? self : this);
