# Rack-Planer

Grafischer Planer für Serverschränke: Geräte nach Höheneinheiten (HE) vorne und hinten
einplanen, Einbautiefe prüfen, Geräte mit Namen und IP-Adressen beschriften und
Leistungsaufnahme sowie Wärmelast (W und BTU/h) im Blick behalten – in 2D und 3D.

## Download

Auf der [Release-Seite](https://github.com/DAHpublic/Rack-Planer/releases/latest):

| Datei | Für |
|---|---|
| `Rack-Planer_v<Version>.exe` | **Desktop-Version** für Windows – herunterladen und starten, keine Installation |
| `Rack-Planer-Web_v<Version>.zip` | **Webversion** für die Synology (Web Station) oder jeden Webserver mit PHP 7.4+ – Anleitung: [`web/SYNOLOGY.md`](web/SYNOLOGY.md) |

Beide Versionen tragen dieselbe Versionsnummer (aktuell 2.05) und öffnen dieselben
Projektdateien (`.rack.json`).

- **Desktop-Version:** ein Programm mit drei Ansichten, umschaltbar in der Leiste:
  **Vorderseite**, **Rückseite** (2D) und die frei drehbare **3D**-Ansicht.
- **Webversion (HTML/PHP):** kein Docker, keine Datenbank – Ordner auf den Webserver kopieren,
  fertig. Alle im Heimnetz öffnen den Planer im Browser; die Schränke liegen zentral als
  `.rack.json`-Dateien auf dem Server. Gerechnet, gezeichnet und exportiert (PDF/PNG/SVG) wird
  im Browser. **Update:** im Programm Hilfe → Programm aktualisieren → neues ZIP auswählen; die
  Daten bleiben erhalten.

> Die EXE ist noch nicht digital signiert. Windows SmartScreen kann deshalb beim ersten Start
> warnen („Weitere Informationen“ → „Trotzdem ausführen“).

## Funktionen
- Schrankhöhe in HE einstellen (Schnellwahl 6/9/12/15/22/42/47 HE)
- Einbautiefe des Schranks (Standard 800 mm, Schnellwahl 45/60/80/100/120 cm) und Tiefe jedes Geräts;
  alle Vorlagen mit realen Tiefen (Synology laut Datenblatt, sonst typische Werte, als „ca.“ markiert)
- **Vorder- und Rückseite** umschaltbar (Strg + R). Jedes Gerät wird vorne oder hinten montiert und
  belegt ab dort seine Tiefe – die Tiefe ist eine Kapazität: 800 mm Schrank, hinten 50 mm
  Steckdosenleiste → vorne noch 750 mm frei. Geräte der Gegenseite werden gestrichelt mit freier
  Tiefe angedeutet (Doppelklick wechselt die Seite), rechts zeigt eine Seitenansicht die Tiefe je HE
  (immer vorne links, hinten rechts; inkl. Fachböden mit ihren Geräten; ausblendbar mit dem Häkchen „Seitenansicht“ in der Leiste, in den 2D-Ansichten und im Web).
- **Tiefenkonflikte** werden rot markiert und im Banner erklärt: zu tief für den Schrank, vorne + hinten
  zusammen zu tief, oder Einbauschienen (USV, Server, Rack-NAS) blockieren die Gegenseite
- **„Aktueller Stand“** (Datum) je Schrank, bei neuen Dateien das Erstellungsdatum; steht auf jedem
  Export unter dem Titel
- **Historie:** Wird eine gespeicherte Datei geändert, fragt der Planer, ob eine Historie angelegt
  werden soll. Frühere Stände bleiben in derselben Datei; im Tab „Historie“ neben „Geräte im Schrank“
  lassen sie sich im Schrank ansehen, wiederherstellen oder als eigene Datei speichern (Strg + H)
- Fachböden als Vorlagen: kurz (250 mm), 400 mm und volle Tiefe (4-Punkt, blockiert die Rückseite).
  Nicht rackfähige Geräte belegen auf dem Fachboden nur so viel Höhe wie nötig, aufgerundet auf das
  nächste Schraubenloch (⅓ HE)
- **Hilfe:** „Infos über Rack-Planer“ (Version) und ein kurzes Tutorial (F1)
- Geräte aus Vorlagen hinzufügen: Synology RackStation, Synology DiskStation (Desktop),
  AVM FRITZ!Box, Switch, Patchpanel, Firewall, Server, USV, Zubehör
- Eigene Geräte mit beliebiger Höhe, Kategorie, Breite und Leistung
- Größe (HE), Position, Breite und Leistung jedes Geräts nachträglich ändern
- Nicht rackfähige Geräte (z. B. DiskStation, FRITZ!Box): Programm bietet an, einen
  Fachboden einzubauen oder das Gerät auf einen vorhandenen Fachboden mit freiem Platz zu stellen
- Info-Banner, wenn NAS, Firewall und/oder Server, aber keine USV eingebaut sind
  (mit Knopf „USV hinzufügen“)
- Beschriftung jedes Geräts mit Gerätename und bis zu 5 IP-Adressen (ungültige IPs werden rot markiert)
- Verschieben per Maus (Drag & Drop, grün = Platz frei, rot = belegt) oder ▲/▼
- Summe Leistungsaufnahme und Wärmelast (W und BTU/h) in der Statusleiste
- Exportieren als PDF (A4) mit Vorderseite und/oder Rückseite (nebeneinander oder per Häkchen je auf einer eigenen
  PDF-Seite) oder als Bild einer
  Seite (PNG oder SVG): nur Schrank, Geräte, Beschriftung und Stand – keine Hinweise; auf Wunsch mit
  maximaler Strom- und Wärmelast unter dem Schrank
- Projekte speichern/öffnen (`.rack.json`, eine Datei pro Schrank inkl. Historie); gespeichert wird
  atomar, ein abgebrochener Speichervorgang beschädigt die vorhandene Datei nicht
- Rückgängig/Wiederholen (Strg + Z / Strg + Y) für alle Änderungen am Schrank
- Suchfeld für die Vorlagen (Strg + F), Enter fügt die markierte Vorlage hinzu
- Warnung bei doppelt vergebenen IP-Adressen (Banner, Markierung in Liste und Eingabefeld);
  die Subnetzmaske spielt dabei keine Rolle (`192.168.1.10/24`, `/16`, `192.168.1.10 255.255.255.0`
  und `192.168.1.10` gelten als dieselbe Adresse)
- Geräteliste mit Spalten für Name, HE, Seite, IP-Adresse und Leistung

## 3D-Ansicht (Desktop- und Webversion)
- Das Programm startet mit der 2D-Vorderseite; in der Leiste schalten **Vorderseite**, **Rückseite**
  und **3D** zwischen den Ansichten um (Strg + R wechselt die Seite, Strg + 3 = 3D)
- **Drehen** mit der linken (auf freier Fläche) oder rechten Maustaste, **Zoomen** mit dem Mausrad,
  **Ansicht verschieben** mit der mittleren Maustaste oder Umschalt + linke Maustaste,
  **Doppelklick** holt ein Gerät heran; ← / → drehen, + / − zoomen
- Feste Blickwinkel oben links: Vorne, Hinten, Links, Rechts, Oben, 3D, Anpassen (Strg + 0);
  Seitenwände und Beschriftung (Namen, IP-Adressen, HE-Nummern) ein-/ausblendbar
- **Geräte anklicken** wählt sie aus (Eigenschaften rechts), **Geräte ziehen** verschiebt sie nach oben
  oder unten (grün = frei, rot = belegt), Entf löscht
- **Geräte auf Fachböden** (nicht rackfähig) lassen sich wie in 2D frei auf denselben oder einen
  anderen Fachboden ziehen, auch auf einen Fachboden der Rückseite; der Fachboden wächst bei Bedarf
  und wird auf das nächste Schraubenloch aufgerundet
- Tiefe wird echt dargestellt: Geräte beginnen an ihrer Montageseite und reichen so tief in den
  Schrank, wie sie sind; Einbauschienen laufen sichtbar von vorne nach hinten; Tiefenkonflikte rot
- Schaut die Kamera auf die Rückseite, werden neue Geräte hinten montiert (wie „Rückseite“ in 2D)
- Historie: frühere Stände werden auch in 3D angezeigt (nur ansehen)
- Webversion: gleiche Bedienung und Darstellung im Browser (`web/app/view3d.js`),
  Export der 3D-Ansicht als PNG
- **Export der 3D-Ansicht** als PNG (Standard, doppelte Auflösung) oder SVG mit Titel, Stand und
  Strom-/Wärmelast (Exportieren → „3D-Ansicht als Bild“, Strg + Umschalt + E); PDF und Bilder der
  Vorder-/Rückseite wie gewohnt
- Die 3D-Grafik wird ohne OpenGL/Grafiktreiber gezeichnet und läuft daher auf jedem Windows-PC,
  auch ohne dedizierte Grafikkarte – als **portable EXE** ohne Installation
- 19"-Profile mit allen Schraubenlöchern (drei je HE, ⅓-Raster), Trennlinien und HE-Nummern vorne und
  hinten – so lassen sich Geräte genau auf die richtige HE ziehen

## Portabel
Der Rack-Planer legt keine Konfigurations- oder Hilfsdateien an und schreibt nichts in die
Registry. Einstellungen wie der zuletzt benutzte Ordner gelten nur bis zum Beenden.
Dateien entstehen nur dort, wo du speicherst oder exportierst.

## Windows-EXE bauen
1. Python 3.10 oder neuer von https://www.python.org installieren
   („Add python.exe to PATH“ anhaken).
2. `build.bat` doppelklicken.
3. Ergebnis: `dist\Rack-Planer_v<Version>.exe`, z. B. `Rack-Planer_v2.05.exe` (eine einzelne
   Datei, ohne Installation lauffähig). Die Versionsnummer steht in `APP_VERSION` in
   `rackcore/version.py` (gilt für Desktop und Web); ältere EXE-Dateien werden nie überschrieben. Für eine neue EXE zuerst
   die Version erhöhen. Versionsnummer und Entwickler stehen auch in den Dateieigenschaften.

Auf GitHub baut der Workflow „Windows-EXE bauen“ (`.github/workflows/build-windows.yml`) die
EXE und hängt sie an das Release `v<Version>`; der Workflow „Webversion (HTML/PHP)“ baut die
Web-ZIP (lokal: `python web/build_web.py`) und hängt sie an dasselbe Release.

**Gerätevorlagen** stehen für beide Versionen in einer Datei: [`rackcore/vorlagen.json`](rackcore/vorlagen.json)
(eine Zeile je Vorlage). Neue Vorlage = neue Zeile; die Desktop-EXE und das Web-ZIP übernehmen
die Datei beim nächsten Build.

## Direkt starten (ohne EXE)
```
pip install -r requirements.txt
python rack_planer.py
```

## Entwicklung
Aufbau des Repositorys (Details: `docs/ARCHITEKTUR.md`):

| Ordner/Datei | Inhalt |
|---|---|
| `rackcore/` | **Gemeinsamer Kern** ohne Qt: Datenmodell, Belegung, Tiefenprüfung, Vorlagen, IP-Prüfung, Dateiformat inkl. Historie – wird von Desktop und Web gleichermaßen genutzt |
| `planer2d/` | Desktop-Oberfläche (PySide6): 2D-Grafik (`scene.py`), 3D-Ansicht (`view3d.py`), Hauptfenster (`mainwindow.py`, erweitert um 3D in `mainwindow3d.py`), Dialoge, Export, Tutorial; Version: `rackcore/version.py` |
| `rack_planer.py` | Startpunkt (`python rack_planer.py`, Windows-Build) |
| `web/` | Webversion (HTML/PHP): `index.html`, `api.php` (Speicher), `app/` (Oberfläche, Rechenkern `core.js`/`engine.js` = JavaScript-Fassung von `rackcore`, Zeichnung `render.js`, Export `export.js`, 3D `view3d.js`); ZIP bauen: `python web/build_web.py`; Anleitung und Entwicklung: `web/SYNOLOGY.md` |
| `rack_resources.py` | eingebettete Bilder, erzeugt mit `python tools/make_resources.py` |
| `tests/` | Tests für Kern und Oberfläche: `pip install -r requirements-dev.txt`, dann `python -m pytest` (`test_web_core.py` vergleicht den Web-Rechenkern mit `rackcore`, braucht Node.js; Browsertest der Webversion: `tests/e2e/web_e2e.js`) |

## Bedienung
- Vorlage doppelklicken oder auswählen und „Vorlage hinzufügen“
- Gerät im Schrank oder in der Liste anklicken → rechts Name, IP, Höhe usw. bearbeiten
- Entf löscht das ausgewählte Gerät (Strg + Z holt es zurück), Strg + Mausrad zoomt
- Strg + R wechselt zwischen Vorder- und Rückseite; neue Geräte werden auf der angezeigten Seite montiert
- Rechts unter „Eigenschaften“: Montageseite, Tiefe, Einbauschienen und die freie Tiefe am Platz
- F1 startet das Tutorial

## Lizenz
Rack-Planer ist freie Software unter der [MIT-Lizenz](LICENSE) (© 2026 DAHpublic).
Du darfst das Programm und den Quelltext frei nutzen, verändern und weitergeben; die Software
wird ohne jede Gewährleistung bereitgestellt, eine Haftung ist ausgeschlossen.
Die Windows-EXE enthält Qt 6 und PySide6 (GNU LGPL v3) sowie weitere Komponenten anderer
Urheber, siehe [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Im Programm: **Hilfe → Lizenzen**.

## Code signing policy
Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)
– Rollen, Ablauf und Datenschutz: [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md)
(Antrag in Vorbereitung; bis zur Freigabe sind die EXE-Dateien nicht signiert).
