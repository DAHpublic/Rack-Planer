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
   - Erweiterungen: **zip** und **curl** anhaken (für das automatische Update)
   - Sonst alles auf Standard lassen.
3. **Dateien kopieren:** ZIP entpacken und den Ordner **`rack-planer`** in den freigegebenen
   Ordner **`web`** kopieren (File Station oder `\\<NAS>\web` im Explorer). Danach gibt es
   `web/rack-planer/index.html`, `web/rack-planer/api.php` usw.
4. **Schreibrechte geben:** File Station → Rechtsklick auf `web/rack-planer` → Eigenschaften →
   Berechtigung → Erstellen: Benutzer oder Gruppe **`http`**, **Lesen und Schreiben** anhaken,
   „Auf diesen Ordner, Unterordner und Dateien anwenden“ → Speichern.
   (Der Webserver legt beim ersten Speichern den Ordner `daten` an und braucht für das
   automatische Update Schreibrechte auf die Programmdateien.)
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

## Einstellungen (`einstellungen.ini`)

Im Ordner `web/rack-planer` liegt die Datei **`einstellungen.ini`** (mit dem Texteditor oder
dem Texteditor-Paket der Synology bearbeiten). Updates überschreiben sie **nie**; fehlt sie,
legt der Rack-Planer sie mit den Standardwerten neu an. Nach einer Änderung genügt es, die
Seite im Browser neu zu laden.

| Eintrag | Standard | Bedeutung |
|---|---|---|
| `auto_update` | `true` | Neue Versionen nachts automatisch von GitHub laden und einspielen |
| `auto_update_von` / `auto_update_bis` | `"00:30"` / `"03:30"` | Zeitfenster der Prüfung (Uhrzeit des NAS) |
| `web_update` | `false` | Update von Hand über Hilfe → Programm aktualisieren (ZIP hochladen oder „Jetzt aktualisieren“) |
| `quelle` | `"DAHpublic/Rack-Planer"` | GitHub-Repository, aus dessen neuestem Release das Update kommt |
| `server_speichern` | `true` | `false`: Der Server speichert nichts. „Speichern“ lädt den Schrank als `.rack.json`-Datei herunter (inkl. Historie), „Schränke …“ öffnet eine solche Datei – wie in der Desktop-Version. Eigene Vorlagen gibt es dann nicht. |

## Update

### Automatisch (Standard)

Jede Nacht zwischen **00:30 und 03:30 Uhr** schaut der Rack-Planer auf der
[Release-Seite](https://github.com/DAHpublic/Rack-Planer/releases/latest) nach. Gibt es eine
neuere Version, lädt er `Rack-Planer-Web_v<Version>.zip` herunter, prüft die Prüfsumme und
spielt es ein. Ersetzt werden nur Programmdateien und die mitgelieferten Vorlagen – der Ordner
`daten` und `einstellungen.ini` bleiben unverändert. Geprüft wird höchstens einmal je Nacht
(nach einem Fehler, z. B. Internet weg, frühestens eine Stunde später erneut).

Voraussetzungen: PHP-Erweiterungen **zip** und **curl** (Schritt 2), Schreibrechte für `http`
(Schritt 4) und Internetzugang des NAS.

PHP läuft nur, wenn jemand die Seite aufruft – nachts schaut aber selten jemand vorbei. Damit
die Prüfung zuverlässig jede Nacht läuft, einmalig eine Aufgabe im **Aufgabenplaner** anlegen:

1. Systemsteuerung → **Aufgabenplaner** → Erstellen → Geplante Aufgabe →
   **Benutzerdefiniertes Skript**.
2. Reiter **Allgemein**: Aufgabe `Rack-Planer Update`, Benutzer `root` (das Skript ruft nur
   die Webseite auf; das Update selbst macht der Webserver mit seinen eigenen Rechten).
3. Reiter **Zeitplan**: Täglich, Erste Ausführungszeit **00:30**, Häufigkeit **Alle 60 Minuten**,
   Letzte Ausführungszeit **03:00**.
4. Reiter **Aufgabeneinstellungen** → Benutzerdefiniertes Skript:
   ```
   curl -fsS "http://localhost/rack-planer/api.php?p=autoupdate"
   ```
   (Die Adresse ist dieselbe wie im Browser, nur mit `localhost` statt der NAS-IP – bei
   eigenem Port z. B. `http://localhost:8090/api.php?p=autoupdate`.)
5. OK. Zum Testen die Aufgabe markieren → **Ausführen**; unter Aktion → Ergebnis anzeigen steht
   die Antwort, z. B. `"status":"ausserhalb"` (tagsüber), `"aktuell"` oder `"aktualisiert"`.

Mehrfaches Aufrufen schadet nicht: Ist die Nacht schon erledigt, passiert nichts. Wer die Seite
nachts im Zeitfenster öffnet, stößt die Prüfung ebenfalls an. Das Ergebnis der letzten Prüfung
steht im Rack-Planer unter **Hilfe → Programm aktualisieren**.

Alternativ ohne Webserver (SSH oder Aufgabenplaner): `php82 /volume1/web/rack-planer/api.php
autoupdate` (`--jetzt` prüft sofort, ohne Zeitfenster). Dafür muss das PHP der Kommandozeile
die Erweiterungen zip und curl haben – der Weg über curl oben ist meist einfacher.

**Von Version 2.05 auf 2.06** (einmalig, die erste Version mit automatischem Update): wie bisher
von Hand – Hilfe → Programm aktualisieren → ZIP auswählen, oder Ordnerinhalt ersetzen.

### Von Hand

- **Im Browser:** in `einstellungen.ini` `web_update = true` setzen. Dann bietet Hilfe →
  Programm aktualisieren **„Jetzt aktualisieren“** (holt die neueste Version von GitHub) und
  **„ZIP einspielen“** (vorher heruntergeladenes `Rack-Planer-Web_v<Version>.zip` auswählen,
  nicht entpacken).
- **Ordner ersetzen** (geht immer): ZIP entpacken und den Inhalt von `rack-planer` über
  `web/rack-planer` kopieren, vorhandene Dateien ersetzen – **außer `einstellungen.ini`**
  (beim Nachfragen „überspringen“ wählen). Den Ordner `daten` nicht löschen.

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
node tests/e2e/web_e2e.js http://127.0.0.1:8099/ [update.zip]   # Browsertest (Playwright, web_update = true)
node tests/e2e/web_e2e_dateimodus.js http://127.0.0.1:8098/      # Browsertest mit server_speichern = false
```

Aufbau: `web/index.html` (Oberfläche), `web/api.php` (Speicher, Update, Einstellungen),
`web/einstellungen.ini` (Standard-Einstellungen), `web/app/`:
`app.js` (Bedienung), `core.js` (Kern wie `rackcore`), `engine.js` (Bearbeitungsschritte und
Anzeigedaten), `render.js` (SVG-Zeichnung), `textfit.js` (Schriftmaße), `export.js`
(PDF/PNG/SVG), `view3d.js` (3D-Ansicht), `local-api.js` (verbindet alles).
Regeländerungen immer in `rackcore` **und** `core.js`/`engine.js` nachziehen.
