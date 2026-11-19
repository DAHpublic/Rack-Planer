"""Hilfe: „Infos über Rack-Planer“ und ein kurzes Tutorial im Stil einer Spiel-Einführung.

Das Tutorial legt eine abgedunkelte Ebene über das Fenster, hebt den jeweils besprochenen
Bereich hervor und erklärt ihn in einer Sprechblase. Weiter mit Enter/→, zurück mit ←,
beenden mit Esc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from rackcore import APP_NAME, FORMAT_VERSION

from . import APP_AUTHOR, APP_VERSION, EDITION
from .theme import UI_ACCENT, UI_LINE, UI_MUTED, UI_ON_ACCENT, UI_RAISED, UI_TEXT


def show_about(parent):
    QMessageBox.about(
        parent, f"Infos über {APP_NAME}",
        f"<h3 style='margin-bottom:2px'>{APP_NAME} {APP_VERSION}</h3>"
        f"<p style='margin-top:0'><b>{EDITION}</b> · Dateiformat {FORMAT_VERSION}<br>"
        f"Entwickler: {APP_AUTHOR}</p>"
        "<p>Serverschränke planen: Höheneinheiten, Vorder- und Rückseite, Einbautiefe, "
        "Geräte, Fachböden, Beschriftung mit IP-Adressen, Leistung und Wärmelast, "
        "Export als PDF, PNG und SVG, Historie früherer Stände.</p>"
        "<p>Portabel: Das Programm legt keine Einstellungen oder Hilfsdateien an.</p>"
        "<p>Freie Software unter der MIT-Lizenz. Verwendet Qt 6 und PySide6 (GNU LGPL v3); "
        "Details unter <b>Hilfe → Lizenzen</b> und <b>Hilfe → Über Qt</b>.</p>"
        "<p>Kurze Einführung: <b>Hilfe → Tutorial</b> (F1).</p>")


@dataclass
class Step:
    title: str
    text: str
    target: Callable[[], QRect | None] | None = None   # Bereich in Fensterkoordinaten


class TutorialOverlay(QWidget):
    """Abgedunkelte Ebene mit hervorgehobenem Bereich und Sprechblase."""

    BUBBLE_W = 360

    def __init__(self, window: QWidget, steps: list[Step]):
        super().__init__(window)
        self.win = window
        self.steps = steps
        self.i = 0
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.bubble = QWidget(self)
        self.bubble.setObjectName("tutbubble")
        self.bubble.setStyleSheet(
            f"#tutbubble {{ background: {UI_RAISED}; border: 2px solid {UI_ACCENT};"
            f" border-radius: 10px; }}"
            f"#tutbubble QLabel {{ color: {UI_TEXT}; background: transparent; border: none; }}"
            f"#tutbubble QPushButton {{ background: {UI_ACCENT}; color: {UI_ON_ACCENT};"
            f" border: none; border-radius: 5px; padding: 6px 14px; font-weight: 700; }}"
            f"#tutbubble QPushButton#flat {{ background: transparent; color: {UI_MUTED};"
            f" border: 1px solid {UI_LINE}; font-weight: 400; }}")
        bl = QVBoxLayout(self.bubble)
        bl.setContentsMargins(16, 12, 16, 12)
        self.counter = QLabel()
        self.counter.setStyleSheet(f"color:{UI_ACCENT}; font-weight:700; letter-spacing:1px;")
        self.title = QLabel()
        f = QFont(self.title.font())
        f.setPointSizeF(f.pointSizeF() * 1.35)
        f.setBold(True)
        self.title.setFont(f)
        self.title.setWordWrap(True)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.RichText)
        bl.addWidget(self.counter)
        bl.addWidget(self.title)
        bl.addWidget(self.text)
        row = QHBoxLayout()
        self.b_skip = QPushButton("Tour beenden")
        self.b_skip.setObjectName("flat")
        self.b_back = QPushButton("◀ Zurück")
        self.b_back.setObjectName("flat")
        self.b_next = QPushButton("Weiter ▶")
        self.b_skip.clicked.connect(self.finish)
        self.b_back.clicked.connect(self.back)
        self.b_next.clicked.connect(self.next)
        for b in (self.b_skip, self.b_back, self.b_next):
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
        row.addWidget(self.b_skip)
        row.addStretch()
        row.addWidget(self.b_back)
        row.addWidget(self.b_next)
        bl.addLayout(row)
        self.bubble.setFixedWidth(self.BUBBLE_W)
        window.installEventFilter(self)

    # --- Steuerung ---------------------------------------------------------
    def start(self):
        self.setGeometry(self.win.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._show_step()

    def next(self):
        if self.i >= len(self.steps) - 1:
            self.finish()
            return
        self.i += 1
        self._show_step()

    def back(self):
        if self.i > 0:
            self.i -= 1
            self._show_step()

    def finish(self):
        self.win.removeEventFilter(self)
        self.hide()
        self.deleteLater()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.finish()
        elif e.key() in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.next()
        elif e.key() == Qt.Key_Left:
            self.back()

    def mousePressEvent(self, e):
        e.accept()          # Klicks gehen nicht an das Fenster darunter

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Resize:
            self.setGeometry(self.win.rect())
            self._place()
        return False

    # --- Darstellung -------------------------------------------------------
    def _target(self) -> QRect | None:
        st = self.steps[self.i]
        if st.target is None:
            return None
        try:
            r = st.target()
        except RuntimeError:
            return None
        return r.adjusted(-6, -6, 6, 6) if r is not None and r.isValid() else None

    def _show_step(self):
        st = self.steps[self.i]
        n = len(self.steps)
        dots = "●" * (self.i + 1) + "○" * (n - self.i - 1)
        self.counter.setText(f"SCHRITT {self.i + 1}/{n}   {dots}")
        self.title.setText(st.title)
        self.text.setText(st.text)
        self.b_back.setVisible(self.i > 0)
        self.b_next.setText("Los geht's! ✔" if self.i == n - 1 else "Weiter ▶")
        self._place()
        self.update()

    def _place(self):
        self.bubble.adjustSize()
        bw, bh = self.bubble.width(), self.bubble.sizeHint().height()
        W, H = self.width(), self.height()
        t = self._target()
        if t is None:
            pos = QPoint((W - bw) // 2, (H - bh) // 2)
        else:
            gap = 18
            cands = [QPoint(t.right() + gap, t.top()),            # rechts
                     QPoint(t.left() - gap - bw, t.top()),        # links
                     QPoint(t.left(), t.bottom() + gap),          # darunter
                     QPoint(t.left(), t.top() - gap - bh)]        # darüber
            pos = None
            for c in cands:
                if c.x() >= 8 and c.x() + bw <= W - 8 and c.y() + bh <= H - 8 and c.y() >= 8:
                    pos = c
                    break
            if pos is None:
                pos = QPoint(max(8, min(t.center().x() - bw // 2, W - bw - 8)),
                             max(8, min(t.center().y() - bh // 2, H - bh - 8)))
            pos.setY(max(8, min(pos.y(), H - bh - 8)))
        self.bubble.setGeometry(pos.x(), pos.y(), bw, bh)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        t = self._target()
        if t is not None:
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(t), 10, 10)
            path = path.subtracted(hole)
        p.fillPath(path, QColor(0, 0, 0, 165))
        if t is not None:
            glow = QColor(UI_ACCENT)
            for w, a in ((9, 40), (5, 90), (2.5, 255)):
                glow.setAlpha(a)
                p.setPen(QPen(glow, w))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(QRectF(t), 10, 10)


def tutorial_steps(win) -> list[Step]:
    """Schritte des Tutorials; die Ziele werden erst beim Anzeigen ermittelt."""

    def rect_of(widget) -> QRect | None:
        if widget is None or not widget.isVisible():
            return None
        return QRect(widget.mapTo(win, QPoint(0, 0)), widget.size())

    def action_rect(*actions) -> QRect | None:
        rects = [rect_of(win.toolbar.widgetForAction(a)) for a in actions]
        rects = [r for r in rects if r is not None]
        if not rects:
            return None
        out = rects[0]
        for r in rects[1:]:
            out = out.united(r)
        return out

    def profile_rect() -> QRect | None:
        v = win.view
        r = v.profile_scene_rect()
        if r is None:
            return None
        poly = v.mapFromScene(r).boundingRect()
        poly = poly.intersected(v.viewport().rect())
        if poly.isEmpty():
            return None
        return QRect(v.viewport().mapTo(win, poly.topLeft()), poly.size())

    return [
        Step("Willkommen beim Rack-Planer! 👋",
             "In wenigen Schritten lernst du alle wichtigen Funktionen kennen.<br><br>"
             "Weiter mit <b>Enter</b> oder <b>→</b>, zurück mit <b>←</b>, "
             "beenden mit <b>Esc</b>."),
        Step("Dein Schrank",
             "Hier legst du <b>Bezeichnung</b>, <b>Höhe</b> in HE, die nutzbare "
             "<b>Einbautiefe</b> und den <b>aktuellen Stand</b> fest. Das Datum erscheint auf "
             "jedem Export unter dem Titel.",
             lambda: rect_of(win.rack_box)),
        Step("Geräte-Vorlagen",
             "Über 80 Geräte mit echten Maßen, Leistung und Tiefe. <b>Strg + F</b> sucht, "
             "<b>Doppelklick</b> baut ein. <span style='color:#e8800c'>Orange</span> = nicht "
             "rackfähig, kommt auf einen Fachboden.",
             lambda: rect_of(win.tpl_box)),
        Step("Bauen per Drag & Drop",
             "Ziehe Geräte mit der Maus an ihren Platz: <span style='color:#2ecc71'>grün</span> "
             "= frei, <span style='color:#e74c3c'>rot</span> = belegt. "
             "<b>Strg + Mausrad</b> zoomt, <b>Entf</b> entfernt.",
             lambda: rect_of(win.view)),
        Step("Vorder- und Rückseite",
             "Schalte zwischen den Seiten um (<b>Strg + R</b>). Neue Geräte werden auf der Seite "
             "montiert, die du gerade siehst. Geräte der Gegenseite sind <i>gestrichelt</i> "
             "angedeutet – mit der freien Tiefe. Doppelklick darauf wechselt die Seite.",
             lambda: action_rect(win.act_front, win.act_rear)),
        Step("Tiefe im Blick",
             "Die <b>Seitenansicht</b> zeigt die Tiefe als Kapazität – immer vorne links, "
             "hinten rechts. Beispiel: 800 mm Schrank, hinten 50 mm Steckdosenleiste – vorne "
             "bleiben 750 mm. Fachböden siehst du mit den Geräten darauf.",
             profile_rect),
        Step("Seitenansicht ein- und ausblenden ☑",
             "Mit dem Häkchen <b>„Seitenansicht“</b> oben in der Leiste blendest du die "
             "Seitenansicht ein oder aus – zum Beispiel, wenn du mehr Platz für den Schrank "
             "möchtest. Dasselbe geht über <b>Ansicht → Seitenansicht</b>.",
             lambda: rect_of(win.cb_profile)),
        Step("Konflikte erkennen ⚠",
             "Reicht die Tiefe nicht oder blockieren <b>Einbauschienen</b> (USV, Server, "
             "Rack-NAS) die Gegenseite, wird das betroffene Gerät <span style='color:#e5413a'>"
             "rot</span> markiert und ein Banner erklärt das Problem.",
             lambda: rect_of(win.view)),
        Step("Eigenschaften",
             "Name, bis zu 5 IP-Adressen, Höhe, <b>Tiefe</b>, <b>Montageseite</b> und "
             "<b>Schienen</b> des ausgewählten Geräts.",
             lambda: rect_of(win.props)),
        Step("Alle Geräte auf einen Blick",
             "Die Liste zeigt jedes Gerät mit HE, Seite, IP und Leistung. Unten in der "
             "Statusleiste stehen Belegung, Leistung und Wärmelast.",
             lambda: rect_of(win.list_box)),
        Step("Zeitreise mit der Historie 🕘",
             "Im Tab <b>„Historie“</b> neben „Geräte im Schrank“ findest du frühere Stände. "
             "Ein Klick zeigt den Stand im Schrank an (nur ansehen), „Wiederherstellen“ "
             "übernimmt ihn, „Als eigene Datei“ speichert ihn separat.",
             lambda: rect_of(win.list_box)),
        Step("Exportieren",
             "Unter <b>Exportieren</b>: <b>als PDF</b> mit Vorder- und/oder Rückseite oder "
             "<b>als Bild</b> einer Seite (PNG oder SVG) – mit Titel und Stand, auf Wunsch mit "
             "maximaler Strom- und Wärmelast.",
             lambda: action_rect(win.act_export)),
        Step("Speichern",
             "Alles zu einem Schrank steckt in <b>einer Datei</b>, auch die Historie. Änderst "
             "du eine gespeicherte Datei, fragt der Planer, ob eine Historie angelegt werden "
             "soll. <b>Strg + Z</b> macht jeden Schritt rückgängig.",
             lambda: action_rect(win.act_save)),
        Step("Geschafft! 🎉",
             "Viel Spaß beim Planen. Das Tutorial findest du jederzeit unter "
             "<b>Hilfe → Tutorial</b> (F1)."),
    ]
