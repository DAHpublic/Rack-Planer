# Rack-Planer Webversion auf der Synology (Web Station, PHP)

Die Webversion ist ein Ordner mit HTML-, JavaScript- und PHP-Dateien. Sie läuft in der
**Web Station** der Synology – ohne Docker und ohne Datenbank. Alle im Heimnetz öffnen den
Planer im Browser; die Schränke liegen als `.rack.json`-Dateien auf dem NAS (dasselbe Format
wie die Desktop-Version). Kein Login – gedacht für das eigene LAN, nicht für das Internet.

## Was du brauchst

- DSM 7 mit den Paketen **Web Station** und **PHP** (8.x, im Paket-Zentrum; 7.4 geht auch).
- Die Datei `Rack-Planer-Web_v<Version>.zip` von der
  [Release-Seite](https://github.com/DAHpublic/Rack-Planer/releases/latest).
  Alternativ selbst bauen: `python web/build_web.py` → `dist/`.

## Einrichten (einmalig, ca. 5 Minuten)

1. **Web Station und PHP installieren:** Paket-Zentrum → „Web Station“ installieren, außerdem
   ein PHP-Paket (z. B. „PHP 8.2“).
2. **PHP-Profil anlegen:** Web Station → **Skriptsprache-Einstellungen** → PHP → Erstellen:
   - Profilname: `Rack-Planer`, PHP-Version: 8.2 (oder die installierte)
   - Erweiterungen: **zip** anhaken (nur für das Update im Browser nötig)
   - Sonst alles auf Standard lassen.
3. **Dateien kopieren:** ZIP entpacken und den Ordner **`rack-planer`** in den freigegebenen
   Ordner **`web`** kopieren (File Station oder `\\<NAS>\web` im Explorer). Danach gibt es
   `web/rack-planer/index.html`, `web/rack-planer/api.php` usw.
4. **Schreibrechte geben:** File Station → Rechtsklick auf `web/rack-planer` → Eigenschaften →
   Berechtigung → Erstellen: Benutzer oder Gruppe **`http`**, **Lesen und Schreiben** anhaken,
   „Auf diesen Ordner, Unterordner und Dateien anwenden“ → Speichern.
   (Der Webserver legt beim ersten Speichern den Ordner `daten` an und braucht für das
   Update im Browser Schreibrechte auf die Programmdateien.)
5. **PHP für den Ordner aktivieren:** Web Station → **Web-Portal** (bzw. „Webdienste“) →
   Standard-Server bzw. das Portal für den Ordner `web` → **PHP-Profil „Rack-Planer“** wählen.
   Bei der Standardeinrichtung genügt es, unter Web Station → **Allgemeine Einstellungen**
   (bzw. Standardserver) als PHP-Profil „Rack-Planer“ einzustellen.
6. **Öffnen:** im Browser `http://<NAS-IP>/rack-planer/` (z. B. `http://192.168.178.20/rack-planer/`).
   Lesezeichen setzen – fertig.

Erscheint statt des Planers der Text „api.php wurde nicht gefunden“ oder PHP-Quelltext, ist
PHP für den Ordner noch nicht aktiv (Schritt 5). Meldet der Planer beim Speichern fehlende
Schreibrechte, Schritt 4 wiederholen.

### Eigene Adresse (optional)

Statt `http://<NAS>/rack-planer/` geht auch ein eigener Port, z. B. `http://<NAS>:8090/`:
Web Station → Web-Portal → Erstellen → „Portal auf Basis eines Webdienstes“ → Webdienst
erstellen: Typ „Statische Website mit PHP“, Dokumentstamm `web/rack-planer`, PHP-Profil
„Rack-Planer“; dann ein Portal mit Port 8090 für diesen Webdienst anlegen.

## Update

Neue Version einspielen – Schränke und eigene Vorlagen bleiben erhalten:

1. Neue `Rack-Planer-Web_v<Version>.zip` von der Release-Seite herunterladen (nicht entpacken).
2. Im Rack-Planer: **Hilfe → Programm aktualisieren …** → ZIP auswählen → „Update einspielen“.
3. Die Seite lädt neu; unter Hilfe → Infos steht die neue Versionsnummer.

Das Update ersetzt nur Programmdateien und die mitgelieferten Vorlagen (`vorlagen.json`). Der
Ordner `daten` wird nie angefasst.

**Von Hand** (falls die Erweiterung „zip“ fehlt oder das Update abgeschaltet ist): ZIP
entpacken und den Inhalt von `rack-planer` über `web/rack-planer` kopieren, vorhandene Dateien
ersetzen. Den Ordner `daten` nicht löschen.

Wer das Update im Browser nicht möchte (z. B. weil viele im Netz Zugriff haben): Datei
`web/rack-planer/daten/einstellungen.json` mit dem Inhalt `{"update_erlaubt": false}` anlegen.

## Vorlagen aktualisieren

Die mitgelieferten Gerätevorlagen stehen in `vorlagen.json` (eine Zeile je Vorlage – dieselbe
Datei wie in der Desktop-Version, im Repository `rackcore/vorlagen.json`). Sie kommen mit jedem
Update automatisch neu. Eigene Vorlagen („Als Vorlage speichern“ im Planer) liegen in
`daten/eigene-vorlagen.json` und bleiben bei Updates erhalten.

## Daten sichern

Alles Wichtige liegt in `web/rack-planer/daten`:

- `schraenke/*.rack.json` – je Schrank eine Projektdatei inkl. Historie; lässt sich direkt in
  der Desktop-Version öffnen
- `eigene-vorlagen.json` – eigene Vorlagen

Diesen Ordner in Hyper Backup aufnehmen oder ab und zu kopieren.

## Entwicklung

```
php -S 127.0.0.1:8090 -t web          # direkt aus dem Repository (Vorlagen/Version aus rackcore)
python web/build_web.py               # ZIP nach dist/
python -m pytest tests/test_web_core.py   # Rechenkern JS gegen rackcore (braucht Node.js)
node tests/e2e/web_e2e.js http://127.0.0.1:8099/ [update.zip]   # Browsertest (Playwright)
```

Aufbau: `web/index.html` (Oberfläche), `web/api.php` (Speicher, Update), `web/app/`:
`app.js` (Bedienung), `core.js` (Kern wie `rackcore`), `engine.js` (Bearbeitungsschritte und
Anzeigedaten), `render.js` (SVG-Zeichnung), `textfit.js` (Schriftmaße), `export.js`
(PDF/PNG/SVG), `view3d.js` (3D-Ansicht), `local-api.js` (verbindet alles).
Regeländerungen immer in `rackcore` **und** `core.js`/`engine.js` nachziehen.
