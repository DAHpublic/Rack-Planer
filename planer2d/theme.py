"""Farben und Dark Theme der Oberfläche sowie Zeichenfarben des Schranks."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Dark Theme: Hauptfarbe dunkles Grau, Akzente helles Grau und Orange
UI_BG = "#2f2f2f"        # Fenster / Hauptfläche
UI_SUNKEN = "#262626"    # Eingabefelder, Listen, Arbeitsfläche
UI_RAISED = "#3a3a3a"    # Schaltflächen, Banner, Tooltips
UI_LINE = "#474747"      # Trennlinien, Rahmen
UI_TEXT = "#ececec"
UI_MUTED = "#a9adb0"     # Akzent helles Grau: Überschriften, Hinweise
UI_DISABLED = "#77797b"
UI_ACCENT = "#e8800c"    # Akzent Orange: Auswahl, Fokus, Hinweise
UI_ON_ACCENT = "#1c1c1c"
UI_ERROR = "#d9534f"     # ungültige oder doppelte Eingaben
IP_BAD_CSS = f"background:#4a2522; border: 1px solid {UI_ERROR};"   # ungültige IP
IP_DUP_CSS = f"background:#4a3a1c; border: 1px solid {UI_ACCENT};"  # doppelte IP
UNDO_LIMIT = 200         # so viele Schritte lassen sich rückgängig machen
CONFLICT_RED = "#e5413a"  # Tiefenkonflikte
INFO_BLUE = "#4a90d9"

# Zeichenfarben des Schranks: dunkel am Bildschirm, hell und druckfreundlich im PDF
RACK_INK = {
    "screen": {
        "title": UI_TEXT, "frame": "#3d3d3d", "frame_edge": "#1a1a1a", "inner": "#212121",
        "rail": UI_MUTED, "grid": "#2d2d2d", "rail_line": "#7b7f82", "hole": "#4b4e51",
        "number": "#1c1c1c", "feet": "#1a1a1a", "plate": "#8c9093", "plate_edge": "#55585b",
        "slot": "#6d7073", "bracket": "#6d7073", "shelf_text": "#c9ccce",
        "select": UI_ACCENT, "subtitle": UI_MUTED, "ghost": "#9aa0a6", "profile_bg": "#1b1b1b",
    },
    "print": {
        "title": "#222222", "frame": "#2b2f36", "frame_edge": "#1c1f24", "inner": "#f4f5f7",
        "rail": "#9aa0a8", "grid": "#d9dce1", "rail_line": "#6f757d", "hole": "#555b63",
        "number": "#1d1f22", "feet": "#1c1f24", "plate": "#aab3b5", "plate_edge": "#5f6a6a",
        "slot": "#7f8c8d", "bracket": "#7f8c8d", "shelf_text": "#2c3e50",
        "select": UI_ACCENT, "subtitle": "#555b63", "ghost": "#6f757d", "profile_bg": "#ffffff",
    },
}
INK = dict(RACK_INK["screen"])


def ink(key: str) -> QColor:
    return QColor(INK[key])


def apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)   # dunkle Titelleiste (Qt ≥ 6.8)
    except AttributeError:
        pass
    pal = QPalette()
    roles = {
        QPalette.Window: UI_BG, QPalette.WindowText: UI_TEXT,
        QPalette.Base: UI_SUNKEN, QPalette.AlternateBase: "#2b2b2b",
        QPalette.ToolTipBase: UI_RAISED, QPalette.ToolTipText: UI_TEXT,
        QPalette.PlaceholderText: "#8e9295",
        QPalette.Text: UI_TEXT, QPalette.Button: UI_RAISED, QPalette.ButtonText: UI_TEXT,
        QPalette.BrightText: "#ff6b5e", QPalette.Link: UI_ACCENT,
        QPalette.Highlight: UI_ACCENT, QPalette.HighlightedText: UI_ON_ACCENT,
        QPalette.Light: "#4a4a4a", QPalette.Midlight: "#424242", QPalette.Mid: "#383838",
        QPalette.Dark: "#1f1f1f", QPalette.Shadow: "#141414",
    }
    for role, c in roles.items():
        pal.setColor(role, QColor(c))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(UI_DISABLED))
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#555555"))
    pal.setColor(QPalette.Disabled, QPalette.Button, QColor("#333333"))
    app.setPalette(pal)
    # Häkchen für die Checkboxen: als PNG im Programm eingebettet (rack_resources.py),
    # damit keine Datei im Temp-Ordner entsteht (portabel).
    check_css = "image: url(:/check.png);"
    app.setStyleSheet(f"""
        QToolTip {{ color: {UI_TEXT}; background: {UI_RAISED}; border: 1px solid {UI_LINE};
                    padding: 4px 6px; }}
        QGroupBox {{ border: 1px solid {UI_LINE}; border-radius: 6px; margin-top: 14px;
                     padding: 10px 6px 6px 6px; }}
        QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
                            left: 10px; padding: 0 4px; color: {UI_MUTED}; font-weight: 600; }}
        QToolBar {{ background: #292929; border: none; border-bottom: 1px solid {UI_LINE};
                    spacing: 2px; padding: 3px; }}
        QMenuBar {{ background: #292929; }}
        QMenuBar::item:selected {{ background: {UI_RAISED}; }}
        QSplitter::handle {{ background: {UI_BG}; }}
        QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #8e9295;
                                border-radius: 3px; background: {UI_SUNKEN}; }}
        QCheckBox::indicator:hover {{ border-color: {UI_ACCENT}; }}
        QCheckBox::indicator:checked {{ background: {UI_ACCENT}; border-color: {UI_ACCENT};
                                        {check_css} }}
        QCheckBox::indicator:disabled {{ border-color: #555555; background: #2a2a2a; }}
    """)


def text_color(bg: QColor) -> QColor:
    lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    return QColor("#1b1b1b") if lum > 150 else QColor("#ffffff")
