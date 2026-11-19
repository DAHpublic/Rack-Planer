"""Hilfe → Lizenzen: MIT-Lizenz des Rack-Planers und Hinweise zu Qt/PySide6 (LGPL v3).

Die Texte liegen im Projektordner (LICENSE, THIRD-PARTY-NOTICES.md, licenses/) und werden
von build.py in die EXE gepackt; dort liegen sie im Entpackordner von PyInstaller.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

# (Reitertitel, Datei relativ zum Projektordner, als Markdown darstellen?)
LICENSE_FILES = [
    ("Rack-Planer (MIT)", "LICENSE", False),
    ("Drittanbieter", "THIRD-PARTY-NOTICES.md", True),
    ("GNU LGPL v3", "licenses/LGPL-3.0.txt", False),
    ("GNU GPL v3", "licenses/GPL-3.0.txt", False),
]


def resource_root() -> Path:
    """Projektordner bzw. Entpackordner der EXE."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def read_license(rel: str) -> str:
    try:
        return (resource_root() / rel).read_text(encoding="utf-8")
    except OSError:
        return f"{rel} wurde nicht gefunden. Siehe https://github.com/DAHpublic/Rack-Planer"


class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lizenzen")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        for title, rel, markdown in LICENSE_FILES:
            view = QTextBrowser()
            view.setOpenExternalLinks(True)
            text = read_license(rel)
            if markdown:
                view.setMarkdown(text)
            else:
                view.setPlainText(text)
            self.tabs.addTab(view, title)
        lay.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


def show_licenses(parent):
    LicenseDialog(parent).exec()
