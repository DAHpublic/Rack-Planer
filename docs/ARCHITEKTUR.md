# Architektur: zwei Versionen, ein Regelwerk

Der Rack-Planer gibt es in zwei Versionen mit derselben Versionsnummer und demselben
Dateiformat:

1. **Desktop-Version** (`planer2d/`) – portable Windows-EXE mit Vorderseite, Rückseite (2D)
   und 3D-Ansicht
2. **Webversion** (`web/`) – HTML/PHP, z. B. auf der Synology (Web Station), offener Zugriff
   im LAN; auch als portable Windows-Variante mit mitgeliefertem PHP

Damit sich beide nicht auseinanderentwickeln, liegen alle fachlichen Regeln an genau
einer Stelle: im Paket **`rackcore/`**.

```
rackcore/            gemeinsamer Kern (reines Python, keine Oberfläche)
  model.py           Schrank, Geräte, Fachböden, Belegung je Seite, Tiefe, Konflikte
  templates.py       Gerätevorlagen (Daten in vorlagen.json, gemeinsam mit der Webversion)
  ips.py             IP-Prüfung, Vergleich ohne Subnetzmaske, doppelte IPs
  fileformat.py      Projektdatei (*.rack.json) inkl. Historie, Migration älterer Dateien
planer2d/            Desktop-Version (PySide6): 2D-Vorder-/Rückseite und 3D-Ansicht
web/                 Web-Version (HTML/PHP): Oberfläche + Rechenkern in JavaScript, api.php speichert
tests/               Tests für Kern und Oberflächen
```

Regel: **Eine Oberfläche rechnet nie selbst**, ob ein Platz frei ist, wie viel Tiefe übrig ist
oder ob eine IP doppelt ist – sie fragt `rackcore`. Neue Regeln kommen zuerst in den Kern
(mit Test), dann in die Oberflächen.

## Dateiformat

Eine Datei pro Schrank, JSON, Endung `.rack.json`. Der aktuelle Schrank steht auf oberster
Ebene (wie in Version 1), dazu `created`, `saved_at` und `history` mit früheren Ständen.
Details stehen in `rackcore/fileformat.py`.

- **Abwärtskompatibel:** Dateien aus 1.00/1.01 werden beim Laden ergänzt (Tiefe und Schienen
  aus den Vorlagen, Schranktiefe 600/800 mm, Stand = Dateidatum).
- **Vorwärtskompatibel:** Version 1.01 kann Dateien aus 2.x öffnen; sie ignoriert Tiefe,
  Rückseite und Historie.
- Neue Felder immer mit Standardwert ergänzen, nie umbenennen oder entfernen;
  `format` erhöhen und in `migrate()` nachrüsten.
- Dieselbe Datei funktioniert in beiden Versionen (Import/Export in der Web-Version).

## Webversion (HTML/PHP)

- **Rechnen im Browser:** `web/app/core.js` ist die JavaScript-Fassung von `rackcore` (Modell,
  Belegung, Tiefe, Konflikte, IP-Prüfung, Dateiformat inkl. Migration), `engine.js` enthält die
  Bearbeitungsschritte (Abläufe wie `planer2d/mainwindow.py`) und alle Anzeigedaten (Banner,
  Liste, Eigenschaften, erlaubte Drag-&-Drop-Ziele, 3D-Daten). `local-api.js` beantwortet die
  bisherigen Adressen `/api/state`, `/api/export` usw. direkt im Browser – die Oberfläche
  (`app.js`, `view3d.js`) spricht dadurch mit einer einheitlichen Schnittstelle.
- **Gleiche Regeln wie Desktop:** Regeländerungen zuerst in `rackcore` (mit Test), dann in
  `core.js`/`engine.js` nachziehen. `tests/test_web_core.py` vergleicht beide (Dateiformat,
  Belegung, Konflikte, IP-Regeln).
- **Zeichnung:** `render.js` erzeugt SVG mit der Optik von `planer2d/scene.py`. Text wird mit
  DejaVu Sans gemessen (`textfit.js` liest die Maße direkt aus der TTF-Datei in `app/fonts`).
  Export im Browser: SVG direkt, PNG über ein Canvas, PDF (A4, Seiten nebeneinander oder
  getrennt, Vektor, Schrift eingebettet) mit jsPDF + svg2pdf.js (`app/lib`).
- **Speicher (`web/api.php`):** PHP 7.4+ ohne Datenbank und ohne Zusatzerweiterungen.
  `daten/schraenke/<id>.rack.json` – je Schrank eine normale Projektdatei inkl. Historie
  (Speichern legt wie in der Desktop-Version den bisherigen Stand in der Historie ab);
  `daten/eigene-vorlagen.json` – im Browser angelegte Vorlagen. Gleichzeitiges Bearbeiten:
  Revision = Prüfsumme der Datei, beim Speichern Warnung, wenn jemand anderes zuvor gespeichert
  hat. Schreibzugriffe laufen nacheinander (Sperrdatei) und atomar (Hilfsdatei + Umbenennen).
- **Vorlagen:** `rackcore/vorlagen.json` ist die einzige Quelle für Desktop (`templates.py`
  lädt sie, die EXE enthält sie) und Web (das ZIP enthält eine Kopie als `vorlagen.json`).
- **Update:** `python web/build_web.py` baut `Rack-Planer-Web_v<V>.zip` (Ordner `rack-planer`
  mit `version.json` und `manifest.json`, ohne `daten`). Im Programm: Hilfe → Programm
  aktualisieren lädt das ZIP hoch; `api.php` prüft es (nur Programmdateien, kein `daten/`),
  ersetzt die Dateien und entfernt Dateien, die es laut neuem Manifest nicht mehr gibt.
  Abschaltbar mit `{"update_erlaubt": false}` in `daten/einstellungen.json`.
- **Betrieb:** Synology Web Station (oder jeder Webserver mit PHP), kein Login, offener
  Zugriff im LAN. Portabel für Windows: dasselbe ZIP plus PHP für Windows und Start-Batch
  (`php -S`). Anleitung: `web/SYNOLOGY.md`.

## 3D-Ansicht

Die 3D-Ansicht ist in Qt umgesetzt, weil das technisch die geringsten Umwege hat:

- **Ein Programm:** Die Desktop-Version startet direkt mit `MainWindow3D` (`planer2d/mainwindow3d.py`), die Leiste schaltet zwischen
  Vorderseite, Rückseite (2D) und 3D um.
- **Gleiche Basis wie 2D:** `MainWindow3D` erbt vom 2D-Hauptfenster. Vorlagen, Eigenschaften,
  IP-Prüfung, Historie, Rückgängig, Export und Tutorial sind damit automatisch identisch und
  bleiben es, wenn die 2D-Version weiterentwickelt wird. Neu ist nur die Ansicht in der Mitte.
- **Keine zusätzliche Laufzeitumgebung:** Die 3D-Grafik (`planer2d/view3d.py`) projiziert die
  achsparallelen Quader des Schranks (Rahmen, 19"-Profile, Geräte, Fachböden, Schienen)
  perspektivisch und zeichnet sie mit QPainter von hinten nach vorne (Maleralgorithmus mit
  Trennebenen, topologisch sortiert). Weder OpenGL noch WebView2 nötig → läuft überall, wo
  die 2D-EXE läuft, und bleibt eine **portable EXE** (PyInstaller, eine Datei).
- **Export gratis:** Derselbe Zeichencode schreibt PNG und SVG der 3D-Ansicht.
- **Geometrie aus dem Kern:** Position, HE, Tiefe, Montageseite und Einbauschienen kommen aus
  `rackcore`; die 3D-Ansicht rechnet keine Regeln selbst (Belegung über `Rack.is_free`,
  Konflikte über `Rack.conflicts`).
- **Webversion:** dieselbe 3D-Ansicht im Browser (`web/app/view3d.js`),
  1:1 aus `build_boxes()`/`render()` übertragen und mit dem normalen Canvas gezeichnet (kein
  WebGL, keine zusätzliche Bibliothek). Der Server liefert dafür in `view.scene3d` Position,
  belegte HE, Fachbodenhöhe und Beschriftung jedes Elements (aus `rackcore`) und in
  `view.targets` die erlaubten Ziele beim Ziehen – auch Fachböden der anderen Seite.

## Code-Signing

Das Windows-Programm wird über die SignPath Foundation signiert, sobald die
Aufnahme bestätigt ist. Nur Builds aus dem GitHub-Workflow werden signiert; jede
Programmdatei trägt den Produktnamen „Rack-Planer“. Einrichtung und Erweiterung für neue
Programme: `docs/signpath/EINRICHTUNG.md`.
