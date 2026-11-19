"""Hinweis-Banner über der Schrankansicht."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from rackcore import (
    CAT_FIREWALL, SIDE_LABEL, Conflict, Item, Rack, fmt_date, fmt_range, other_side,
)

from .theme import CONFLICT_RED, UI_ACCENT, UI_ERROR, UI_ON_ACCENT, UI_RAISED, UI_TEXT


INFO, WARN, CLOCK = "info", "warn", "clock"


def _translucent(color: str, alpha: float = 0.94) -> str:
    """Banner liegen über der Zeichnung – leicht durchscheinend, damit man sie erahnt."""
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


class BannerHost(QWidget):
    """Ansicht mit darübergelegten Bannern.

    Die Banner stehen nicht mehr über der Ansicht im Layout, sondern schweben oben
    über der Zeichnung. So verschiebt ein auftauchender Hinweis weder die 2D-Zeichnung
    noch die 3D-Ansicht (z. B. während man die Kamera dreht). Der Bannerbereich ist nur
    so hoch wie die sichtbaren Banner; ohne Banner ist er ausgeblendet und fängt keine
    Mausklicks ab."""

    def __init__(self, view: QWidget, banners: list[QWidget]):
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._view = view
        self._grid.addWidget(view, 0, 0)
        self.box = QWidget()
        # Breite der Banner zählt nicht für das Layout: ein Banner darf die Mitte nicht
        # verbreitern (und damit die Seitenleisten schmaler machen)
        self.box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay = QVBoxLayout(self.box)
        self._box_lay = lay
        lay.setContentsMargins(10, 10, 10, 0)
        lay.setSpacing(6)
        self.banners = banners
        for b in banners:
            lay.addWidget(b)
            b.installEventFilter(self)
        self._grid.addWidget(self.box, 0, 0, Qt.AlignTop)
        self._sync()

    def set_view(self, view: QWidget):
        """Andere Ansicht unter die Banner legen (Desktop: Stapel aus 2D und 3D)."""
        self._grid.removeWidget(self._view)
        self._view = view
        self._grid.addWidget(view, 0, 0)
        self.box.raise_()

    def set_top(self, y: int):
        """Abstand der Banner vom oberen Rand (3D: unter Werkzeugleiste und Titel)."""
        self._box_lay.setContentsMargins(10, max(0, y), 10, 0)

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.ShowToParent, QEvent.HideToParent):
            self._sync()
        return False

    def _sync(self):
        self.box.setVisible(any(not b.isHidden() for b in self.banners))
        self.box.raise_()


class BannerIcon(QWidget):
    """Symbol des Banners, selbst gezeichnet.

    Früher waren das Schriftzeichen (ⓘ, ⚠, 🕘). Die Standardschrift unter Windows
    enthält sie nicht, deshalb hat Qt beim ersten Anzeigen eines Banners alle
    installierten Schriften nach einem Ersatz durchsucht – das hat das Programm beim
    ersten Gerät in einem neuen Schrank für ein bis zwei Sekunden eingefroren."""

    def __init__(self, kind: str, color: str):
        super().__init__()
        self.kind = kind
        self.color = QColor(color)
        self.setFixedSize(QSize(26, 26))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        c = self.color
        if self.kind == WARN:
            path = QPainterPath()
            path.moveTo(r.center().x(), r.top() + 1)
            path.lineTo(r.right(), r.bottom() - 1)
            path.lineTo(r.left(), r.bottom() - 1)
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawPath(path)
            mark = QColor(UI_RAISED)
            cx = r.center().x()
            p.setPen(QPen(mark, 2.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx, r.top() + 8), QPointF(cx, r.bottom() - 8))
            p.drawPoint(QPointF(cx, r.bottom() - 4.2))
            return
        p.setPen(QPen(c, 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(r)
        cx, cy = r.center().x(), r.center().y()
        if self.kind == CLOCK:
            p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx, cy), QPointF(cx, r.top() + 5))
            p.drawLine(QPointF(cx, cy), QPointF(r.right() - 6, cy + 2))
            return
        # Info: „i“ aus Punkt und Strich
        p.setPen(QPen(c, 2.6, Qt.SolidLine, Qt.RoundCap))
        p.drawPoint(QPointF(cx, r.top() + 6))
        p.drawLine(QPointF(cx, cy - 1), QPointF(cx, r.bottom() - 5.5))


class Banner(QFrame):
    """Banner mit Symbol, Text und optionalen Knöpfen."""

    _n = 0

    def __init__(self, color: str, icon: str):
        super().__init__()
        Banner._n += 1
        name = f"banner{Banner._n}"
        self.setObjectName(name)
        self.setStyleSheet(
            f"#{name} {{ background: {_translucent(UI_RAISED)}; border: 1px solid {color};"
            f" border-radius: 6px; }}"
            f"#{name} QLabel {{ color: {UI_TEXT}; background: transparent; border: none; }}"
            f"#{name} QPushButton {{ background: {color}; color: {UI_ON_ACCENT};"
            f" border: none; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}"
            f"#{name} QPushButton:hover {{ background: #f39327; }}"
            f"#{name} QPushButton[flat=\"true\"] {{ background: transparent; color: {UI_TEXT};"
            f" border: 1px solid #555; font-weight: 400; }}")
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(12, 8, 8, 8)
        ic = BannerIcon(icon, color)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.lay.addWidget(ic, 0, Qt.AlignVCenter)
        self.lay.addWidget(self.text, 1)
        self.hide()

    def add_button(self, text: str, slot, flat: bool = False) -> QPushButton:
        b = QPushButton(text)
        if flat:
            b.setProperty("flat", True)
        b.clicked.connect(slot)
        self.lay.addWidget(b)
        return b


class InfoBanner(Banner):
    """NAS/Firewall/Server ohne USV."""
    addUpsRequested = Signal()

    def __init__(self):
        super().__init__(UI_ACCENT, INFO)
        self.add_button("USV hinzufügen", self.addUpsRequested.emit)

    def update_for(self, missing: list[str]):
        if not missing:
            self.hide()
            return
        if len(missing) == 1:
            what = f"ein {missing[0]}" if missing[0] != CAT_FIREWALL else "eine Firewall"
        else:
            parts = [("eine Firewall" if m == CAT_FIREWALL else f"ein {m}") for m in missing]
            what = ", ".join(parts[:-1]) + " und " + parts[-1]
        self.text.setText(
            f"<b>Hinweis:</b> Im Schrank befindet sich {what}, aber keine USV. "
            "Eine unterbrechungsfreie Stromversorgung schützt vor Datenverlust bei "
            "Stromausfall und ermöglicht ein sauberes Herunterfahren.")
        self.show()


class WarnBanner(Banner):
    """Warnung bei doppelt vergebenen IP-Adressen."""

    def __init__(self):
        super().__init__(UI_ERROR, WARN)

    def update_for(self, dups: dict[str, list[Item]]):
        if not dups:
            self.hide()
            return
        parts = []
        for ip, devs in dups.items():
            names = list(dict.fromkeys(escape(d.label) for d in devs))
            who = ", ".join(names) if len(names) > 1 else f"{names[0]} (mehrfach eingetragen)"
            parts.append(f"<b>{escape(ip)}</b>: {who}")
        title = "Doppelte IP-Adresse" if len(dups) == 1 else "Doppelte IP-Adressen"
        self.text.setText(f"<b>{title}:</b> " + "; ".join(parts))
        self.show()


class DepthBanner(Banner):
    """Tiefenkonflikte (rot) – Klick auf „Zeigen“ wählt das erste betroffene Gerät."""
    showRequested = Signal(str)

    def __init__(self):
        super().__init__(CONFLICT_RED, WARN)
        self._uid = ""
        self.add_button("Zeigen", lambda: self.showRequested.emit(self._uid))

    def update_for(self, conflicts: list[Conflict]):
        if not conflicts:
            self.hide()
            return
        self._uid = conflicts[0].uids[-1]
        title = "Tiefenkonflikt" if len(conflicts) == 1 else f"{len(conflicts)} Tiefenkonflikte"
        lines = [escape(c.text) for c in conflicts[:4]]
        if len(conflicts) > 4:
            lines.append(f"… und {len(conflicts) - 4} weitere (rot markiert)")
        self.text.setText(f"<b>{title}:</b><br>" + "<br>".join(lines))
        self.show()


class RailBanner(Banner):
    """Hinweis: Geräte auf Einbauschienen blockieren die Gegenseite."""

    def __init__(self):
        super().__init__(UI_ACCENT, INFO)
        self.add_button("Ausblenden", self._dismiss, flat=True)
        self._dismissed: set[str] = set()
        self._key = ""

    def _dismiss(self):
        self._dismissed.add(self._key)
        self.hide()

    def update_for(self, rack: Rack, side: str):
        """Zeigt in der Ansicht einer Seite, welche HE dort durch Schienen der
        Gegenseite blockiert sind (nur solange dort noch nichts montiert ist)."""
        rails = [i for i in rack.top_level(other_side(side)) if i.rails]
        self._key = side + "|" + ",".join(sorted(i.uid for i in rails))
        if not rails or self._key in self._dismissed:
            self.hide()
            return
        parts = [f"„{escape(i.label)}“ (HE {fmt_range(i.position, rack.span(i))})"
                 for i in rails[:4]]
        more = f" und {len(rails) - 4} weitere" if len(rails) > 4 else ""
        verb = "sitzt" if len(rails) == 1 else "sitzen"
        self.text.setText(
            f"<b>Einbauschienen:</b> {', '.join(parts)}{more} {verb} auf der "
            f"{SIDE_LABEL[other_side(side)]} auf Schienen. Diese HE sind auf der "
            f"{SIDE_LABEL[side]} blockiert (orange schraffiert) – große Geräte wie USV, Server "
            "und Rack-NAS werden meist mit Schienen montiert.")
        self.show()


class PreviewBanner(Banner):
    """Hinweis, während ein früherer Stand aus der Historie angezeigt wird."""
    restoreRequested = Signal()
    closeRequested = Signal()

    def __init__(self):
        super().__init__(UI_ACCENT, CLOCK)
        self.add_button("Wiederherstellen", self.restoreRequested.emit)
        self.add_button("Zurück zum aktuellen Stand", self.closeRequested.emit, flat=True)

    def show_for(self, as_of: str, saved_at: str):
        when = saved_at.replace("T", " ")[:16]
        d, _, t = when.partition(" ")
        saved = f", gespeichert am {fmt_date(d)} {t}".rstrip() if d else ""
        self.text.setText(
            f"<b>Historie:</b> Du siehst den Stand vom {escape(fmt_date(as_of))}{saved} – "
            "nur zum Ansehen. Bearbeitet wird weiterhin der aktuelle Stand.")
        self.show()
