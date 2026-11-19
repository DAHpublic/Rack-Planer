"""3D-Ansicht des Schranks: frei drehbar und zoombar, gezeichnet mit QPainter.

Der Schrank besteht nur aus achsparallelen Quadern (Rahmen, Profile, Geräte, Fachböden).
Diese werden perspektivisch projiziert und von hinten nach vorne gezeichnet
(Maleralgorithmus mit Trennebenen). Dafür braucht es weder OpenGL noch eine Grafikkarte –
die Ansicht läuft überall, wo die 2D-Ansicht läuft, und lässt sich direkt als PNG oder SVG
exportieren (gleicher Zeichencode).

Koordinaten in mm: x nach rechts (von vorne gesehen), y nach oben, z nach vorne.
Die vordere Montageebene liegt bei z = +Tiefe/2, die hintere bei z = −Tiefe/2.
"""

from __future__ import annotations

import copy
import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from planer2d.theme import CONFLICT_RED, UI_ACCENT, UI_MUTED, UI_TEXT, text_color
from rackcore import (
    CATEGORY_COLORS,
    EPS,
    FRONT,
    REAR,
    SHELF_WIDTH_MM,
    U_MM,
    Item,
    Rack,
    fmt_date,
    fmt_u,
    snap_third,
)

# Maße des Schranks (mm)
EAR_HALF = 241.3          # halbe Breite einer 19"-Frontplatte (482,6 mm)
BODY_HALF = 222.0         # halbe Gehäusebreite eines 19"-Geräts
INNER_HALF = SHELF_WIDTH_MM / 2
PROFILE_IN, PROFILE_OUT = 224.0, 262.0    # 19"-Profile (Abstand von der Mitte)
PROFILE_D = 20.0
OUTER_HALF = 300.0        # Außenbreite 600 mm
POST = 30.0               # Eckpfosten
CAB_EXTRA = 70.0          # Rahmen vor/hinter den Montageebenen
TOP_H = 40.0
BASE_H = 40.0
PLINTH_H = 60.0
EAR_D = 4.0
PLATE_H = 6.0             # Blechstärke eines Fachbodens (Darstellung)
UNKNOWN_DEPTH = 40.0      # Geräte ohne Tiefenangabe

FRAME = QColor("#3b3e42")
FRAME_DARK = QColor("#2a2c2f")
PROFILE = QColor("#a9aeb2")
RAIL = QColor("#b9bec2")
PANEL = QColor(150, 160, 170, 46)
FLOOR_LINE = QColor(255, 255, 255, 18)
GHOST_OK = QColor(46, 204, 113, 120)
GHOST_BAD = QColor(231, 76, 60, 120)

# Flächen eines Quaders: (Achse, Richtung)
AA = True
FACES = [(0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1)]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def face_corners(lo, hi, axis: int, sign: int):
    """Ecken einer Fläche in der Reihenfolge oben links, oben rechts, unten rechts,
    unten links – so, wie man die Fläche von außen sieht."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    if axis == 2 and sign > 0:      # vorne
        return [(x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1)]
    if axis == 2:                   # hinten (von hinten gesehen)
        return [(x1, y1, z0), (x0, y1, z0), (x0, y0, z0), (x1, y0, z0)]
    if axis == 0 and sign > 0:      # rechts
        return [(x1, y1, z1), (x1, y1, z0), (x1, y0, z0), (x1, y0, z1)]
    if axis == 0:                   # links
        return [(x0, y1, z0), (x0, y1, z1), (x0, y0, z1), (x0, y0, z0)]
    if axis == 1 and sign > 0:      # oben
        return [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]
    return [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)]   # unten


def face_size(lo, hi, axis: int) -> tuple[float, float]:
    """Breite und Höhe einer Fläche in mm (in der Reihenfolge von face_corners)."""
    dx, dy, dz = hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]
    if axis == 2:
        return dx, dy
    if axis == 0:
        return dz, dy
    return dx, dz


@dataclass
class Box:
    lo: tuple
    hi: tuple
    color: QColor
    uid: str = ""                 # anklickbares Element (Gerät oder Fachboden)
    outline: QColor | None = None
    outline_w: float = 0.8
    # Beschriftung: Fläche (Achse, Richtung) → Funktion(painter, Breite, Höhe)
    decor: dict = field(default_factory=dict)
    shade: bool = True
    # beim Zeichnen ermittelt
    polys: list = field(default_factory=list)
    rect: QRectF | None = None
    hull: QPolygonF | None = None
    dist: float = 0.0

    @property
    def center(self):
        return tuple((a + b) / 2 for a, b in zip(self.lo, self.hi))


class Camera:
    def __init__(self):
        self.target = (0.0, 0.0, 0.0)
        self.yaw = math.radians(-32)      # 0 = genau von vorne
        self.pitch = math.radians(16)
        self.dist = 3000.0
        self.fov = math.radians(35)

    def copy(self) -> Camera:
        c = Camera()
        c.target, c.yaw, c.pitch, c.dist, c.fov = self.target, self.yaw, self.pitch, \
            self.dist, self.fov
        return c

    @property
    def pos(self):
        cp = math.cos(self.pitch)
        t = self.target
        return (t[0] + self.dist * math.sin(self.yaw) * cp,
                t[1] + self.dist * math.sin(self.pitch),
                t[2] + self.dist * math.cos(self.yaw) * cp)

    def basis(self):
        f = _norm(_sub(self.target, self.pos))
        r = _norm(_cross(f, (0.0, 1.0, 0.0)))
        if abs(_dot(r, r)) < 1e-9:
            r = (1.0, 0.0, 0.0)
        u = _cross(r, f)
        return f, r, u


class Projector:
    NEAR = 20.0

    def __init__(self, cam: Camera, w: float, h: float, ox: float = 0, oy: float = 0):
        self.cam = cam
        self.eye = cam.pos
        self.f, self.r, self.u = cam.basis()
        self.cx, self.cy = ox + w / 2, oy + h / 2
        self.focal = 0.5 * h / math.tan(cam.fov / 2)

    def view(self, p):
        d = _sub(p, self.eye)
        return (_dot(d, self.r), _dot(d, self.u), _dot(d, self.f))

    def to_screen(self, v) -> QPointF:
        return QPointF(self.cx + self.focal * v[0] / v[2], self.cy - self.focal * v[1] / v[2])

    def point(self, p) -> QPointF | None:
        v = self.view(p)
        return None if v[2] < self.NEAR else self.to_screen(v)

    def polygon(self, pts) -> QPolygonF | None:
        """Polygon projizieren; an der Nahebene abschneiden (Sutherland-Hodgman)."""
        vs = [self.view(p) for p in pts]
        if all(v[2] >= self.NEAR for v in vs):
            return QPolygonF([self.to_screen(v) for v in vs])
        out = []
        n = len(vs)
        for i in range(n):
            a, b = vs[i], vs[(i + 1) % n]
            ina, inb = a[2] >= self.NEAR, b[2] >= self.NEAR
            if ina:
                out.append(a)
            if ina != inb:
                t = (self.NEAR - a[2]) / (b[2] - a[2])
                out.append(tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
        if len(out) < 3:
            return None
        return QPolygonF([self.to_screen(v) for v in out])

    def ray(self, pt: QPointF):
        """Blickstrahl (Ursprung, Richtung) durch einen Bildschirmpunkt."""
        x = (pt.x() - self.cx) / self.focal
        y = -(pt.y() - self.cy) / self.focal
        d = tuple(self.f[k] + x * self.r[k] + y * self.u[k] for k in range(3))
        return self.eye, _norm(d)


# ---------------------------------------------------------------------------
# Szene aus dem Schrank aufbauen
# ---------------------------------------------------------------------------

def _shade(c: QColor, f: float) -> QColor:
    out = QColor(min(255, int(c.red() * f)), min(255, int(c.green() * f)),
                 min(255, int(c.blue() * f)))
    out.setAlpha(c.alpha())
    return out


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    out = QColor(int(a.red() * (1 - t) + b.red() * t), int(a.green() * (1 - t) + b.green() * t),
                 int(a.blue() * (1 - t) + b.blue() * t))
    out.setAlpha(a.alpha())
    return out


def _zrange(side: str, depth_mm: float, from_face: float, rack: Rack) -> tuple[float, float]:
    """z-Bereich eines Körpers, der an der Montageebene seiner Seite beginnt."""
    half = rack.depth_mm / 2
    if side == FRONT:
        z1 = half - from_face
        return z1 - depth_mm, z1
    z0 = -half + from_face
    return z0, z0 + depth_mm


def _label_painter(lines: list[str], fg: QColor, big: float) -> Callable:
    """Zeichnet Name und IP-Adressen auf eine Frontplatte (lokale Koordinaten in mm).
    Breite Platten: Name links, IPs rechts; schmale Geräte: alles untereinander."""
    name, ips = (lines[0] if lines else ""), lines[1:]

    def font(size: float, bold: bool) -> QFont:
        f = QFont()
        f.setPixelSize(max(1, int(size)))
        f.setBold(bold)
        return f

    def paint(p: QPainter, w: float, h: float):
        p.setPen(fg)
        size = max(6.0, min(big, h * 0.42))
        if w < 320:                       # schmal (z. B. Gerät auf einem Fachboden)
            rows = [(name, True)] if name else []
            rows += [(ip, False) for ip in ips]
            size = max(5.0, min(size, w / 9, h / (len(rows) * 1.25 + 0.4)))
            n = max(1, min(len(rows), int(h / (size * 1.25))))
            top = (h - n * size * 1.25) / 2
            for i, (txt, bold) in enumerate(rows[:n]):
                f = font(size if bold else size * 0.85, bold)
                p.setFont(f)
                r = QRectF(8, top + i * size * 1.25, w - 16, size * 1.25)
                p.drawText(r, Qt.AlignHCenter | Qt.AlignVCenter,
                           p.fontMetrics().elidedText(txt, Qt.ElideRight, int(r.width())))
            return
        x0 = 30.0
        name_w = w - 2 * x0
        if ips:
            ips_size = max(5.0, min(size * 0.8, h / (len(ips) + 0.6)))
            p.setFont(font(ips_size, False))
            ipw = min(w * 0.42, max(p.fontMetrics().horizontalAdvance(ip) for ip in ips) + 4)
            rows = min(len(ips), max(1, int(h / (ips_size * 1.15))))
            top = (h - rows * ips_size * 1.15) / 2
            for i, ip in enumerate(ips[:rows]):
                p.drawText(QRectF(w - ipw - 28, top + i * ips_size * 1.15, ipw, ips_size * 1.2),
                           Qt.AlignRight | Qt.AlignVCenter, ip)
            name_w = w - ipw - x0 - 44
        p.setFont(font(size, True))
        p.drawText(QRectF(x0, 0, name_w, h), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(name, Qt.ElideRight, int(name_w)))
    return paint


HOLE_X = 232.5            # Lochmitte: 465 mm Lochabstand (EIA-310)
HOLE_SIZE = 9.5           # quadratische Käfigmutter-Löcher
HOLE_OFFSETS = (6.35, 6.35 + 15.875, 6.35 + 2 * 15.875)   # drei Löcher je HE (⅓-Raster)


def _profile_painter(rack: Rack, outer_left: bool, numbers: bool) -> Callable:
    """Lochraster eines 19"-Profils: drei quadratische Löcher je HE, Trennlinie zwischen
    den HE, jede HE im Wechsel leicht abgesetzt, dazu die HE-Nummer am äußeren Rand.
    outer_left: Die Außenkante des Profils liegt (von dieser Seite gesehen) links."""
    width = PROFILE_OUT - PROFILE_IN
    hole_u = (PROFILE_OUT - HOLE_X) if outer_left else (HOLE_X - PROFILE_IN)
    num_w = PROFILE_OUT - EAR_HALF           # nicht von Frontplatten verdeckter Streifen
    num_x = 0.0 if outer_left else width - num_w

    def paint(p: QPainter, w: float, h: float):
        p.setPen(Qt.NoPen)
        alt = QColor(0, 0, 0, 28)
        for u in range(1, rack.height_u + 1):
            if u % 2 == 0:
                p.fillRect(QRectF(0, h - u * U_MM, w, U_MM), alt)
        hole = QColor("#16171a")
        rim = QColor(255, 255, 255, 60)
        hs = HOLE_SIZE
        for u in range(1, rack.height_u + 1):
            base = h - (u - 1) * U_MM
            for off in HOLE_OFFSETS:
                cy = base - off
                r = QRectF(hole_u - hs / 2, cy - hs / 2, hs, hs)
                p.setBrush(rim)
                p.drawRect(r.translated(0.8, 0.8))
                p.setBrush(hole)
                p.drawRect(r)
        p.setPen(QPen(QColor("#2b2d30"), 1.6))
        for u in range(0, rack.height_u + 1):
            y = h - u * U_MM
            p.drawLine(QPointF(0, y), QPointF(w, y))
        if numbers:
            f = QFont()
            f.setPixelSize(14)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#141517"))
            for u in range(1, rack.height_u + 1):
                p.drawText(QRectF(num_x, h - u * U_MM, num_w, U_MM), Qt.AlignCenter, str(u))
    return paint


def build_boxes(rack: Rack, selected_uid: str = "", conflict_uids: set | None = None,
                side_panels: bool = True, labels: bool = True) -> list[Box]:
    conflict_uids = conflict_uids or set()
    boxes: list[Box] = []
    H = rack.height_u * U_MM
    D = float(max(rack.depth_mm, 200))
    half = D / 2
    zo = half + CAB_EXTRA
    red = QColor(CONFLICT_RED)
    accent = QColor(UI_ACCENT)

    # --- Rahmen --------------------------------------------------------------
    boxes.append(Box((-OUTER_HALF, -BASE_H, -zo), (OUTER_HALF, 0, zo), FRAME))
    boxes.append(Box((-OUTER_HALF + 20, -BASE_H - PLINTH_H, -zo + 20),
                     (OUTER_HALF - 20, -BASE_H, zo - 20), FRAME_DARK))
    boxes.append(Box((-OUTER_HALF, H, -zo), (OUTER_HALF, H + TOP_H, zo), FRAME))
    for sx in (-1, 1):
        for sz in (-1, 1):
            x0 = OUTER_HALF - POST if sx > 0 else -OUTER_HALF
            z0 = zo - POST if sz > 0 else -zo
            boxes.append(Box((x0, 0, z0), (x0 + POST, H, z0 + POST), FRAME))
        if side_panels:
            x0 = OUTER_HALF - 3 if sx > 0 else -OUTER_HALF
            boxes.append(Box((x0, 0, -zo + POST), (x0 + 3, H, zo - POST), PANEL, shade=False,
                             outline=QColor(255, 255, 255, 25)))
    # 19"-Profile vorne und hinten, je links und rechts
    for side, zc in ((FRONT, half), (REAR, -half)):
        z0, z1 = (zc - PROFILE_D, zc) if side == FRONT else (zc, zc + PROFILE_D)
        for sx in (-1, 1):
            x0, x1 = (PROFILE_IN, PROFILE_OUT) if sx > 0 else (-PROFILE_OUT, -PROFILE_IN)
            b = Box((x0, 0, z0), (x1, H, z1), PROFILE, outline=QColor("#5b5f63"))
            # Lochraster und HE-Nummern auf beiden Profilen der jeweiligen Seite
            face = (2, 1) if side == FRONT else (2, -1)
            outer_left = (sx < 0) == (side == FRONT)
            b.decor[face] = _profile_painter(rack, outer_left, labels)
            boxes.append(b)

    # --- Geräte ---------------------------------------------------------------
    for it in rack.top_level():
        side = it.mount_side
        y0 = (it.position - 1) * U_MM
        span = rack.span(it)
        bad = it.uid in conflict_uids
        sel = it.uid == selected_uid
        outward = (2, 1) if side == FRONT else (2, -1)
        if it.is_shelf:
            depth = float(it.depth_mm or D)
            col = QColor(CATEGORY_COLORS.get(it.category, "#95a5a6"))
            if bad:
                col = _mix(col, red, 0.55)
            z0, z1 = _zrange(side, depth, 0, rack)
            boxes.append(Box((-BODY_HALF, y0, z0), (BODY_HALF, y0 + PLATE_H, z1), col,
                             uid=it.uid, outline=accent if sel else (red if bad else None),
                             outline_w=2.2 if sel or bad else 0.8))
            ez0, ez1 = _zrange(side, EAR_D, -EAR_D, rack)
            for sx in (-1, 1):
                x0, x1 = (BODY_HALF, EAR_HALF) if sx > 0 else (-EAR_HALF, -BODY_HALF)
                boxes.append(Box((x0, y0, ez0), (x1, y0 + U_MM * it.height_u - 1, ez1), col,
                                 uid=it.uid, outline=accent if sel else None,
                                 outline_w=2.2 if sel else 0.8))
            if it.rails:
                boxes.extend(_rails(rack, it, y0, bad))
            for d in rack.on_shelf(it.uid):
                boxes.append(_shelf_device(rack, it, d, y0, selected_uid, bad, labels))
            continue
        col = QColor(CATEGORY_COLORS.get(it.category, "#2e86c1"))
        if bad:
            col = _mix(col, red, 0.55)
        depth = float(it.depth_mm) if it.depth_mm > 0 else UNKNOWN_DEPTH
        top = y0 + span * U_MM - 0.8
        bottom = y0 + 0.8
        outline = accent if sel else (red if bad else QColor(0, 0, 0, 90))
        ow = 2.4 if sel or bad else 0.8
        lines = []
        if labels:
            if it.show_name:
                lines.append(it.label)
            else:
                lines.append("")
            lines.extend(it.all_ips())
        fg = text_color(col)
        if it.rackmount:
            z0, z1 = _zrange(side, max(depth - EAR_D, 1.0), 0, rack)
            boxes.append(Box((-BODY_HALF, bottom, z0), (BODY_HALF, top, z1),
                             _shade(col, 0.82), uid=it.uid, outline=outline, outline_w=ow))
            ez0, ez1 = _zrange(side, EAR_D, -EAR_D, rack)
            front = Box((-EAR_HALF, bottom, ez0), (EAR_HALF, top, ez1), col, uid=it.uid,
                        outline=outline, outline_w=ow)
            if labels and any(lines):
                front.decor[outward] = _label_painter(lines, fg, 22)
            boxes.append(front)
            if it.rails:
                boxes.extend(_rails(rack, it, y0, bad))
        else:
            # nicht rackfähig, ohne Fachboden eingesetzt
            h = it.height_cm * 10 if it.height_cm > 0 else span * U_MM
            w = min(float(it.width_mm or 440), 2 * BODY_HALF) / 2
            z0, z1 = _zrange(side, depth, 0, rack)
            b = Box((-w, bottom, z0), (w, min(top, y0 + h), z1), col, uid=it.uid,
                    outline=outline, outline_w=ow)
            if labels and any(lines):
                b.decor[outward] = _label_painter(lines, fg, 18)
            boxes.append(b)
    return boxes


def _rails(rack: Rack, it: Item, y0: float, bad: bool) -> list[Box]:
    """Einbauschienen: laufen von Profil zu Profil über die ganze Tiefe."""
    half = rack.depth_mm / 2
    col = QColor(CONFLICT_RED) if bad else RAIL
    out = []
    for sx in (-1, 1):
        x0, x1 = (BODY_HALF, PROFILE_IN) if sx > 0 else (-PROFILE_IN, -BODY_HALF)
        out.append(Box((x0, y0 + 4, -half + PROFILE_D), (x1, y0 + 16, half - PROFILE_D), col,
                       uid=it.uid, outline=QColor(0, 0, 0, 80)))
    return out


def _shelf_device(rack: Rack, shelf: Item, d: Item, y0: float, selected_uid: str, bad: bool,
                  labels: bool) -> Box:
    side = shelf.mount_side
    h = rack.load_u(d) * U_MM
    # Fachboden-Innenmaß (450 mm) auf die gezeichnete Bodenplatte abbilden
    k = BODY_HALF / INNER_HALF
    off = max(0, d.offset_mm)
    x0 = -BODY_HALF + off * k
    x1 = min(BODY_HALF, x0 + d.width_mm * k)
    x0, x1 = x0 + 0.5, x1 - 0.5
    if side == REAR:                  # von hinten gesehen ist links = +x
        x0, x1 = -x1, -x0
    depth = float(d.depth_mm) if d.depth_mm > 0 else 150.0
    z0, z1 = _zrange(side, depth, 15, rack)
    col = QColor(CATEGORY_COLORS.get(d.category, "#2e86c1"))
    if bad:
        col = _mix(col, QColor(CONFLICT_RED), 0.45)
    sel = d.uid == selected_uid
    b = Box((x0, y0 + PLATE_H, z0), (x1, y0 + PLATE_H + h, z1), col, uid=d.uid,
            outline=QColor(UI_ACCENT) if sel else QColor(0, 0, 0, 90),
            outline_w=2.4 if sel else 0.8)
    if labels:
        lines = [d.label if d.show_name else "", *d.all_ips()[:2]]
        if any(lines):
            b.decor[(2, 1) if side == FRONT else (2, -1)] = _label_painter(
                lines, text_color(col), 14)
    return b


# ---------------------------------------------------------------------------
# Zeichnen
# ---------------------------------------------------------------------------

def _separates(a: Box, b: Box, eye) -> int:
    """Reihenfolge zweier Quader: -1 = a zuerst (a liegt hinter b), 1 = b zuerst,
    0 = keine Verdeckung möglich oder nicht entscheidbar."""
    for k in range(3):
        if a.hi[k] <= b.lo[k] + EPS:
            if eye[k] >= b.lo[k]:
                return -1
            if eye[k] <= a.hi[k]:
                return 1
            return 0
        if b.hi[k] <= a.lo[k] + EPS:
            if eye[k] >= a.lo[k]:
                return 1
            if eye[k] <= b.hi[k]:
                return -1
            return 0
    return 2      # überschneiden sich


def _hull(points: list[QPointF]) -> QPolygonF:
    """Konvexe Hülle (monotone chain)."""
    pts = sorted({(round(q.x(), 3), round(q.y(), 3)) for q in points})
    if len(pts) < 3:
        return QPolygonF([QPointF(x, y) for x, y in pts])

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return QPolygonF([QPointF(x, y) for x, y in lower[:-1] + upper[:-1]])


def overlaps(a: Box, b: Box) -> bool:
    """Überdecken sich die Umrisse zweier Quader auf dem Bildschirm (mehr als eine Kante)?"""
    if not a.rect.intersects(b.rect):
        return False
    return a.hull.intersects(b.hull)


def sort_boxes(boxes: list[Box], eye) -> list[Box]:
    """Topologische Sortierung: was verdeckt wird, kommt zuerst. Reihenfolgen werden nur
    für Quader festgelegt, die sich auf dem Bildschirm tatsächlich überdecken."""
    n = len(boxes)
    after: list[list[int]] = [[] for _ in range(n)]
    indeg = [0] * n
    for i in range(n):
        for j in range(i + 1, n):
            if not overlaps(boxes[i], boxes[j]):
                continue
            s = _separates(boxes[i], boxes[j], eye)
            if s == 2:
                s = -1 if boxes[i].dist > boxes[j].dist else 1
            if s == -1:
                after[i].append(j)
                indeg[j] += 1
            elif s == 1:
                after[j].append(i)
                indeg[i] += 1
    heap = [(-boxes[i].dist, i) for i in range(n) if indeg[i] == 0]
    heapq.heapify(heap)
    done = [False] * n
    out: list[Box] = []
    while len(out) < n:
        if not heap:     # Zyklus: den entferntesten verbleibenden Quader nehmen
            i = max((k for k in range(n) if not done[k]), key=lambda k: boxes[k].dist)
            indeg[i] = 0
            heap.append((-boxes[i].dist, i))
        _, i = heapq.heappop(heap)
        if done[i]:
            continue
        done[i] = True
        out.append(boxes[i])
        for j in after[i]:
            indeg[j] -= 1
            if indeg[j] == 0 and not done[j]:
                heapq.heappush(heap, (-boxes[j].dist, j))
    return out


def render(p: QPainter, cam: Camera, boxes: list[Box], w: float, h: float,
           floor_y: float = 0.0, ghost: Box | None = None, background: bool = True,
           floor_texts: tuple[str, str] = ("", ""), text_z: float = 700.0,
           fast: bool = False) -> list[Box]:
    """Zeichnet die Szene; liefert die gezeichneten Quader in Zeichenreihenfolge.
    fast: ohne Kantenglättung und Beschriftung (flüssiges Drehen)."""
    proj = Projector(cam, w, h)
    eye = proj.eye
    p.setRenderHint(QPainter.Antialiasing, AA and not fast)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    if background:
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor("#3a3c3f"))
        g.setColorAt(1, QColor("#1c1d1f"))
        p.fillRect(QRectF(0, 0, w, h), g)
    _draw_floor(p, proj, floor_y, () if fast else floor_texts, text_z)

    light = _norm(tuple(-proj.f[k] * 0.7 - proj.r[k] * 0.35 for k in range(3)))
    light = _norm((light[0], light[1] + 0.9, light[2]))
    visible: list[Box] = []
    for b in boxes:
        b.polys = []
        rect = None
        for axis, sign in FACES:
            # Rückseiten weglassen
            if sign > 0 and eye[axis] <= b.hi[axis]:
                continue
            if sign < 0 and eye[axis] >= b.lo[axis]:
                continue
            lo = list(b.lo)
            hi = list(b.hi)
            poly = proj.polygon(face_corners(lo, hi, axis, sign))
            if poly is None:
                continue
            b.polys.append(((axis, sign), poly))
            br = poly.boundingRect()
            rect = br if rect is None else rect.united(br)
        if rect is None:
            continue
        b.rect = rect
        b.hull = _hull([q for _f, poly in b.polys for q in poly])
        c = b.center
        b.dist = math.dist(c, eye)
        visible.append(b)
    ordered = sort_boxes(visible, eye)
    for b in ordered:
        _draw_box(p, proj, b, light, not fast)
    if ghost is not None:
        ghost.polys = []
        for axis, sign in FACES:
            if (sign > 0 and eye[axis] <= ghost.hi[axis]) or \
                    (sign < 0 and eye[axis] >= ghost.lo[axis]):
                continue
            poly = proj.polygon(face_corners(ghost.lo, ghost.hi, axis, sign))
            if poly is not None:
                ghost.polys.append(((axis, sign), poly))
        _draw_box(p, proj, ghost, light)
    return ordered


def _draw_box(p: QPainter, proj: Projector, b: Box, light, decor: bool = True):
    for (axis, sign), poly in b.polys:
        n = [0.0, 0.0, 0.0]
        n[axis] = float(sign)
        col = b.color
        if b.shade:
            f = 0.42 + 0.68 * max(0.0, _dot(n, light))
            col = _shade(col, f)
        p.setBrush(QBrush(col))
        if b.outline is not None:
            pen = QPen(b.outline, b.outline_w)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
        else:
            p.setPen(QPen(_shade(col, 0.7), 0.6))
        p.drawPolygon(poly)
        fn = b.decor.get((axis, sign)) if decor else None
        if fn is not None:
            _draw_decor(p, proj, b, axis, sign, fn)


def _draw_decor(p: QPainter, proj: Projector, b: Box, axis: int, sign: int, fn: Callable):
    corners = face_corners(b.lo, b.hi, axis, sign)
    pts = [proj.point(c) for c in corners]
    if any(pt is None for pt in pts):
        return
    w, h = face_size(b.lo, b.hi, axis)
    dst = QPolygonF(pts)
    if dst.boundingRect().height() < 5:
        return          # zu klein, um lesbar zu sein
    src = QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)])
    t = QTransform.quadToQuad(src, dst)
    if t is None:
        return
    p.save()
    p.setTransform(t, True)
    p.setClipRect(QRectF(0, 0, w, h))
    fn(p, w, h)
    p.restore()


def _draw_floor(p: QPainter, proj: Projector, y: float, texts: tuple[str, str],
                text_z: float = 700.0):
    pen = QPen(FLOOR_LINE, 1)
    p.setPen(pen)
    ext, step = 2400, 200
    for k in range(-ext, ext + 1, step):
        for a, b in (((k, y, -ext), (k, y, ext)), ((-ext, y, k), (ext, y, k))):
            seg = _clip_segment(proj, a, b)
            if seg:
                p.drawLine(*seg)
    front, rear = texts or ("", "")
    for txt, zc, rot in ((front, 1, False), (rear, -1, True)):
        if not txt:
            continue
        z = zc * text_z
        x0, x1 = -500, 500
        if not rot:
            quad = [(x0, y, z), (x1, y, z), (x1, y, z + 160), (x0, y, z + 160)]
        else:
            quad = [(x1, y, z), (x0, y, z), (x0, y, z - 160), (x1, y, z - 160)]
        pts = [proj.point(c) for c in quad]
        if any(pt is None for pt in pts):
            continue
        t = QTransform.quadToQuad(QPolygonF([QPointF(0, 0), QPointF(1000, 0),
                                             QPointF(1000, 160), QPointF(0, 160)]),
                                  QPolygonF(pts))
        if t is None:
            continue
        p.save()
        p.setTransform(t, True)
        f = QFont()
        f.setPixelSize(90)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 14)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 40))
        p.drawText(QRectF(0, 0, 1000, 160), Qt.AlignCenter, txt)
        p.restore()


def _clip_segment(proj: Projector, a, b):
    va, vb = proj.view(a), proj.view(b)
    n = proj.NEAR
    if va[2] < n and vb[2] < n:
        return None
    if va[2] < n or vb[2] < n:
        t = (n - va[2]) / (vb[2] - va[2])
        c = tuple(va[k] + t * (vb[k] - va[k]) for k in range(3))
        if va[2] < n:
            va = c
        else:
            vb = c
    return proj.to_screen(va), proj.to_screen(vb)


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

PRESETS = {
    "front": (0.0, 6.0),
    "rear": (180.0, 6.0),
    "left": (-90.0, 4.0),
    "right": (90.0, 4.0),
    "top": (-20.0, 72.0),
    "iso": (-32.0, 16.0),
}


class RackView3D(QWidget):
    """Frei drehbare 3D-Ansicht. Linke Maustaste auf einem Gerät: verschieben (HE),
    sonst drehen; rechte Maustaste: drehen; mittlere Maustaste oder Umschalt: verschieben
    der Ansicht; Mausrad: zoomen; Doppelklick: auf das Gerät zoomen."""

    selectedChanged = Signal(str)
    moveRequested = Signal(str, float)
    shelfMoveRequested = Signal(str, str, int)   # Geräte-uid, Fachboden-uid, Abstand mm
    deleteRequested = Signal()
    sideChanged = Signal(str)          # Kamera steht jetzt vorne/hinten

    def __init__(self, rack: Rack, parent=None):
        super().__init__(parent)
        self.rack = rack
        self.selected_uid = ""
        self.read_only = False
        self.fine = False
        self.conflict_uids: set[str] = set()
        self.side_panels = True
        self.labels = True
        self.cam = Camera()
        self._boxes: list[Box] = []
        self._drawn: list[Box] = []
        self._dirty = True
        self._press = None              # (pos, button, modifiers, cam-Kopie)
        self._drag = None               # Verschieben eines Geräts
        self._ghost: Box | None = None
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._anim_step)
        self._anim_from = self._anim_to = None
        self._anim_t = 0.0
        self._fast = False              # während Drehen/Zoomen: schneller zeichnen
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(160)
        self._settle.timeout.connect(self._end_fast)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 300)
        self._build_buttons()
        self.fit(animate=False)

    # --- Bedienelemente -------------------------------------------------------------
    def _build_buttons(self):
        bar = QWidget(self)
        bar.setObjectName("view3dbar")
        bar.setStyleSheet(
            "#view3dbar { background: rgba(30,30,30,170); border-radius: 6px; }"
            "#view3dbar QToolButton { color: #ececec; background: transparent; border: none;"
            " padding: 3px 7px; border-radius: 4px; }"
            "#view3dbar QToolButton:hover { background: rgba(255,255,255,30); }"
            f"#view3dbar QToolButton:checked {{ color: {UI_ACCENT}; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(0)
        self.btns = {}
        for key, text, tip in (("front", "Vorne", "Ansicht von vorne"),
                               ("rear", "Hinten", "Ansicht von hinten"),
                               ("left", "Links", "Ansicht von links"),
                               ("right", "Rechts", "Ansicht von rechts"),
                               ("top", "Oben", "Ansicht von schräg oben"),
                               ("iso", "3D", "Schräge 3D-Ansicht"),
                               ("fit", "Anpassen", "Ganzen Schrank zeigen (Strg + 0)")):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            if key == "fit":
                b.clicked.connect(lambda: self.fit())
            else:
                b.clicked.connect(lambda _=False, k=key: self.preset(k))
            lay.addWidget(b)
            self.btns[key] = b
        sep = QWidget()
        sep.setFixedWidth(10)
        lay.addWidget(sep)
        self.btn_panels = QToolButton()
        self.btn_panels.setText("Seitenwände")
        self.btn_panels.setCheckable(True)
        self.btn_panels.setChecked(True)
        self.btn_panels.setToolTip("Seitenwände ein-/ausblenden")
        self.btn_panels.toggled.connect(self._on_panels)
        lay.addWidget(self.btn_panels)
        self.btn_labels = QToolButton()
        self.btn_labels.setText("Beschriftung")
        self.btn_labels.setCheckable(True)
        self.btn_labels.setChecked(True)
        self.btn_labels.setToolTip("Namen, IP-Adressen und HE-Nummern ein-/ausblenden")
        self.btn_labels.toggled.connect(self._on_labels)
        lay.addWidget(self.btn_labels)
        self.bar = bar
        bar.adjustSize()

    def _on_panels(self, on: bool):
        self.side_panels = on
        self.refresh()

    def _on_labels(self, on: bool):
        self.labels = on
        self.refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.bar.adjustSize()
        self.bar.move(8, 8)

    # --- Szene --------------------------------------------------------------------
    def refresh(self):
        self._boxes = build_boxes(self.rack, self.selected_uid, self.conflict_uids,
                                  self.side_panels, self.labels)
        self.update()

    def bounds(self):
        H = self.rack.height_u * U_MM
        zo = max(self.rack.depth_mm, 200) / 2 + CAB_EXTRA
        return (-OUTER_HALF, -BASE_H - PLINTH_H, -zo), (OUTER_HALF, H + TOP_H, zo)

    def _fit_camera(self, cam: Camera, w: float | None = None, h: float | None = None):
        lo, hi = self.bounds()
        cam.target = tuple((a + b) / 2 for a, b in zip(lo, hi))
        r = 0.5 * math.dist(lo, hi)
        w = w or max(1, self.width())
        h = h or max(1, self.height())
        half_v = cam.fov / 2
        half_h = math.atan(math.tan(half_v) * w / h)
        cam.dist = r / math.sin(min(half_v, half_h)) * 0.98

    def fit(self, animate: bool = True):
        target = self.cam.copy()
        self._fit_camera(target)
        self._go(target, animate)

    def preset(self, key: str, animate: bool = True):
        yaw, pitch = PRESETS[key]
        target = self.cam.copy()
        target.yaw, target.pitch = math.radians(yaw), math.radians(pitch)
        self._fit_camera(target)
        self._go(target, animate)

    def show_side(self, side: str):
        """Kamera auf die Vorder- bzw. Rückseite drehen (nur wenn nötig)."""
        if self.facing_side() != side:
            self.preset("front" if side == FRONT else "rear")

    def facing_side(self) -> str:
        return FRONT if math.cos(self.cam.yaw) >= 0 else REAR

    def _go(self, target: Camera, animate: bool):
        # kürzester Weg beim Drehen
        dy = (target.yaw - self.cam.yaw + math.pi) % (2 * math.pi) - math.pi
        target.yaw = self.cam.yaw + dy
        if not animate or not self.isVisible():
            self.cam = target
            self._anim.stop()
            self._camera_changed(False)
            return
        self._anim_from, self._anim_to, self._anim_t = self.cam.copy(), target, 0.0
        self._anim.start()

    def _anim_step(self):
        self._anim_t = min(1.0, self._anim_t + 0.08)
        t = self._anim_t
        e = t * t * (3 - 2 * t)
        a, b = self._anim_from, self._anim_to
        c = Camera()
        c.fov = b.fov
        c.yaw = a.yaw + (b.yaw - a.yaw) * e
        c.pitch = a.pitch + (b.pitch - a.pitch) * e
        c.dist = a.dist + (b.dist - a.dist) * e
        c.target = tuple(a.target[k] + (b.target[k] - a.target[k]) * e for k in range(3))
        self.cam = c
        if t >= 1.0:
            self._anim.stop()
        self._camera_changed()

    def _begin_fast(self):
        self._fast = True
        self._settle.start()

    def _end_fast(self):
        if self._press is not None or self._anim.isActive():
            self._settle.start()
            return
        self._fast = False
        self.update()

    def _camera_changed(self, interactive: bool = True):
        if interactive and self.isVisible():
            self._begin_fast()
        old = getattr(self, "_side", None)
        self._side = self.facing_side()
        if old is not None and old != self._side:
            self.sideChanged.emit(self._side)
        self.update()

    def zoom(self, factor: float):
        self.cam.dist = min(20000.0, max(150.0, self.cam.dist / factor))
        self._camera_changed()

    def focus_item(self, uid: str):
        b = next((b for b in self._boxes if b.uid == uid), None)
        it = self.rack.get(uid)
        if b is None or it is None:
            return
        top = self.rack.top_of(it)
        target = self.cam.copy()
        target.target = b.center
        target.yaw = 0.0 if top.mount_side == FRONT else math.pi
        target.yaw += math.radians(-25 if top.mount_side == FRONT else 25)
        target.pitch = math.radians(14)
        target.dist = 1300.0
        self._go(target, True)

    # --- Zeichnen ---------------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        if not self._boxes:
            self._boxes = build_boxes(self.rack, self.selected_uid, self.conflict_uids,
                                      self.side_panels, self.labels)
        floor = -BASE_H - PLINTH_H
        self._drawn = render(p, self.cam, self._boxes, self.width(), self.height(), floor,
                             self._ghost, floor_texts=("VORNE", "HINTEN"),
                             text_z=self.bounds()[1][2] + 60, fast=self._fast)
        self._paint_overlay(p)
        p.end()

    def banner_top(self) -> int:
        """Oberkante für darübergelegte Hinweis-Banner: unter Werkzeugleiste und Titel."""
        return self.bar.geometry().bottom() + 22 + (54 if self.read_only else 36)

    def _paint_overlay(self, p: QPainter):
        p.resetTransform()
        r = self.rack
        f = QFont()
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(UI_TEXT))
        x = 14
        y = self.bar.geometry().bottom() + 22
        p.drawText(QPointF(x, y), r.name)
        f.setBold(False)
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(QColor(UI_MUTED))
        p.drawText(QPointF(x, y + 18),
                   f"Stand {fmt_date(r.as_of)} · {r.height_u} HE · Tiefe {r.depth_mm} mm · "
                   f"Blick von {'vorne' if self.facing_side() == FRONT else 'hinten'}")
        if self.read_only:
            p.setPen(QColor(UI_ACCENT))
            p.drawText(QPointF(x, y + 36), "Früherer Stand – nur ansehen")
        hint = ("Linke Maustaste: drehen · auf einem Gerät: verschieben · Rechte Maustaste: "
                "drehen · Mittlere Maustaste / Umschalt: Ansicht verschieben · Mausrad: zoomen · "
                "Doppelklick: Gerät heranholen")
        if self.read_only:
            hint = ("Linke/rechte Maustaste: drehen · Mittlere Maustaste / Umschalt: verschieben"
                    " · Mausrad: zoomen")
        p.setPen(QColor(255, 255, 255, 110))
        p.drawText(QRectF(10, self.height() - 24, self.width() - 20, 20),
                   Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                   p.fontMetrics().elidedText(hint, Qt.ElideRight, self.width() - 20))
        if self._drag and self._drag.get("text"):
            p.setPen(QColor(UI_TEXT))
            f.setBold(True)
            p.setFont(f)
            p.drawText(QPointF(self._drag["mouse"].x() + 16, self._drag["mouse"].y() - 10),
                       self._drag["text"])

    def render_image(self, painter: QPainter, w: float, h: float, background: bool = True):
        """Für den Export: aktuelle Kamera, auf die Bildgröße angepasst."""
        cam = self.cam.copy()
        boxes = build_boxes(self.rack, "", self.conflict_uids, self.side_panels, True)
        render(painter, cam, boxes, w, h, -BASE_H - PLINTH_H, background=background)

    # --- Maus ---------------------------------------------------------------------
    def pick(self, pt: QPointF) -> str:
        for b in reversed(self._drawn):
            if not b.uid:
                continue
            for _face, poly in b.polys:
                if poly.containsPoint(pt, Qt.OddEvenFill):
                    return b.uid
        return ""

    def mousePressEvent(self, e):
        self.setFocus()
        self._anim.stop()
        pos = e.position()
        self._press = (pos, e.button(), e.modifiers(), self.cam.copy())
        self._drag = None
        if e.button() == Qt.LeftButton and not (e.modifiers() & Qt.ShiftModifier):
            uid = self.pick(pos)
            if uid and not self.read_only:
                self._drag = self._start_drag(uid, pos)
            self._press_uid = uid
        else:
            self._press_uid = None

    def _top(self, uid: str) -> Item | None:
        it = self.rack.get(uid)
        return self.rack.top_of(it) if it is not None else None

    def _plane_y(self, pos: QPointF, center) -> float | None:
        """Höhe (mm) unter dem Mauszeiger in einer senkrechten Ebene durch center,
        die zur Kamera zeigt."""
        pt = self._plane_point(pos, center)
        return None if pt is None else pt[1]

    def _plane_point(self, pos: QPointF, center):
        """Punkt (x, y, z in mm) unter dem Mauszeiger in einer senkrechten Ebene durch
        center, die zur Kamera zeigt."""
        proj = Projector(self.cam, self.width(), self.height())
        n = (proj.f[0], 0.0, proj.f[2])
        if math.hypot(n[0], n[2]) < 0.15:
            return None
        n = _norm(n)
        o, d = proj.ray(pos)
        den = _dot(d, n)
        if abs(den) < 1e-6:
            return None
        t = _dot(_sub(center, o), n) / den
        if t <= 0:
            return None
        return tuple(o[k] + d[k] * t for k in range(3))

    def _start_drag(self, uid: str, pos: QPointF):
        top = self._top(uid)
        if top is None:
            return None
        b = next((b for b in self._boxes if b.uid == uid), None)
        if b is None:
            return None
        it = self.rack.get(uid)
        if it is not None and it.shelf_id:
            # Gerät auf einem Fachboden: frei auf (andere) Fachböden ziehen, wie in 2D
            pt = self._plane_point(pos, b.center)
            if pt is None:
                return None
            return {"uid": uid, "shelf_mode": True, "grab_x": pt[0] - b.lo[0],
                    "grab_y": pt[1] - b.lo[1], "center": b.center, "active": False,
                    "target": None, "ok": False, "mouse": pos, "text": ""}
        y = self._plane_y(pos, b.center)
        if y is None:
            return None
        return {"uid": uid, "top": top.uid, "grab": y / U_MM - (top.position - 1),
                "center": b.center, "active": False, "pos": top.position, "ok": True,
                "mouse": pos, "text": ""}

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._press is None:
            uid = self.pick(pos)
            self.setCursor(Qt.PointingHandCursor if uid and not self.read_only
                           else Qt.ArrowCursor)
            return
        start, button, mods, cam0 = self._press
        dx, dy = pos.x() - start.x(), pos.y() - start.y()
        if self._drag is not None:
            if not self._drag["active"] and math.hypot(dx, dy) < 4:
                return
            self._drag["active"] = True
            self._update_drag(pos)
            return
        if math.hypot(dx, dy) < 2:
            return
        pan = button == Qt.MiddleButton or (mods & Qt.ShiftModifier)
        if pan:
            proj = Projector(cam0, self.width(), self.height())
            scale = cam0.dist / proj.focal
            t = cam0.target
            self.cam.target = tuple(t[k] - (dx * proj.r[k] - dy * proj.u[k]) * scale
                                    for k in range(3))
        else:
            self.cam.yaw = cam0.yaw - dx * 0.008
            self.cam.pitch = max(math.radians(-80), min(math.radians(85),
                                                        cam0.pitch + dy * 0.008))
        self.setCursor(Qt.ClosedHandCursor)
        self._camera_changed()

    def _shelf_target(self, dev: Item, x_left: float, y_bottom: float):
        """Fachboden, auf dem das gezogene Gerät landen würde, und Abstand von links (mm).
        Bevorzugt Fachböden auf der Seite, auf die die Kamera gerade schaut."""
        dev_h = self.rack.load_u(dev) * U_MM
        facing = self.facing_side()
        best = None
        for s in (i for i in self.rack.top_level() if i.is_shelf):
            plate_top = (s.position - 1) * U_MM + PLATE_H
            dist = abs(y_bottom - plate_top)
            if dist > max(dev_h, U_MM):
                continue
            key = (s.mount_side != facing, dist)
            if best is None or key < best[0]:
                best = (key, s)
        if best is None:
            return None
        s = best[1]
        k = BODY_HALF / INNER_HALF
        if s.mount_side == REAR:          # von hinten gesehen ist links = +x
            off = (-x_left - dev.width_mm * k + BODY_HALF) / k
        else:
            off = (x_left + BODY_HALF) / k
        off = int(round(off / 5) * 5)
        off = max(0, min(off, SHELF_WIDTH_MM - dev.width_mm))
        return s, off

    def _update_shelf_drag(self, pos: QPointF):
        d = self._drag
        dev = self.rack.get(d["uid"])
        pt = self._plane_point(pos, d["center"])
        if dev is None or pt is None:
            return
        x_left, y_bottom = pt[0] - d["grab_x"], pt[1] - d["grab_y"]
        target = self._shelf_target(dev, x_left, y_bottom)
        if target is None:
            d["target"], d["ok"] = None, False
            d["text"] = "Auf einen Fachboden ziehen"
            lo = (x_left, y_bottom, d["center"][2] - 20)
            w = dev.width_mm * BODY_HALF / INNER_HALF
            hi = (x_left + w, y_bottom + self.rack.load_u(dev) * U_MM, d["center"][2] + 20)
        else:
            s, off = target
            ok = self.rack.can_place_on_shelf(dev, s, off)
            d["target"], d["ok"] = (s.uid, off), ok
            d["text"] = (f"Fachboden HE {fmt_u(s.position)} · {off} mm von links"
                         + ("" if ok else " – kein Platz"))
            tmp = copy.copy(dev)
            tmp.shelf_id, tmp.offset_mm = s.uid, off
            b = _shelf_device(self.rack, s, tmp, (s.position - 1) * U_MM, "", False, False)
            lo, hi = b.lo, b.hi
        self._ghost = Box((lo[0] - 1, lo[1], lo[2] - 1), (hi[0] + 1, hi[1] + 1, hi[2] + 1),
                          GHOST_OK if d["ok"] else GHOST_BAD,
                          outline=QColor(255, 255, 255, 160), outline_w=1.5, shade=False)
        self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def _update_drag(self, pos: QPointF):
        d = self._drag
        d["mouse"] = pos
        if d.get("shelf_mode"):
            self._update_shelf_drag(pos)
            return
        top = self.rack.get(d["top"])
        if top is None:
            return
        y = self._plane_y(pos, d["center"])
        if y is None:
            return
        span = self.rack.span(top)
        raw = y / U_MM - d["grab"] + 1
        if self.fine or abs(span - round(span)) > EPS:
            new = snap_third(raw)
        else:
            new = float(round(raw))
        new = max(1.0, min(float(self.rack.height_u) - span + 1, new))
        ok = self.rack.is_free(new, span, ignore=top.uid, side=top.mount_side)
        d["pos"], d["ok"] = new, ok
        d["text"] = f"HE {fmt_u(new)}" + ("" if ok else " – belegt")
        y0 = (new - 1) * U_MM
        depth = max(UNKNOWN_DEPTH, float(self.rack.depth_of(top)))
        z0, z1 = _zrange(top.mount_side, depth, -EAR_D, self.rack)
        self._ghost = Box((-EAR_HALF - 2, y0, z0 - 1), (EAR_HALF + 2, y0 + span * U_MM, z1 + 1),
                          GHOST_OK if ok else GHOST_BAD, outline=QColor(255, 255, 255, 160),
                          outline_w=1.5, shade=False)
        self.setCursor(Qt.SizeVerCursor)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._press is None:
            return
        start = self._press[0]
        moved = math.hypot(e.position().x() - start.x(), e.position().y() - start.y()) >= 4
        d = self._drag
        self._press = None
        self._drag = None
        self._ghost = None
        self.setCursor(Qt.ArrowCursor)
        if d is not None and d["active"] and d.get("shelf_mode"):
            if d["ok"] and d["target"] is not None:
                dev = self.rack.get(d["uid"])
                shelf_uid, off = d["target"]
                if dev is not None and (dev.shelf_id, dev.offset_mm) != (shelf_uid, off):
                    self.shelfMoveRequested.emit(d["uid"], shelf_uid, off)
            self.update()
            return
        if d is not None and d["active"]:
            top = self.rack.get(d["top"])
            if top is not None and d["ok"] and abs(d["pos"] - top.position) > EPS:
                self.moveRequested.emit(top.uid, d["pos"])
            self.update()
            return
        if not moved and e.button() == Qt.LeftButton:
            uid = self.pick(e.position())
            if uid != self.selected_uid:
                self.selected_uid = uid
                self.refresh()
                self.selectedChanged.emit(uid)
        self.update()

    def mouseDoubleClickEvent(self, e):
        uid = self.pick(e.position())
        if uid:
            self.focus_item(uid)

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120
        if steps:
            self.zoom(1.15 ** steps)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Delete and self.selected_uid and not self.read_only:
            self.deleteRequested.emit()
            return
        if k == Qt.Key_Left:
            self.cam.yaw -= math.radians(10)
        elif k == Qt.Key_Right:
            self.cam.yaw += math.radians(10)
        elif k in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom(1.15)
            return
        elif k == Qt.Key_Minus:
            self.zoom(1 / 1.15)
            return
        else:
            super().keyPressEvent(e)
            return
        self._camera_changed()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if self._press is None:
            self.setCursor(Qt.ArrowCursor)

