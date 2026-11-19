"""Datenmodell: Schrank, Geräte, Fachböden, Belegung und Tiefenprüfung.

Reines Python ohne Qt – gemeinsamer Kern für die Desktop-Version (2D und 3D) und die Webversion.
"""

from __future__ import annotations

import datetime as _dt
import math
import uuid
from dataclasses import asdict, dataclass, field

APP_NAME = "Rack-Planer"

CAT_NAS = "NAS"
CAT_FIREWALL = "Firewall"
CAT_SERVER = "Server"
CAT_USV = "USV"
CAT_SWITCH = "Switch"
CAT_ROUTER = "Router"
CAT_PATCH = "Patchpanel"
CAT_ACCESSORY = "Zubehör"
CAT_OTHER = "Sonstiges"
CAT_NVR = "NVR"
CAT_PBX = "Telefonanlage"
CAT_SHELF = "Fachboden"

CATEGORIES = [CAT_NAS, CAT_FIREWALL, CAT_SERVER, CAT_USV, CAT_SWITCH, CAT_ROUTER, CAT_NVR, CAT_PBX,
              CAT_PATCH, CAT_ACCESSORY, CAT_OTHER]
CRITICAL_CATEGORIES = (CAT_NAS, CAT_FIREWALL, CAT_SERVER)

CATEGORY_COLORS = {
    CAT_NAS: "#2f6fb3",
    CAT_FIREWALL: "#c0392b",
    CAT_SERVER: "#3d4a5c",
    CAT_USV: "#d68910",
    CAT_SWITCH: "#1e8449",
    CAT_ROUTER: "#8e44ad",
    CAT_PATCH: "#5d6d7e",
    CAT_ACCESSORY: "#7f8c8d",
    CAT_OTHER: "#2e86c1",
    CAT_NVR: "#138d75",
    CAT_PBX: "#a04000",
    CAT_SHELF: "#95a5a6",
}

# Montageseite
FRONT = "front"
REAR = "rear"
SIDES = (FRONT, REAR)
SIDE_LABEL = {FRONT: "Vorderseite", REAR: "Rückseite"}
SIDE_SHORT = {FRONT: "vorne", REAR: "hinten"}


def other_side(side: str) -> str:
    return REAR if side == FRONT else FRONT


SHELF_WIDTH_MM = 450     # nutzbare Breite eines 19"-Fachbodens (Innenmaß)
U_MM = 44.45             # Höhe einer Höheneinheit in mm
DEFAULT_DEPTH_MM = 800   # Einbautiefe eines neuen Schranks
DEPTH_PRESETS = (450, 600, 800, 1000, 1200)
EPS = 1e-6
MAX_IPS = 5              # IP-Adressen je Gerät


def today_iso() -> str:
    return _dt.date.today().isoformat()


def snap_third(value: float) -> float:
    """Auf das Lochraster (⅓ HE) runden."""
    return round(value * 3) / 3


def fmt_u(value: float) -> str:
    """HE-Angabe mit Dritteln, z. B. 10, 10⅓, 10⅔."""
    whole = math.floor(value + EPS)
    frac = round((value - whole) * 3)
    if frac == 3:
        whole, frac = whole + 1, 0
    return f"{whole}" + {0: "", 1: "⅓", 2: "⅔"}.get(frac, "")


def fmt_range(pos: float, span: float) -> str:
    """HE-Bereich, z. B. „5“ oder „5–6“."""
    return fmt_u(pos) if span <= 1 + EPS else f"{fmt_u(pos)}–{fmt_u(pos + span - 1)}"


def fmt_date(iso: str) -> str:
    """ISO-Datum (2026-11-17) als 17.11.2026; Unlesbares unverändert."""
    try:
        return _dt.date.fromisoformat(iso[:10]).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return iso or ""


def split_ips(text: str) -> list[str]:
    """Mehrere IP-Adressen aus einer Eingabe (getrennt durch Komma, Semikolon oder
    Leerzeichen). Eine Subnetzmaske hinter einer Adresse (… 255.255.255.0) bleibt dabei."""
    out: list[str] = []
    for tok in text.replace(";", ",").replace(" ", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if out and tok.startswith("255.") and "/" not in out[-1] and " " not in out[-1]:
            out[-1] += " " + tok
        else:
            out.append(tok)
    return out


def units_for_cm(height_cm: float) -> int:
    """Benötigte HE für ein Gerät mit der angegebenen Höhe in cm."""
    return max(1, math.ceil(height_cm * 10 / U_MM - 1e-6))


def ceil_third(value: float) -> float:
    """Auf das nächste Schraubenloch (⅓ HE) aufrunden."""
    return math.ceil(value * 3 - 1e-6) / 3


PLATE_U = 1 / 3          # Bodenplatte eines Fachbodens: unteres Drittel seiner HE


@dataclass
class Item:
    name: str
    category: str
    height_u: int = 1
    ip: str = ""
    model: str = ""
    rackmount: bool = True
    width_mm: int = 440      # nur für Geräte auf einem Fachboden relevant
    power_w: float = 0.0
    position: float = 0      # unterste HE (1 = ganz unten, Drittel möglich); 0 auf Fachboden
    shelf_id: str = ""       # gesetzt, wenn das Gerät auf einem Fachboden steht
    offset_mm: int = -1      # Abstand vom linken Rand des Fachbodens (-1 = automatisch)
    height_cm: float = 0.0   # tatsächliche Höhe nicht rackfähiger Geräte
    show_name: bool = True   # Gerätename in der Grafik anzeigen
    ips: list = field(default_factory=list)   # weitere IP-Adressen (max. MAX_IPS - 1)
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    # ab Dateiformat 2
    depth_mm: int = 0        # Einbautiefe ab der Montageseite (0 = unbekannt)
    mount_side: str = FRONT  # FRONT oder REAR; Geräte auf Fachböden: Seite des Fachbodens
    rails: bool = False      # auf Einbauschienen montiert (blockiert die Gegenseite)

    def all_ips(self) -> list[str]:
        """Alle eingetragenen IP-Adressen (Haupt-IP zuerst), höchstens MAX_IPS."""
        out = [a.strip() for a in [self.ip, *self.ips] if a and a.strip()]
        return out[:MAX_IPS]

    @property
    def is_shelf(self) -> bool:
        return self.category == CAT_SHELF

    @property
    def label(self) -> str:
        return self.name or self.model or self.category


@dataclass
class Conflict:
    """Tiefenproblem im Schrank.

    kind: "too_deep" (Gerät tiefer als der Schrank), "depth" (vorne + hinten zusammen zu
    tief) oder "rails" (Einbauschienen blockieren die Gegenseite)."""
    kind: str
    uids: tuple
    pos: float
    span: float
    text: str


class Rack:
    def __init__(self, name: str = "Serverschrank", height_u: int = 12,
                 depth_mm: int = DEFAULT_DEPTH_MM, as_of: str | None = None):
        self.name = name
        self.height_u = height_u
        self.depth_mm = depth_mm          # nutzbare Einbautiefe in mm
        self.as_of = today_iso() if as_of is None else as_of   # „Aktueller Stand“ (ISO)
        self.items: list[Item] = []

    # --- Abfragen ------------------------------------------------------------
    def get(self, uid: str) -> Item | None:
        return next((i for i in self.items if i.uid == uid), None)

    def top_level(self, side: str | None = None) -> list[Item]:
        return [i for i in self.items
                if not i.shelf_id and (side is None or i.mount_side == side)]

    def on_shelf(self, shelf_uid: str) -> list[Item]:
        return [i for i in self.items if i.shelf_id == shelf_uid]

    def devices(self) -> list[Item]:
        return [i for i in self.items if not i.is_shelf]

    def top_of(self, item: Item) -> Item:
        """Element der obersten Ebene (für Geräte auf einem Fachboden: der Fachboden)."""
        return (self.get(item.shelf_id) or item) if item.shelf_id else item

    def side_of(self, item: Item) -> str:
        return self.top_of(item).mount_side

    @staticmethod
    def load_u(dev: Item) -> float:
        """Tatsächliche Höhe eines Geräts auf einem Fachboden in HE (aus der Höhe in cm)."""
        return dev.height_cm * 10 / U_MM if dev.height_cm > 0 else float(dev.height_u)

    def shelf_span(self, shelf: Item, extra: Item | None = None) -> float:
        """Belegte HE eines Fachbodens: Bodenplatte plus höchstes Gerät, aufgerundet auf
        das nächste Schraubenloch (⅓ HE), mindestens die Höhe des Fachbodens selbst."""
        devs = [d for d in self.on_shelf(shelf.uid) if extra is None or d.uid != extra.uid]
        if extra is not None:
            devs.append(extra)
        load = max((self.load_u(d) for d in devs), default=0.0)
        if load <= 0:
            return float(shelf.height_u)
        return max(float(shelf.height_u), ceil_third(PLATE_U + load))

    def span(self, item: Item, height_override: int | None = None) -> float:
        """Belegte HE eines Elements der obersten Ebene (Fachboden inkl. Aufbau)."""
        if item.is_shelf:
            return self.shelf_span(item)
        return item.height_u if height_override is None else height_override

    def shelf_overlaps(self, shelf_uid: str, offset: int, width: int, exclude: str = "") -> bool:
        if offset < 0 or offset + width > SHELF_WIDTH_MM:
            return True
        for d in self.on_shelf(shelf_uid):
            if d.uid != exclude and d.offset_mm >= 0 and \
                    offset < d.offset_mm + d.width_mm and d.offset_mm < offset + width:
                return True
        return False

    def shelf_gap(self, shelf_uid: str, width: int, exclude: str = "") -> int:
        """Erste freie Lücke von links auf dem Fachboden; -1 = kein Platz."""
        cands = [0] + sorted(d.offset_mm + d.width_mm for d in self.on_shelf(shelf_uid)
                             if d.uid != exclude and d.offset_mm >= 0)
        for c in cands:
            if not self.shelf_overlaps(shelf_uid, c, width, exclude):
                return c
        return -1

    def can_place_on_shelf(self, dev: Item, shelf: Item, offset: int) -> bool:
        """Passt dev an Position offset auf den Fachboden (Breite und Höhe)?"""
        if self.shelf_overlaps(shelf.uid, offset, dev.width_mm, exclude=dev.uid):
            return False
        old = dev.shelf_id, dev.offset_mm
        dev.shelf_id, dev.offset_mm = shelf.uid, offset
        try:
            return self.is_free(shelf.position, self.span(shelf), ignore=shelf.uid,
                                side=shelf.mount_side)
        finally:
            dev.shelf_id, dev.offset_mm = old

    def normalize(self):
        """Ergänzt fehlende oder ungültige Werte (z. B. aus älteren Projektdateien)."""
        for d in self.items:
            if not d.rackmount and d.height_cm <= 0:
                d.height_cm = round(d.height_u * U_MM / 10, 1)
            if d.mount_side not in SIDES:
                d.mount_side = FRONT
            d.depth_mm = max(0, int(d.depth_mm or 0))
        for s in (i for i in self.items if i.is_shelf):
            for d in self.on_shelf(s.uid):
                d.mount_side = s.mount_side
                if d.offset_mm < 0:
                    d.offset_mm = max(0, self.shelf_gap(s.uid, d.width_mm, exclude=d.uid))

    def is_free(self, pos: float, span: int, ignore: str = "", side: str = FRONT) -> bool:
        """Ist der Bereich auf der angegebenen Montageseite frei? Geräte der Gegenseite
        belegen keine HE dieser Seite – ob die Tiefe reicht, prüft conflicts()."""
        if pos < 1 - EPS or pos + span - 1 > self.height_u + EPS:
            return False
        for it in self.top_level(side):
            if it.uid == ignore:
                continue
            a, b = it.position, it.position + self.span(it)
            if pos < b - EPS and a < pos + span - EPS:
                return False
        return True

    @staticmethod
    def _step(span: float) -> float:
        """Raster für die Platzsuche: ganze HE, bei Bruchteilen ⅓ HE."""
        return 1.0 if abs(span - round(span)) < EPS else 1 / 3

    def find_free(self, span: float, side: str = FRONT) -> float:
        """Höchste freie Position (Schrank wird von oben befüllt); 0 = kein Platz."""
        step = self._step(span)
        pos = snap_third(math.floor((self.height_u - span + 1) / step + EPS) * step)
        while pos >= 1 - EPS:
            if self.is_free(pos, span, side=side):
                return int(pos) if step == 1 else pos
            pos = snap_third(pos - step)
        return 0

    def nearest_free(self, pos: float, span: float, ignore: str = "", side: str = FRONT) -> float:
        """Freie Position möglichst nah an pos; 0 = kein Platz."""
        step = self._step(span)
        for k in range(int(self.height_u / step) + 1):
            dist = k * step
            for cand in (snap_third(pos - dist), snap_third(pos + dist)):
                if self.is_free(cand, span, ignore, side):
                    return cand
        return 0

    def _occupied_thirds(self, side: str | None = None) -> set[int]:
        out: set[int] = set()
        for it in self.top_level(side):
            a = round(it.position * 3)
            out.update(range(a, a + round(3 * self.span(it))))
        return out

    def used_u(self, side: str | None = None) -> float:
        """Belegte HE (beide Seiten zusammen oder nur eine Seite)."""
        return len(self._occupied_thirds(side)) / 3

    def required_height(self) -> int:
        top = max((i.position + self.span(i) - 1 for i in self.top_level()), default=0)
        return math.ceil(top - EPS)

    def missing_ups(self) -> list[str]:
        cats = {d.category for d in self.devices()}
        if CAT_USV in cats:
            return []
        return [c for c in CRITICAL_CATEGORIES if c in cats]

    def total_power(self) -> float:
        return sum(d.power_w for d in self.devices())

    def power_summary(self) -> str:
        """Max. Stromlast und Wärmelast als Text (für Exporte)."""
        def num(v: float, digits: int = 0) -> str:
            t = f"{v:,.{digits}f}"
            return t.replace(",", "X").replace(".", ",").replace("X", ".")
        p = self.total_power()
        return (f"Max. Stromlast: {num(p)} W (≈ {num(p / 230, 1)} A bei 230 V)   ·   "
                f"Wärmelast: {num(p)} W ≈ {num(p * 3.412)} BTU/h")

    # --- Tiefe ---------------------------------------------------------------
    def depth_of(self, item: Item) -> int:
        """Belegte Tiefe eines Elements der obersten Ebene (Fachboden: inkl. Geräten)."""
        if item.is_shelf:
            return max([item.depth_mm, *(d.depth_mm for d in self.on_shelf(item.uid))])
        return item.depth_mm

    def facing(self, pos: float, span: float, side: str, ignore: str = "") -> list[Item]:
        """Elemente der Gegenseite, die sich mit dem HE-Bereich überschneiden."""
        out = []
        for it in self.top_level(other_side(side)):
            if it.uid == ignore:
                continue
            a, b = it.position, it.position + self.span(it)
            if pos < b - EPS and a < pos + span - EPS:
                out.append(it)
        return out

    def free_depth(self, pos: float, span: float, side: str, ignore: str = "") -> int:
        """Freie Tiefe für ein Gerät an diesem Platz (Schranktiefe minus Gegenseite)."""
        used = max((self.depth_of(o) for o in self.facing(pos, span, side, ignore)), default=0)
        return max(0, self.depth_mm - used)

    def rail_blockers(self, pos: float, span: float, side: str, ignore: str = "") -> list[Item]:
        """Geräte der Gegenseite, deren Einbauschienen diesen HE-Bereich blockieren."""
        return [o for o in self.facing(pos, span, side, ignore) if o.rails]

    def conflicts(self) -> list[Conflict]:
        out: list[Conflict] = []
        dmax = self.depth_mm
        for it in self.top_level():
            d = self.depth_of(it)
            if dmax > 0 and d > dmax:
                out.append(Conflict(
                    "too_deep", (it.uid,), it.position, self.span(it),
                    f"„{it.label}“ ist {d} mm tief, der Schrank hat nur {dmax} mm Einbautiefe."))
        for f in self.top_level(FRONT):
            fa, fb = f.position, f.position + self.span(f)
            for r in self.top_level(REAR):
                ra, rb = r.position, r.position + self.span(r)
                lo, hi = max(fa, ra), min(fb, rb)
                if hi - lo <= EPS:
                    continue
                he = fmt_range(lo, hi - lo)
                if f.rails or r.rails:
                    rail = f if f.rails else r
                    victim = r if rail is f else f
                    out.append(Conflict(
                        "rails", (f.uid, r.uid), lo, hi - lo,
                        f"„{rail.label}“ ({SIDE_SHORT[rail.mount_side]}) sitzt auf "
                        f"Einbauschienen, die HE {he} auf der {SIDE_LABEL[victim.mount_side]} "
                        f"blockieren – dort ist „{victim.label}“ montiert."))
                    continue
                df, dr = self.depth_of(f), self.depth_of(r)
                if dmax > 0 and df + dr > dmax:
                    out.append(Conflict(
                        "depth", (f.uid, r.uid), lo, hi - lo,
                        f"HE {he}: „{f.label}“ (vorne, {df} mm) und „{r.label}“ (hinten, "
                        f"{dr} mm) brauchen zusammen {df + dr} mm – Einbautiefe {dmax} mm."))
        return out

    def conflict_uids(self) -> set[str]:
        return {u for c in self.conflicts() for u in c.uids}

    def rail_devices(self) -> list[Item]:
        """Elemente mit Einbauschienen (für den Hinweis „hinten blockiert“)."""
        return [i for i in self.top_level() if i.rails]

    # --- Änderungen ----------------------------------------------------------
    def remove(self, uid: str):
        self.items = [i for i in self.items if i.uid != uid and i.shelf_id != uid]

    # --- Speichern/Laden (nur der Schrank; Datei inkl. Historie: fileformat) --
    def to_dict(self) -> dict:
        return {"name": self.name, "height_u": self.height_u, "depth_mm": self.depth_mm,
                "as_of": self.as_of, "items": [asdict(i) for i in self.items]}

    @classmethod
    def from_dict(cls, data: dict) -> "Rack":
        rack = cls(data.get("name", "Serverschrank"), int(data.get("height_u", 12)),
                   int(data.get("depth_mm") or DEFAULT_DEPTH_MM), str(data.get("as_of") or ""))
        known = set(Item.__dataclass_fields__)
        rack.items = []
        for d in data.get("items", []):
            item = Item(**{k: v for k, v in d.items() if k in known})
            item.ips = [str(a) for a in item.ips if str(a).strip()][:MAX_IPS - 1]
            if "show_name" not in d and item.is_shelf:
                item.show_name = False      # ältere Dateien: Fachboden ohne Namen
            rack.items.append(item)
        rack.normalize()
        return rack
