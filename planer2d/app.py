"""Start der Desktop-Anwendung (2D-Vorderseite, 2D-Rückseite und 3D-Ansicht)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

import rack_resources  # noqa: F401  (registriert eingebettete Bilder unter ":/")
from rackcore import APP_NAME

from . import APP_AUTHOR, APP_VERSION
from .mainwindow3d import MainWindow3D
from .theme import apply_dark_theme


def app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#2b2f36"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(10, 2, 44, 60), 5, 5)
    for i, c in enumerate(("#2f6fb3", "#1e8449", "#c0392b", "#d68910")):
        p.setBrush(QColor(c))
        p.drawRect(QRectF(15, 8 + i * 13, 34, 10))
    p.end()
    return QIcon(pm)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_AUTHOR)
    apply_dark_theme(app)
    app.setWindowIcon(app_icon())
    win = MainWindow3D()
    win.show()
    if len(sys.argv) > 1:
        arg = Path(sys.argv[1])
        if arg.is_file():
            win.open_path(arg)
        else:
            QMessageBox.warning(win, APP_NAME, f"Die Datei wurde nicht gefunden:\n{arg}")
    sys.exit(app.exec())

