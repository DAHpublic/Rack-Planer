# Drittanbieter-Komponenten / Third-party notices

Rack-Planer selbst steht unter der **MIT-Lizenz** (siehe `LICENSE`).
Die Windows-EXE enthält zusätzlich die folgenden Komponenten anderer Urheber.
Sie gehören nicht zum Rack-Planer und stehen unter ihren eigenen Lizenzen.

| Komponente | Verwendung | Lizenz | Quelle |
|---|---|---|---|
| **Qt 6** (The Qt Company Ltd. und Mitwirkende) | Oberfläche, Zeichnen, PDF/SVG-Export | GNU LGPL v3 | https://www.qt.io/download-open-source · https://code.qt.io |
| **PySide6 / Shiboken6** (Qt for Python) | Python-Anbindung an Qt | GNU LGPL v3 | https://pypi.org/project/PySide6-Essentials/ · https://code.qt.io/cgit/pyside/pyside-setup.git |
| **Python** (Python Software Foundation) | Laufzeitumgebung | PSF License Agreement | https://www.python.org/downloads/source/ · https://docs.python.org/3/license.html |
| **PyInstaller-Bootloader** | Start der Einzeldatei-EXE | GPL v2 oder neuer **mit Bootloader-Ausnahme** (erlaubt die Weitergabe der erzeugten EXE unter beliebiger Lizenz) | https://github.com/pyinstaller/pyinstaller |

Qt und Python bringen ihrerseits weitere freie Bibliotheken mit (z. B. zlib, libpng,
FreeType, HarfBuzz, PCRE2, OpenSSL, libffi, SQLite, expat). Deren Lizenzen sind in den
Dokumentationen aufgeführt: https://doc.qt.io/qt-6/licenses-used-in-qt.html und
https://docs.python.org/3/license.html.

## Hinweise zur LGPL (Qt / PySide6)

- Qt und PySide6 werden **unverändert** verwendet, so wie sie von PyPI (`PySide6-Essentials`)
  geladen werden. Den vollständigen Quelltext gibt es unter den oben genannten Adressen.
- Der Lizenztext liegt bei: `licenses/LGPL-3.0.txt` (die LGPL v3 ergänzt die GNU GPL v3,
  `licenses/GPL-3.0.txt`). Beide sind auch im Programm unter **Hilfe → Lizenzen** einsehbar,
  ebenso **Hilfe → Über Qt**.
- **Austausch der Qt-Bibliotheken:** Der komplette Quelltext des Rack-Planers ist öffentlich
  und unter MIT lizenziert. Wer eine andere oder selbst geänderte Version von Qt/PySide6
  verwenden möchte, kann das Programm direkt damit starten (`python rack_planer.py`) oder die
  EXE mit `python build.py` gegen die eigene Version neu bauen (siehe `README.md`).

---

*English summary:* Rack-Planer is MIT-licensed. The Windows executable bundles Qt 6 and
PySide6/Shiboken6 (unmodified, GNU LGPL v3), the Python runtime (PSF License) and the
PyInstaller bootloader (GPL v2+ with bootloader exception). License texts are in
`licenses/`; the full Rack-Planer source and build script let you run or rebuild the program
with a different or modified Qt/PySide6.

## Webversion (HTML/PHP)

Die Webversion (`web/`, ZIP `Rack-Planer-Web_v<Version>.zip`) enthält zusätzlich – die
Lizenztexte stehen in `web/app/LIZENZEN.txt` und liegen dem ZIP bei:

| Komponente | Verwendung | Lizenz | Quelle |
|---|---|---|---|
| **DejaVu Sans** | Schrift für Zeichnung und Export | Bitstream-Vera-Lizenz (DejaVu-Änderungen gemeinfrei) | https://dejavu-fonts.github.io/ |
| **jsPDF** 4.2.1 | PDF-Export im Browser | MIT | https://github.com/parallax/jsPDF |
| **svg2pdf.js** 2.9.0 | SVG → PDF für jsPDF | MIT | https://github.com/yWorks/svg2pdf.js |

Die portable Windows-Variante bringt außerdem **PHP** für Windows mit (PHP License v3.01,
https://www.php.net/license/), unverändert von https://windows.php.net.
