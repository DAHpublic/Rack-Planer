// Hilfsprozess für tests/test_web_core.py: liest JSON-Zeilen {templates, body} und antwortet
// mit dem Ergebnis von RackEngine.state(body) (wie früher POST /api/state).
"use strict";
const fs = require("fs");
const path = require("path");
const app = path.join(__dirname, "..", "..", "web", "app");
const T = require(path.join(app, "textfit.js"));
const C = require(path.join(app, "core.js"));
const E = require(path.join(app, "engine.js"));
T.setFontData(fs.readFileSync(path.join(app, "fonts", "DejaVuSans.ttf")), fs.readFileSync(path.join(app, "fonts", "DejaVuSans-Bold.ttf")));
const rl = require("readline").createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const msg = JSON.parse(line);
  let out;
  try {
    if (msg.templates) C.setTemplates(msg.templates);
    if (msg.read) out = C.readDocument(msg.read, msg.file_date || "");
    else if (msg.eval) out = eval(msg.eval);      // nur für Tests: Ausdruck mit C (core.js)
    else out = E.state(msg.body);
  } catch (e) { out = { exception: String(e && e.stack || e) }; }
  process.stdout.write(JSON.stringify(out !== null && typeof out === "object" && !Array.isArray(out) && "exception" in out ? out : { result: out }) + "\n");
});
