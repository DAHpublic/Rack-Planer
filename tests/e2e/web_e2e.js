// Browsertest der Webversion (HTML/PHP): startet nichts selbst – erwartet den Server unter
// BASE (z. B. php -S 127.0.0.1:8099 -t <ordner>). Aufruf: node tests/e2e/web_e2e.js <BASE> [update.zip] [shots-dir]
"use strict";
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8099/";
const UPDATE_ZIP = process.argv[3] || "";
const SHOTS = process.argv[4] || "";
const errors = [];
let step = "";
const ok = (cond, msg) => { if (!cond) throw new Error(`${step}: ${msg}`); console.log(`  ✓ ${msg}`); };

async function clickButton(page, text) {
  await page.locator(".modal .buttons button", { hasText: text }).first().click();
}
async function menu(page, menuName, itemText) {
  await page.click(`[data-menu="${menuName}"]`);
  await page.locator(".menu-pop, .popup, .dropdown, [role=menu]").locator(`text=${itemText}`).first().click();
}
async function download(page, fn) {
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 30000 }), fn()]);
  const p = await dl.path();
  return { name: dl.suggestedFilename(), data: fs.readFileSync(p) };
}
const rows = (page) => page.locator("#devlist tr").count();

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ acceptDownloads: true, viewport: { width: 1500, height: 950 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
  try {
    step = "Start";
    const t0 = Date.now();
    await page.goto(BASE);
    await page.waitForSelector("#rackview svg", { timeout: 20000 });
    ok(await page.locator("#loading").isHidden(), `Oberfläche geladen (${Date.now() - t0} ms)`);
    ok((await page.locator("#tpl-tree .tpl").count()) > 50, "Vorlagen geladen");

    step = "Vorlage hinzufügen";
    await page.fill("#tpl-search", "RS2423+");
    await page.press("#tpl-search", "Enter");
    await page.waitForFunction(() => document.querySelectorAll("#devlist tr").length === 1);
    ok(true, "RackStation per Suche + Enter eingefügt");
    const t1 = Date.now();
    await page.fill("#tpl-search", "Server 2 HE");
    await page.press("#tpl-search", "Enter");
    await page.waitForFunction(() => document.querySelectorAll("#devlist tr").length === 2);
    ok(Date.now() - t1 < 1500, `Zweites Gerät ohne Verzögerung (${Date.now() - t1} ms)`);

    step = "Nicht rackfähig → Fachboden";
    await page.fill("#tpl-search", "DS923+");
    await page.press("#tpl-search", "Enter");
    await page.waitForSelector(".modal");
    await clickButton(page, "Neuen Fachboden einbauen");
    await page.waitForFunction(() => document.querySelectorAll("#devlist tr").length === 4);
    ok(true, "Fachboden + DS923+ eingebaut");

    step = "Eigenschaften";
    await page.locator("#devlist tr", { hasText: "RackStation" }).click();
    await page.waitForFunction(() => document.querySelector("#p-model").textContent.includes("RackStation"));
    await page.fill("#p-name", "NAS-01");
    await page.fill("#p-ip", "192.168.1.10");
    await page.waitForTimeout(700);
    await page.locator("#devlist tr", { hasText: "Server 2 HE" }).click();
    await page.waitForFunction(() => document.querySelector("#p-model").textContent.includes("Server 2 HE"));
    await page.fill("#p-ip", "192.168.1.10/24");
    await page.waitForTimeout(800);
    ok(await page.locator(".banner.err").count() === 1, "Banner doppelte IP erscheint");
    const viewTop = await page.locator("#viewwrap").boundingBox();
    ok(viewTop.y < 80, `Banner verschiebt die Ansicht nicht (Ansicht oben bei ${Math.round(viewTop.y)} px)`);

    step = "Speichern";
    await page.keyboard.press("Control+s");
    await page.waitForFunction(() => /Gespeichert/.test(document.querySelector("#status-msg").textContent));
    const racks = await (await page.request.get(BASE + "api.php?p=racks")).json();
    ok(racks.length === 1 && racks[0].devices === 3, "Schrank auf dem Server (3 Geräte)");

    step = "Historie";
    await page.fill("#r-name", "Hauptschrank");
    await page.press("#r-name", "Tab");
    const hist = page.locator(".modal", { hasText: "Historie anlegen" });
    await hist.waitFor({ timeout: 5000 });
    await clickButton(page, "Historie anlegen");
    await page.waitForTimeout(500);
    await page.keyboard.press("Control+s");
    await page.waitForFunction(() => /Historie/.test(document.querySelector("#status-msg").textContent));
    const rec = await (await page.request.get(BASE + "api.php?p=racks/" + racks[0].id)).json();
    ok(rec.document.history.entries.length === 1 && rec.document.name === "Hauptschrank", "früherer Stand in der Historie");

    step = "Export";
    let d = await download(page, async () => { await page.keyboard.press("Control+p"); await page.waitForSelector(".modal"); await clickButton(page, "Exportieren"); });
    ok(d.data.slice(0, 5).toString() === "%PDF-" && d.data.length > 5000, `PDF ${d.name} (${d.data.length} Bytes)`);
    if (SHOTS) fs.writeFileSync(path.join(SHOTS, "export.pdf"), d.data);
    d = await download(page, async () => { await page.keyboard.press("Control+e"); await page.waitForSelector(".modal"); await clickButton(page, "Exportieren"); });
    ok(d.data.slice(1, 4).toString() === "PNG" && d.data.length > 5000, `PNG ${d.name} (${d.data.length} Bytes)`);
    if (SHOTS) fs.writeFileSync(path.join(SHOTS, "export.png"), d.data);
    d = await download(page, async () => {
      await page.keyboard.press("Control+e"); await page.waitForSelector(".modal");
      await page.selectOption(".modal select", "svg"); await clickButton(page, "Exportieren");
    });
    ok(d.data.toString().includes("<svg") && d.name.endsWith(".svg"), `SVG ${d.name}`);
    d = await download(page, async () => { await menu(page, "save", "Als Datei herunterladen"); });
    const file = JSON.parse(d.data.toString());
    ok(file.format === 2 && file.items.length === 4 && file.history.entries.length === 1, `Projektdatei ${d.name}`);

    step = "3D";
    await page.click("#tb-3d");
    await page.waitForTimeout(800);
    ok(await page.locator("#view3d canvas").count() > 0, "3D-Ansicht sichtbar");
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "web-3d.png") });
    const before = await page.locator("#view3d").boundingBox();
    await page.click("#tb-front");
    await page.waitForTimeout(300);
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "web-2d.png") });
    ok(Math.abs(before.y - (await page.locator("#viewwrap").boundingBox()).y) < 2, "Banner liegen über der 3D-Ansicht");

    step = "Neu laden";
    await page.reload();
    await page.waitForSelector("#rackview svg");
    await page.waitForFunction(() => document.querySelectorAll("#devlist tr").length === 4);
    ok((await page.inputValue("#r-name")) === "Hauptschrank", "zuletzt geöffneter Schrank wieder da");

    step = "Import";
    const old = { app: "Rack-Planer", version: 1, name: "Alt 1.0", height_u: 12, items: [
      { name: "NAS", category: "NAS", model: "RackStation RS2423+", height_u: 2, position: 5, uid: "1".repeat(32) }] };
    await page.setInputFiles("#file-input", { name: "alt.rack.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(old)) });
    await page.locator(".modal", { hasText: "älteren Version" }).waitFor();
    await clickButton(page, "OK");
    await page.waitForFunction(() => document.querySelector("#r-name").value === "Alt 1.0");
    const r2 = await (await page.request.get(BASE + "api.php?p=racks")).json();
    const imp = r2.find((r) => r.name === "Alt 1.0");
    const impRec = await (await page.request.get(BASE + "api.php?p=racks/" + imp.id)).json();
    ok(impRec.document.items[0].depth_mm === 724 && impRec.document.items[0].rails === true, "Import ergänzt Tiefe/Schienen aus Vorlagen");

    step = "Eigene Vorlage";
    await page.locator("#devlist tr", { hasText: "NAS" }).click();
    await page.waitForFunction(() => document.querySelector("#p-model").textContent.includes("RackStation"));
    await page.click("#p-save-tpl");
    await page.waitForSelector(".modal input");
    await page.fill(".modal input", "Mein NAS");
    await clickButton(page, "OK");
    await page.waitForFunction(() => [...document.querySelectorAll("#tpl-tree .tpl")].some((e) => e.textContent.includes("Mein NAS")));
    ok(true, "eigene Vorlage gespeichert und gelistet");

    step = "Schrankliste";
    await page.click('[data-act="open"]');
    await page.waitForSelector(".modal table.racks");
    ok(await page.locator(".modal table.racks tbody tr").count() === 2, "zwei Schränke in der Liste");
    await clickButton(page, "Schließen");

    if (UPDATE_ZIP) {
      step = "Update";
      await menu(page, "help", "Programm aktualisieren");
      await page.waitForSelector(".modal input[type=file]");
      await page.setInputFiles(".modal input[type=file]", UPDATE_ZIP);
      await clickButton(page, "Update einspielen");
      await page.locator(".modal", { hasText: "Update eingespielt" }).waitFor({ timeout: 20000 });
      ok(true, (await page.locator(".modal .body").textContent()).trim());
      await Promise.all([page.waitForNavigation(), clickButton(page, "OK")]);
      await page.waitForSelector("#rackview svg");
      const r3 = await (await page.request.get(BASE + "api.php?p=racks")).json();
      ok(r3.length === 2, "Daten nach dem Update unverändert");
    }
    ok(errors.length === 0, "keine Fehler in der Browser-Konsole" + (errors.length ? ":\n" + errors.join("\n") : ""));
    console.log("ALLES OK");
  } catch (e) {
    console.error("FEHLER:", e.message);
    if (errors.length) console.error(errors.join("\n"));
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "fehler.png") }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
