"""Grafik des Schranks: Rahmen, Geräte, Gegenseite, Seitenansicht (Tiefe) und Ansicht."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsItem, QGraphicsScene, QGraphicsView

from rackcore import (
    CATEGORY_COLORS, FRONT, SHELF_WIDTH_MM, SIDE_LABEL, SIDE_SHORT, U_MM, Item, Rack,
    fmt_date, fmt_range, other_side, snap_third,
)

from .theme import CONFLICT_RED, UI_ACCENT, UI_SUNKEN, ink, text_color as _text_color

U_PX = 32.0             # Höhe einer HE in Szeneneinheiten
INNER_W = 440.0         # Innenbreite (19")
RAIL_W = 34.0           # Breite der Profilschienen
FRAME = 14.0            # Rahmenstärke
TITLE_H = 54.0          # Titel + „Stand“
RACK_W = INNER_W + 2 * RAIL_W + 2 * FRAME
PROFILE_GAP = 34.0      # Abstand Schrank – Seitenansicht
PROFILE_W = 150.0       # Breite der Seitenansicht (= Schranktiefe)


class RackGeometry:
    def __init__(self, rack: Rack):
        self.rack = rack
        self.top = TITLE_H + FRAME
        self.left = FRAME + RAIL_W

    def y_for(self, pos: float, span: float) -> float:
        """Obere Kante eines Bereichs ab HE pos mit span HE."""
        return self.top + (self.rack.height_u - (pos + span - 1)) * U_PX

    def unit_at(self, y: float) -> float:
        """Stufenlose Höhe in HE (1 = Unterkante des Schranks)."""
        return self.rack.height_u + 1 - (y - self.top) / U_PX

    def total_height(self) -> float:
        return TITLE_H + 2 * FRAME + self.rack.height_u * U_PX + 30


def _px(pt: float) -> int:
    """Schriftgröße in Szeneneinheiten – unabhängig von der DPI des Ausgabegeräts (PDF)."""
    return round(pt * 96 / 72)


def depth_tooltip(rack: Rack, item: Item) -> list[str]:
    """Tooltip-Zeilen zu Montageseite, Tiefe, Schienen und Gegenseite."""
    top = rack.top_of(item)
    side = top.mount_side
    out = []
    d = item.depth_mm
    out.append(f"Montiert {SIDE_SHORT[side]}, Tiefe {d} mm" if d else
               f"Montiert {SIDE_SHORT[side]}, Tiefe unbekannt")
    if item.rails:
        out.append("Auf Einbauschienen (blockiert die Gegenseite)")
    span = rack.span(top)
    facing = rack.facing(top.position, span, side, ignore=top.uid)
    if facing:
        names = ", ".join(f"{o.label} ({rack.depth_of(o)} mm)" for o in facing)
        out.append(f"{SIDE_LABEL[other_side(side)]}: {names}")
    out.append(f"Freie Tiefe hier: {rack.free_depth(top.position, span, side, top.uid)} mm "
               f"von {rack.depth_mm} mm")
    return out


class RackFrameItem(QGraphicsItem):
    def __init__(self, rack: Rack, side: str = FRONT, side_label: bool = True,
                 footer: str = ""):
        super().__init__()
        self.rack = rack
        self.side = side
        self.side_label = side_label
        self.footer = footer
        self.geo = RackGeometry(rack)
        self.setZValue(-10)

    def boundingRect(self) -> QRectF:
        if self.footer:     # Zeile unter dem Schrank darf breiter sein als der Schrank
            return QRectF(-60, -2, RACK_W + 120, self.geo.total_height() + 4)
        return QRectF(-2, -2, RACK_W + 4, self.geo.total_height() + 4)

    def paint(self, p: QPainter, option, widget=None):
        g = self.geo
        h = self.rack.height_u * U_PX
        p.setRenderHint(QPainter.Antialiasing)

        # Titel und „Aktueller Stand“
        f = QFont(p.font())
        f.setPixelSize(_px(13))
        f.setBold(True)
        p.setFont(f)
        p.setPen(ink("title"))
        title = f"{self.rack.name}  ({self.rack.height_u} HE)"
        if self.side_label:
            title += f" – {SIDE_LABEL[self.side]}"
        fm = QFontMetricsF(f)
        p.drawText(QRectF(-60, 0, RACK_W + 120, 26), Qt.AlignHCenter | Qt.AlignBottom,
                   fm.elidedText(title, Qt.ElideRight, RACK_W + 120))
        if self.rack.as_of:
            f.setPixelSize(_px(8.5))
            f.setBold(False)
            p.setFont(f)
            p.setPen(ink("subtitle"))
            p.drawText(QRectF(0, 27, RACK_W, 18), Qt.AlignHCenter | Qt.AlignVCenter,
                       f"Stand: {fmt_date(self.rack.as_of)}")

        # Rahmen
        outer = QRectF(0, TITLE_H, RACK_W, h + 2 * FRAME)
        p.setPen(QPen(ink("frame_edge"), 1.5))
        p.setBrush(ink("frame"))
        p.drawRoundedRect(outer, 6, 6)
        # Innenraum
        p.setPen(Qt.NoPen)
        p.setBrush(ink("inner"))
        p.drawRect(QRectF(g.left, g.top, INNER_W, h))
        # Schienen
        p.setBrush(ink("rail"))
        for x in (FRAME, FRAME + RAIL_W + INNER_W):
            p.drawRect(QRectF(x, g.top, RAIL_W, h))

        # HE-Raster und Nummern
        f.setPixelSize(_px(7.5))
        f.setBold(False)
        p.setFont(f)
        for i in range(self.rack.height_u):
            u = self.rack.height_u - i
            y = g.top + i * U_PX
            p.setPen(QPen(ink("grid"), 0.8))
            p.drawLine(QPointF(g.left, y), QPointF(g.left + INNER_W, y))
            p.setPen(QPen(ink("rail_line"), 0.8))
            p.drawLine(QPointF(FRAME, y), QPointF(FRAME + RAIL_W, y))
            p.drawLine(QPointF(FRAME + RAIL_W + INNER_W, y), QPointF(RACK_W - FRAME, y))
            # Montagelöcher
            p.setBrush(ink("hole"))
            p.setPen(Qt.NoPen)
            for k in (0.2, 0.5, 0.8):
                for x in (FRAME + RAIL_W - 7, FRAME + RAIL_W + INNER_W + 4):
                    p.drawRect(QRectF(x, y + U_PX * k - 1.5, 3, 3))
            p.setPen(ink("number"))
            p.drawText(QRectF(FRAME + 2, y, RAIL_W - 12, U_PX), Qt.AlignCenter, str(u))
            p.drawText(QRectF(FRAME + RAIL_W + INNER_W + 9, y, RAIL_W - 12, U_PX),
                       Qt.AlignCenter, str(u))
        # Füße
        p.setBrush(ink("feet"))
        p.setPen(Qt.NoPen)
        fy = TITLE_H + h + 2 * FRAME
        p.drawRect(QRectF(10, fy, 26, 8))
        p.drawRect(QRectF(RACK_W - 36, fy, 26, 8))
        if self.footer:
            f.setPixelSize(_px(8.5))
            p.setFont(f)
            p.setPen(ink("title"))
            p.drawText(QRectF(-60, fy + 10, RACK_W + 120, 20), Qt.AlignHCenter | Qt.AlignVCenter,
                       self.footer)


class ElementItem(QGraphicsItem):
    """Ein Gerät oder Fachboden im Schrank."""

    def __init__(self, rack: Rack, item: Item, rect: QRectF, selected: bool,
                 conflict: bool = False, interactive: bool = True):
        super().__init__()
        self.rack = rack
        self.item = item
        self.rect = rect
        self.selected = selected
        self.conflict = conflict
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(1)
        tip = [item.name or item.model]
        if item.model and item.model != item.name:
            tip.append(item.model)
        ips = item.all_ips()
        if ips:
            tip.append(("IP: " if len(ips) == 1 else "IPs: ") + ", ".join(ips))
        tip.append(f"{item.category}, {item.height_u} HE")
        if item.power_w:
            tip.append(f"{item.power_w:g} W")
        tip += depth_tooltip(rack, item)
        self.setToolTip("\n".join(tip))
        if not interactive:
            self.setCursor(Qt.ArrowCursor)
            self.setAcceptedMouseButtons(Qt.NoButton)

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-3, -3, 3, 3)

    def paint(self, p: QPainter, option, widget=None):
        it = self.item
        r = self.rect
        p.setRenderHint(QPainter.Antialiasing)
        if it.is_shelf:
            self._paint_shelf(p, r)
        else:
            self._paint_device(p, r)
        if self.conflict:
            p.setBrush(QBrush(QColor(CONFLICT_RED).lighter(110), Qt.FDiagPattern))
            p.setPen(QPen(QColor(CONFLICT_RED), 2.5, Qt.DashLine))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        if self.selected:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(ink("select"), 3))
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 4, 4)

    def _paint_shelf(self, p: QPainter, r: QRectF):
        plate_h = PLATE_H
        plate = QRectF(r.left() - EAR_W, r.bottom() - plate_h, r.width() + 2 * EAR_W, plate_h)
        p.setPen(QPen(ink("plate_edge"), 1))
        p.setBrush(ink("plate"))
        p.drawRect(plate)
        # Lüftungsschlitze
        p.setPen(QPen(ink("slot"), 1))
        x = plate.left() + 40
        while x < plate.right() - 40:
            p.drawLine(QPointF(x, plate.top() + 2), QPointF(x + 10, plate.top() + 2))
            x += 18
        # Halterung bis zur Schienenebene
        p.setBrush(ink("bracket"))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(plate.left(), r.top() + 2, 5, r.height() - 2))
        p.drawRect(QRectF(plate.right() - 5, r.top() + 2, 5, r.height() - 2))
        f = QFont(p.font())
        f.setPixelSize(_px(7))
        p.setFont(f)
        p.setPen(ink("shelf_text"))
        if self.item.show_name:
            p.drawText(r.adjusted(8, 0, -8, -plate_h - 1), Qt.AlignRight | Qt.AlignVCenter,
                       self.item.name or "Fachboden")

    def _paint_ip_grid(self, p: QPainter, rect: QRectF, name: str, ips: list[str],
                       f_name: QFont, f_small: QFont):
        """Name/Modell links, IP-Adressen als Raster rechts daneben oder darunter.
        Die Schrift wird bei Bedarf verkleinert, damit sich nichts überschneidet."""
        it = self.item
        heads: list[tuple[str, QFont]] = [(name, f_name)] if it.show_name else []
        if it.model and (it.model != name or not it.show_name):
            heads.append((it.model, f_small))
        gap = 10.0

        def draw_heads(area: QRectF, hs):
            hh = [QFontMetricsF(f).height() for _, f in hs]
            while hs and sum(hh) > area.height() + 0.5:
                hs = hs[:-1]
                hh = hh[:-1]
            y = area.top() + (area.height() - sum(hh)) / 2
            for (txt, fn), lh in zip(hs, hh):
                p.setFont(fn)
                fm = QFontMetricsF(fn)
                p.drawText(QRectF(area.left(), y, area.width(), lh), Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(txt, Qt.ElideRight, area.width()))
                y += lh

        def grid(fm: QFontMetricsF, items, max_rows: int):
            """Spalten (spaltenweise gefüllt) mit eigener Breite je Spalte."""
            n = len(items)
            cols = math.ceil(n / max(1, min(max_rows, n)))
            rows = math.ceil(n / cols)
            widths = [max(fm.horizontalAdvance(a) for a in items[c * rows:(c + 1) * rows]) + gap
                      for c in range(cols)]
            return rows, widths, sum(widths) - gap

        def draw_grid(x0: float, y0: float, rows: int, widths, fs: QFont, items):
            p.setFont(fs)
            lh = QFontMetricsF(fs).height()
            x = x0
            for c, w in enumerate(widths):
                for r_, txt in enumerate(items[c * rows:(c + 1) * rows]):
                    p.drawText(QRectF(x, y0 + r_ * lh, w, lh), Qt.AlignLeft | Qt.AlignVCenter, txt)
                x += w

        for px in range(f_small.pixelSize(), 6, -1):
            fs = QFont(f_small)
            fs.setPixelSize(px)
            fm = QFontMetricsF(fs)
            lh = fm.height()
            rows_fit = int(rect.height() // lh)
            if rows_fit < 1:
                continue
            # A: Raster rechts neben dem Namen
            rows, widths, grid_w = grid(fm, ips, rows_fit)
            name_w = rect.width() - grid_w - 12
            if grid_w <= rect.width() and (not heads or name_w >= min(90.0, rect.width() * 0.35)):
                x0 = rect.right() - grid_w if heads else rect.left()
                draw_grid(x0, rect.top() + (rect.height() - rows * lh) / 2, rows, widths, fs, ips)
                if heads:
                    draw_heads(QRectF(rect.left(), rect.top(), name_w, rect.height()), heads)
                return
            # B: Raster unter dem Namen
            hs = heads[:1]
            hh = sum(QFontMetricsF(f).height() for _, f in hs)
            rows_b = int((rect.height() - hh) // lh)
            if rows_b >= 1:
                rows, widths, grid_w = grid(fm, ips, rows_b)
                if grid_w <= rect.width():
                    y0 = rect.top() + (rect.height() - hh - rows * lh) / 2
                    if hs:
                        draw_heads(QRectF(rect.left(), y0, rect.width(), hh), hs)
                    draw_grid(rect.left(), y0 + hh, rows, widths, fs, ips)
                    return
        # Zu wenig Platz: Name und so viele IPs wie passen, Rest als "+N" (alle im Tooltip)
        fs = QFont(f_small)
        fs.setPixelSize(7)
        fm = QFontMetricsF(fs)
        lh = fm.height()
        hs = [(heads[0][0], QFont(fs))] if heads else []
        for _, f in hs:
            f.setBold(True)
        hh = lh if hs and rect.height() >= 2 * lh else 0.0
        rows = max(1, int((rect.height() - hh) // lh))
        shown = list(ips)
        while len(shown) > 1:
            r_, widths, gw = grid(fm, shown, rows)
            if gw <= rect.width():
                break
            rest = len(ips) - (len(shown) - 1) + 1
            shown = ips[:len(shown) - 2] + [f"+{rest}"]
        r_, widths, gw = grid(fm, shown, rows)
        y0 = rect.top() + (rect.height() - hh - r_ * lh) / 2
        if hh:
            draw_heads(QRectF(rect.left(), y0, rect.width(), hh), hs)
        draw_grid(rect.left(), y0 + hh, r_, widths, fs, shown)

    def _paint_device(self, p: QPainter, r: QRectF):
        it = self.item
        base = QColor(CATEGORY_COLORS.get(it.category, "#2e86c1"))
        fg = _text_color(base)
        body = r.adjusted(1, 1, -1, -1)
        if it.rackmount and not it.shelf_id:
            # Rackohren
            p.setPen(Qt.NoPen)
            p.setBrush(base.darker(130))
            # nur über den Schraubenlöchern, damit die HE-Nummern sichtbar bleiben
            p.drawRect(QRectF(body.left() - EAR_W, body.top(), EAR_W, body.height()))
            p.drawRect(QRectF(body.right(), body.top(), EAR_W, body.height()))
        p.setPen(QPen(base.darker(160), 1))
        p.setBrush(base)
        p.drawRoundedRect(body, 3, 3)
        if not it.rackmount and not it.shelf_id:
            # Nicht rackfähig und ohne Fachboden: schraffiert
            p.setBrush(QBrush(QColor(255, 255, 255, 70), Qt.BDiagPattern))
            p.drawRoundedRect(body, 3, 3)

        # LEDs
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#7CFC00"))
        led_x = body.right() - 10
        p.drawEllipse(QPointF(led_x, body.top() + 7), 2.2, 2.2)

        # Text
        pad = 8
        text_rect = body.adjusted(pad, 2, -18, -2)
        f_name = QFont(p.font())
        f_name.setBold(True)
        f_small = QFont(p.font())
        f_small.setBold(False)
        narrow = text_rect.width() < 140
        f_name.setPixelSize(_px(8 if narrow else 9.5))
        f_small.setPixelSize(_px(7 if narrow else 8))
        name = it.name or it.model or it.category
        ips = it.all_ips()
        p.setPen(fg)
        if len(ips) > 1:
            self._paint_ip_grid(p, text_rect, name, ips, f_name, f_small)
            return
        lines: list[tuple[str, QFont]] = [(name, f_name)] if it.show_name else []
        if ips:
            lines.append((ips[0], f_small))
        if it.model and (it.model != name or not it.show_name):
            lines.append((it.model, f_small))

        p.setPen(fg)
        if it.height_u == 1 and not narrow and len(lines) > 1 and it.show_name:
            # Eine Zeile: Name links, IP rechts
            p.setFont(f_small)
            fm = QFontMetricsF(f_small)
            right = (ips[0] if ips else "") or it.model
            rw = min(fm.horizontalAdvance(right) + 4, text_rect.width() * 0.45)
            p.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter,
                       fm.elidedText(right, Qt.ElideRight, rw))
            p.setFont(f_name)
            fmn = QFontMetricsF(f_name)
            p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                       fmn.elidedText(name, Qt.ElideRight, text_rect.width() - rw - 8))
            return

        # Mehrzeilig, vertikal zentriert, nur so viele Zeilen wie passen
        heights = [QFontMetricsF(fn).height() for _, fn in lines]
        while lines and sum(heights) > text_rect.height():
            lines.pop()
            heights.pop()
        y = text_rect.top() + (text_rect.height() - sum(heights)) / 2
        for (txt, fn), lh in zip(lines, heights):
            p.setFont(fn)
            fm = QFontMetricsF(fn)
            p.drawText(QRectF(text_rect.left(), y, text_rect.width(), lh),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(txt, Qt.ElideRight, text_rect.width()))
            y += lh




EAR_W = 10                      # Rackohren/Fachboden ragen nur so weit auf die Schienen
PLATE_H = U_PX / 3              # Bodenplatte des Fachbodens: unteres Drittel der HE
SHELF_SCALE = (INNER_W - 8) / SHELF_WIDTH_MM   # Szeneneinheiten je mm auf dem Fachboden


def device_height_px(d: Item) -> float:
    if d.height_cm > 0:
        return min(d.height_u * U_PX, d.height_cm * 10 / U_MM * U_PX)
    return d.height_u * U_PX


def shelf_rect_for(geo: "RackGeometry", rack: Rack, shelf: Item) -> QRectF:
    span = rack.span(shelf)
    top = geo.y_for(shelf.position, span)
    return QRectF(geo.left, top + (span - shelf.height_u) * U_PX, INNER_W,
                  shelf.height_u * U_PX)


def shelf_device_rect(geo: "RackGeometry", shelf_rect: QRectF, d: Item, offset: int) -> QRectF:
    w = max(16.0, d.width_mm * SHELF_SCALE)
    h = device_height_px(d)
    # Gerät steht direkt auf der Bodenplatte (unteres Drittel der HE)
    bottom = shelf_rect.bottom() - PLATE_H
    return QRectF(geo.left + 4 + offset * SHELF_SCALE, bottom - h, w - 2, h)


class GhostItem(QGraphicsItem):
    """Gerät der Gegenseite, angedeutet (gestrichelt) – mit Hinweis auf die freie Tiefe.
    Doppelklick wechselt auf die andere Seite."""

    def __init__(self, rack: Rack, item: Item, rect: QRectF, side: str):
        super().__init__()
        self.rack = rack
        self.item = item
        self.rect = rect
        self.side = side            # angezeigte Seite (das Gerät sitzt auf der Gegenseite)
        self.setZValue(0)
        span = rack.span(item)
        self.free = max(0, rack.depth_mm - rack.depth_of(item))
        self.blocked = item.rails
        lines = [f"{SIDE_LABEL[item.mount_side]}: {item.label}",
                 f"HE {fmt_range(item.position, span)} · Tiefe {rack.depth_of(item)} mm"]
        if self.blocked:
            lines.append(f"Einbauschienen: auf der {SIDE_LABEL[side]} ist hier nichts montierbar.")
        else:
            lines.append(f"Auf der {SIDE_LABEL[side]} frei: {self.free} mm Tiefe")
        lines.append("Doppelklick: zur anderen Seite wechseln")
        self.setToolTip("\n".join(lines))

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, p: QPainter, option, widget=None):
        r = self.rect.adjusted(2, 2, -2, -2)
        base = QColor(CATEGORY_COLORS.get(self.item.category, "#888888"))
        p.setRenderHint(QPainter.Antialiasing)
        fill = QColor(base)
        fill.setAlpha(45)
        p.setBrush(fill)
        p.setPen(QPen(ink("ghost"), 1.2, Qt.DashLine))
        p.drawRoundedRect(r, 3, 3)
        if self.blocked:
            p.setBrush(QBrush(QColor(UI_ACCENT), Qt.BDiagPattern))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, 3, 3)
        f = QFont(p.font())
        f.setPixelSize(_px(7))
        p.setFont(f)
        fm = QFontMetricsF(f)
        p.setPen(ink("ghost"))
        where = SIDE_SHORT[self.item.mount_side]
        main = f"{where}: {self.item.label} ({self.rack.depth_of(self.item)} mm)"
        hint = ("Schienen – hier blockiert" if self.blocked else f"frei: {self.free} mm")
        tr = r.adjusted(8, 1, -8, -1)
        if tr.height() >= 2 * fm.height():
            p.drawText(QRectF(tr.left(), tr.center().y() - fm.height(), tr.width(), fm.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(main, Qt.ElideRight,
                                                                     tr.width()))
            p.setPen(QColor(UI_ACCENT) if self.blocked else ink("ghost"))
            p.drawText(QRectF(tr.left(), tr.center().y(), tr.width(), fm.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, hint)
        else:
            hw = fm.horizontalAdvance(hint) + 4
            p.setPen(QColor(UI_ACCENT) if self.blocked else ink("ghost"))
            p.drawText(tr, Qt.AlignRight | Qt.AlignVCenter, hint)
            p.setPen(ink("ghost"))
            p.drawText(QRectF(tr.left(), tr.top(), tr.width() - hw - 6, tr.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(main, Qt.ElideRight, tr.width() - hw - 6))


class DepthProfileItem(QGraphicsItem):
    """Seitenansicht: belegte Tiefe je HE, immer von der Seite gesehen – vorne links,
    hinten rechts (unabhängig von der angezeigten Seite). Geräte der angezeigten Seite
    sind kräftig, die der Gegenseite blass schraffiert. Fachböden erscheinen als Boden mit
    den Geräten darauf, Einbauschienen als Linie über die ganze Tiefe, Konflikte rot."""

    def __init__(self, rack: Rack, side: str, conflict_uids: set[str]):
        super().__init__()
        self.rack = rack
        self.side = side
        self.conflicts = conflict_uids
        self.geo = RackGeometry(rack)
        self.x0 = RACK_W + PROFILE_GAP
        self.setZValue(-5)
        self.setToolTip(
            f"Seitenansicht: Einbautiefe {rack.depth_mm} mm, links vorne, rechts hinten.\n"
            "Rote Bereiche: Tiefe reicht nicht oder Einbauschienen blockieren.")

    def boundingRect(self) -> QRectF:
        return QRectF(self.x0 - 4, 0, PROFILE_W + 8, self.geo.total_height())

    def _box(self, p: QPainter, it: Item, rect: QRectF, viewed: bool, bad: bool):
        base = QColor(CATEGORY_COLORS.get(it.category, "#888888"))
        c = QColor(base)
        c.setAlpha(230 if viewed else 130)
        p.setBrush(c)
        p.setPen(QPen(QColor(CONFLICT_RED) if bad else base.darker(150), 2 if bad else 0.8))
        p.drawRect(rect)
        if not viewed:
            p.setBrush(QBrush(QColor(255, 255, 255, 60), Qt.BDiagPattern))
            p.setPen(Qt.NoPen)
            p.drawRect(rect)

    def paint(self, p: QPainter, option, widget=None):
        g = self.geo
        rack = self.rack
        x0 = self.x0
        h = rack.height_u * U_PX
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(p.font())
        f.setPixelSize(_px(7.5))
        f.setBold(True)
        p.setFont(f)
        p.setPen(ink("title"))
        p.drawText(QRectF(x0 - 20, 0, PROFILE_W + 40, 26), Qt.AlignHCenter | Qt.AlignBottom,
                   "Seitenansicht (Tiefe)")
        f.setBold(False)
        f.setPixelSize(_px(7))
        p.setFont(f)
        p.setPen(ink("subtitle"))
        p.drawText(QRectF(x0, 30, PROFILE_W, 16), Qt.AlignLeft | Qt.AlignVCenter, "vorne")
        p.drawText(QRectF(x0, 30, PROFILE_W, 16), Qt.AlignRight | Qt.AlignVCenter, "hinten")
        p.drawText(QRectF(x0, 30, PROFILE_W, 16), Qt.AlignHCenter | Qt.AlignVCenter,
                   f"{rack.depth_mm} mm")
        area = QRectF(x0, g.top, PROFILE_W, h)
        p.setPen(QPen(ink("frame_edge"), 1))
        p.setBrush(ink("profile_bg"))
        p.drawRect(area)
        p.setPen(QPen(ink("grid"), 0.6))
        for i in range(1, rack.height_u):
            y = g.top + i * U_PX
            p.drawLine(QPointF(x0, y), QPointF(x0 + PROFILE_W, y))
        scale = PROFILE_W / max(1, rack.depth_mm)

        def hrect(side: str, depth: int, top: float, height: float) -> QRectF:
            w = min(PROFILE_W, depth * scale)
            x = x0 if side == FRONT else x0 + PROFILE_W - w
            return QRectF(x, top, w, height)

        rails = []
        for it in rack.top_level():
            span = rack.span(it)
            y = g.y_for(it.position, span)
            viewed = it.mount_side == self.side
            bad = it.uid in self.conflicts
            side = it.mount_side
            if it.is_shelf:
                bottom = y + span * U_PX
                plate = hrect(side, max(it.depth_mm, 1), bottom - PLATE_H, PLATE_H - 1)
                pc = QColor(CATEGORY_COLORS[it.category])
                pc.setAlpha(255 if viewed else 150)
                p.setBrush(pc)
                p.setPen(QPen(QColor(CONFLICT_RED) if bad else pc.darker(160), 1.5 if bad else 0.8))
                p.drawRect(plate)
                for d in rack.on_shelf(it.uid):
                    dh = device_height_px(d)
                    r = hrect(side, d.depth_mm or 1, bottom - PLATE_H - dh, dh)
                    self._box(p, d, r, viewed, bad)
            else:
                d = it.depth_mm
                rect = hrect(side, d, y + 1.5, span * U_PX - 3)
                if d > 0:
                    self._box(p, it, rect, viewed, bad)
                else:
                    # Tiefe unbekannt: nur Markierung an der Montageseite
                    base = QColor(CATEGORY_COLORS.get(it.category, "#888888"))
                    p.setPen(QPen(base, 3))
                    xm = x0 + 1.5 if side == FRONT else x0 + PROFILE_W - 1.5
                    p.drawLine(QPointF(xm, rect.top()), QPointF(xm, rect.bottom()))
            if rack.depth_of(it) > rack.depth_mm:
                p.setPen(QPen(QColor(CONFLICT_RED), 3))
                xe = x0 + PROFILE_W if side == FRONT else x0
                p.drawLine(QPointF(xe, y + 1.5), QPointF(xe, y + span * U_PX - 1.5))
            if it.rails:
                rails.append((y, span, QColor(CATEGORY_COLORS.get(it.category, "#888")), bad))
        for y, span, base, bad in rails:
            p.setPen(QPen(QColor(CONFLICT_RED) if bad else base.lighter(130), 1.6, Qt.DashLine))
            for yy in (y + 3, y + span * U_PX - 3):
                p.drawLine(QPointF(x0 + 2, yy), QPointF(x0 + PROFILE_W - 2, yy))
        for c in rack.conflicts():
            if c.kind == "too_deep":
                continue
            y = g.y_for(c.pos, c.span)
            p.setBrush(QBrush(QColor(CONFLICT_RED), Qt.DiagCrossPattern))
            p.setPen(QPen(QColor(CONFLICT_RED), 1.5))
            p.drawRect(QRectF(x0 + 1, y + 1, PROFILE_W - 2, c.span * U_PX - 2))


def build_scene(scene: QGraphicsScene, rack: Rack, selected_uid: str = "", side: str = FRONT,
                show_other: bool = True, profile: bool = True, side_label: bool = True,
                footer: str = ""):
    """Zeichnet den Schrank von der angegebenen Seite.

    show_other: Geräte der Gegenseite andeuten; profile: Seitenansicht mit Tiefe.
    Für Exporte beides aus: dann nur Schrank, Geräte und Beschriftung."""
    scene.clear()
    geo = RackGeometry(rack)
    scene.addItem(RackFrameItem(rack, side, side_label, footer))
    bad = rack.conflict_uids() if show_other or profile else set()
    if show_other:
        for it in rack.top_level(other_side(side)):
            span = rack.span(it)
            rect = QRectF(geo.left, geo.y_for(it.position, span), INNER_W, span * U_PX)
            scene.addItem(GhostItem(rack, it, rect, side))
    for it in rack.top_level(side):
        span = rack.span(it)
        top = geo.y_for(it.position, span)
        conflict = it.uid in bad
        if it.is_shelf:
            # Fachboden selbst: unterster Teil
            shelf_rect = QRectF(geo.left, top + (span - it.height_u) * U_PX, INNER_W,
                                it.height_u * U_PX)
            scene.addItem(ElementItem(rack, it, shelf_rect, it.uid == selected_uid, conflict))
            for d in rack.on_shelf(it.uid):
                drect = shelf_device_rect(geo, shelf_rect, d, max(0, d.offset_mm))
                scene.addItem(ElementItem(rack, d, drect, d.uid == selected_uid, conflict))
        else:
            rect = QRectF(geo.left, top + 1, INNER_W, span * U_PX - 2)
            scene.addItem(ElementItem(rack, it, rect, it.uid == selected_uid, conflict))
    width = RACK_W
    if profile:
        scene.addItem(DepthProfileItem(rack, side, bad))
        width = RACK_W + PROFILE_GAP + PROFILE_W
    scene.setSceneRect(QRectF(-20, -10, width + 40, geo.total_height() + 20))


class RackView(QGraphicsView):
    selectedChanged = Signal(str)
    moveRequested = Signal(str, float)   # uid (oberste Ebene), neue Position
    shelfMoveRequested = Signal(str, str, int)   # Geräte-uid, Fachboden-uid, Abstand mm
    deleteRequested = Signal()
    sideSwitchRequested = Signal(str)    # uid eines Geräts der Gegenseite

    def __init__(self, rack: Rack):
        super().__init__()
        self.rack = rack
        self.selected_uid = ""
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setBackgroundBrush(QColor(UI_SUNKEN))
        self.setFrameShape(QFrame.NoFrame)
        self.setDragMode(QGraphicsView.NoDrag)
        self._drag_uid = ""
        self._drag_offset_u = 0.0
        self.fine = False            # Feinraster ⅓ HE (Lochraster)
        self._drag_dev = ""          # Gerät auf einem Fachboden, das verschoben wird
        self._drag_grab_x = 0.0      # Abstand Mauszeiger – linke Gerätekante
        self._ghost = None
        self._zoom = 1.0
        self.side = FRONT            # angezeigte Seite
        self.show_other = True       # Gegenseite andeuten
        self.show_profile = True     # Seitenansicht (Tiefe)
        self.read_only = False       # früherer Stand aus der Historie: nur ansehen

    def profile_scene_rect(self) -> QRectF | None:
        """Bereich der Seitenansicht in Szenenkoordinaten (für das Tutorial)."""
        if not self.show_profile:
            return None
        geo = RackGeometry(self.rack)
        return QRectF(RACK_W + PROFILE_GAP - 6, 0, PROFILE_W + 12, geo.total_height())

    def refresh(self):
        self._ghost = None
        build_scene(self.scene(), self.rack, self.selected_uid, self.side, self.show_other,
                    self.show_profile)

    def fit(self):
        self.resetTransform()
        r = self.scene().sceneRect()
        if r.height() <= 0:
            return
        s = min(self.viewport().height() / r.height(), self.viewport().width() / r.width())
        s = max(0.35, min(s, 1.6))
        self._zoom = s
        self.scale(s, s)

    def zoom(self, factor: float):
        nz = max(0.25, min(self._zoom * factor, 4.0))
        self.scale(nz / self._zoom, nz / self._zoom)
        self._zoom = nz

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.zoom(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
        else:
            super().wheelEvent(e)

    def _element_at(self, pos) -> ElementItem | None:
        for gi in self.items(pos):
            if isinstance(gi, ElementItem):
                return gi
        return None

    def _top_level_of(self, item: Item) -> Item:
        return self.rack.get(item.shelf_id) if item.shelf_id else item

    def mousePressEvent(self, e):
        if self.read_only:
            return
        if e.button() == Qt.LeftButton:
            el = self._element_at(e.position().toPoint())
            uid = el.item.uid if el else ""
            if uid != self.selected_uid:
                self.selected_uid = uid
                self.selectedChanged.emit(uid)
                self.refresh()
            if el and el.item.shelf_id:
                # Nicht rackfähiges Gerät: frei auf (anderen) Fachböden verschieben
                self._drag_dev = el.item.uid
                self._drag_grab_x = self.mapToScene(e.position().toPoint()).x() - el.rect.left()
                self.viewport().setCursor(Qt.ClosedHandCursor)
            elif el:
                top = self._top_level_of(el.item)
                geo = RackGeometry(self.rack)
                u = geo.unit_at(self.mapToScene(e.position().toPoint()).y())
                self._drag_uid = top.uid
                self._drag_offset_u = u - top.position
                self.viewport().setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(e)

    def _show_ghost(self, rect: QRectF, ok: bool, data):
        if self._ghost is None:
            self._ghost = self.scene().addRect(rect)
            self._ghost.setZValue(10)
        self._ghost.setRect(rect)
        col = QColor(46, 204, 113, 90) if ok else QColor(231, 76, 60, 90)
        self._ghost.setBrush(col)
        self._ghost.setPen(QPen(col.darker(150), 2, Qt.DashLine))
        self._ghost.setData(0, data if ok else None)

    def _shelf_target(self, pt: QPointF):
        """Fachboden unter dem Mauszeiger und neuer Abstand in mm für das gezogene Gerät."""
        dev = self.rack.get(self._drag_dev)
        geo = RackGeometry(self.rack)
        best = None
        for s in (i for i in self.rack.top_level(self.side) if i.is_shelf):
            srect = shelf_rect_for(geo, self.rack, s)
            reach = max(self.rack.span(s) - s.height_u, dev.height_u) * U_PX
            if srect.top() - reach <= pt.y() <= srect.bottom():
                best = (s, srect)
                break
        if best is None:
            return None
        s, srect = best
        x_mm = (pt.x() - self._drag_grab_x - geo.left - 4) / SHELF_SCALE
        offset = int(round(x_mm / 5) * 5)
        offset = max(0, min(offset, SHELF_WIDTH_MM - dev.width_mm))
        return s, srect, offset

    def _move_shelf_device(self, pt: QPointF):
        dev = self.rack.get(self._drag_dev)
        target = self._shelf_target(pt)
        geo = RackGeometry(self.rack)
        if target is None:
            h = device_height_px(dev)
            w = max(16.0, dev.width_mm * SHELF_SCALE)
            rect = QRectF(pt.x() - self._drag_grab_x, pt.y() - h / 2, w, h)
            self._show_ghost(rect, False, None)
            return
        s, srect, offset = target
        ok = self.rack.can_place_on_shelf(dev, s, offset)
        rect = shelf_device_rect(geo, srect, dev, offset)
        self._show_ghost(rect, ok, f"{s.uid}:{offset}")

    def mouseMoveEvent(self, e):
        if self._drag_dev and e.buttons() & Qt.LeftButton:
            self._move_shelf_device(self.mapToScene(e.position().toPoint()))
        elif self._drag_uid and e.buttons() & Qt.LeftButton:
            top = self.rack.get(self._drag_uid)
            geo = RackGeometry(self.rack)
            span = self.rack.span(top)
            u = geo.unit_at(self.mapToScene(e.position().toPoint()).y())
            raw = u - self._drag_offset_u
            raw = snap_third(raw) if self.fine else round(raw)
            new_pos = max(1, min(raw, self.rack.height_u - span + 1))
            ok = self.rack.is_free(new_pos, span, ignore=top.uid, side=top.mount_side)
            rect = QRectF(geo.left, geo.y_for(new_pos, span), INNER_W, span * U_PX)
            self._show_ghost(rect, ok, new_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag_dev and e.button() == Qt.LeftButton:
            uid, ghost = self._drag_dev, self._ghost
            self._drag_dev = ""
            self.viewport().unsetCursor()
            if ghost is not None:
                data = ghost.data(0)
                self.scene().removeItem(ghost)
                self._ghost = None
                if data:
                    shelf_uid, offset = data.split(":")
                    self.shelfMoveRequested.emit(uid, shelf_uid, int(offset))
        elif self._drag_uid and e.button() == Qt.LeftButton:
            uid, ghost = self._drag_uid, self._ghost
            self._drag_uid = ""
            self.viewport().unsetCursor()
            if ghost is not None:
                new_pos = ghost.data(0) or 0
                self.scene().removeItem(ghost)
                self._ghost = None
                if new_pos:
                    self.moveRequested.emit(uid, float(new_pos))
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.read_only:
            return
        for gi in self.items(e.position().toPoint()):
            if isinstance(gi, GhostItem):
                self.sideSwitchRequested.emit(gi.item.uid)
                return
            if isinstance(gi, ElementItem):
                break
        super().mouseDoubleClickEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Delete and self.selected_uid and not self.read_only:
            self.deleteRequested.emit()
            return
        super().keyPressEvent(e)

