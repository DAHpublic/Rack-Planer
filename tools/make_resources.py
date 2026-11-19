"""Erzeugt rack_resources.py (eingebettete Bilder für die Oberfläche).

Nur nötig, wenn sich ein Bild ändert. Aufruf aus dem Projektordner:
    python tools/make_resources.py

Hintergrund: Bis Version 1.00 wurde das Häkchen der Checkboxen beim Start als PNG in den
Temp-Ordner von Windows geschrieben. Seit 1.01 steckt es als Qt-Ressource im Programm,
damit die portable EXE keine Dateien außerhalb ihres Ordners anlegt.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ON_ACCENT = "#1c1c1c"        # = UI_ON_ACCENT in planer2d/theme.py


def check_png(path: Path):
    pm = QPixmap(28, 28)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ON_ACCENT), 3.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(6.5, 14.5), QPointF(11.5, 19.5), QPointF(21.5, 8.5)])
    p.end()
    if not pm.save(str(path), "PNG"):
        sys.exit(f"{path} konnte nicht geschrieben werden")


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        check_png(tmp / "check.png")
        (tmp / "rack.qrc").write_text(
            '<RCC><qresource prefix="/"><file>check.png</file></qresource></RCC>',
            encoding="utf-8")
        out = ROOT / "rack_resources.py"
        subprocess.run(["pyside6-rcc", str(tmp / "rack.qrc"), "-o", str(out)], check=True)
    print(f"Fertig: {out}")


if __name__ == "__main__":
    main()
