// Browsertest der Webversion mit abgeschaltetem Speichern auf dem Server
// (einstellungen.ini: server_speichern = false). Erwartet den Server unter BASE.
// Aufruf: node tests/e2e/web_e2e_dateimodus.js <BASE> [shots-dir]
"use strict";
const { chromium } = require("playwright");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8098/";
const SHOTS = process.argv[3] || "";
const errors = [];
let step = "";
const ok = (cond, msg) => { if (!cond) throw new Error(`${step}: ${msg}`); console.log(`  ✓ ${msg}`); };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ acceptDownloads: true, viewport: { width: 1500, height: 950 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/403/.test(m.text())) errors.push(`console: ${m.text()}`); });
  try {
    step = "Start";
    await page.goto(BASE);
    await page.waitForSelector("#rackview svg", { timeout: 20000 });
    const info = await (await page.request.get(BASE + "api.php?p=info")).json();
    ok(info.server_save === false, "Server meldet: Speichern abgeschaltet");
    ok(info.update_allowed === false, "Update von Hand standardmäßig aus");

    step = "Speichern als Datei";
    await page.fill("#tpl-search", "RS2423+");
    await page.press("#tpl-search", "Enter");
    await page.waitForFunction(() => document.querySelectorAll("#devlist tr").length === 1);
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 15000 }), page.keyboard.press("Control+s")]);
    const name = dl.suggestedFilename();
    const doc = JSON.parse(fs.readFileSync(await dl.path(), "utf-8"));
    ok(name.endsWith(".rack.json"), `Strg + S lädt „${name}“ herunter`);
    ok(doc.items.length === 1 && doc.history && doc.saved_at, "Datei enthält Schrank, Historie und Speicherzeit");
    const racks = await (await page.request.get(BASE + "api.php?p=racks")).json();
    ok(Array.isArray(racks) && racks.length === 0, "auf dem Server liegt nichts");
    const res = await page.request.post(BASE + "api.php?p=racks", { data: { document: doc } });
    ok(res.status() === 403, "Server lehnt Speichern ab (403)");
    ok(await page.locator("#p-save-tpl").isDisabled(), "„Als Vorlage speichern“ ist gesperrt");

    step = "Datei öffnen";
    doc.name = "Aus Datei";
    const tmp = path.join(os.tmpdir(), "dateimodus-test.rack.json");
    fs.writeFileSync(tmp, JSON.stringify(doc));
    await page.click('[data-act="new"]').catch(() => {});
    if (await page.locator(".modal").count()) await page.locator(".modal .buttons button", { hasText: "Verwerfen" }).click();
    await page.setInputFiles("#file-input", tmp);
    await page.waitForFunction(() => /Aus Datei/.test(document.querySelector("#doc-title").textContent));
    ok(!(await page.locator("#doc-title").textContent()).includes("noch nicht gespeichert"), "Datei geöffnet, gilt als gespeichert");

    ok(errors.length === 0, "keine Fehler in der Browser-Konsole" + (errors.length ? ":\n" + errors.join("\n") : ""));
    console.log("ALLES OK");
  } catch (e) {
    console.error("FEHLER:", e.message);
    if (errors.length) console.error(errors.join("\n"));
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "fehler-dateimodus.png") }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
