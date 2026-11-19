"""Gerätevorlagen (Maße, Leistung, Tiefe, Einbauschienen).

Maße und Leistungswerte laut Herstellerangaben, gerundet; Leistung im Betrieb typisch.
Wo es keine offiziellen Angaben gibt (Platzhalter wie „Switch 24 Port“ oder Patchpanels),
ist die Tiefe ein typischer Schätzwert und in der Notiz mit „ca.“ gekennzeichnet.
Nicht rackfähige Geräte: HE = benötigte Höhe auf einem Fachboden.

Die Vorlagen selbst stehen in vorlagen.json (gemeinsam für Desktop- und Webversion).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .model import SHELF_WIDTH_MM, units_for_cm


@dataclass
class Template:
    group: str
    model: str
    category: str
    height_u: int
    rackmount: bool
    width_mm: int = SHELF_WIDTH_MM
    power_w: float = 0.0
    note: str = ""
    height_cm: float = 0.0
    depth_mm: int = 0          # Einbautiefe in mm (0 = unbekannt)
    rails: bool = False        # wird typischerweise auf Einbauschienen montiert
    full_depth: bool = False   # Tiefe = Einbautiefe des Schranks (z. B. 4-Punkt-Fachboden)


VORLAGEN_DATEI = Path(__file__).resolve().with_name("vorlagen.json")


def template_from_dict(d: dict) -> Template:
    """Vorlage aus einem Eintrag der vorlagen.json. Nicht rackfähige Geräte: HE ergeben sich aus
    der Höhe in cm (falls height_u fehlt)."""
    rackmount = bool(d.get("rackmount", True))
    height_cm = float(d.get("height_cm") or 0) if not rackmount else 0.0
    if rackmount:
        height_u = max(1, int(d.get("height_u") or 1))
    else:
        height_u = int(d["height_u"]) if d.get("height_u") else units_for_cm(height_cm)
    return Template(str(d.get("group", "")), str(d.get("model", "")), str(d.get("category", "")),
                    height_u, rackmount, int(d.get("width_mm") or SHELF_WIDTH_MM),
                    float(d.get("power_w") or 0), str(d.get("note") or ""), height_cm,
                    int(d.get("depth_mm") or 0), bool(d.get("rails")), bool(d.get("full_depth")))


def load_templates(path: str | Path = VORLAGEN_DATEI) -> list[Template]:
    """Vorlagen aus der JSON-Datei laden (gemeinsame Quelle für Desktop- und Webversion)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [template_from_dict(d) for d in data["vorlagen"]]


# Maße und Leistungswerte stehen in rackcore/vorlagen.json (eine Zeile je Vorlage) – dort
# lassen sich Vorlagen ergänzen oder ändern, ohne Programmcode anzufassen.
TEMPLATES: list[Template] = load_templates()

# Standardtiefe eines neuen Fachbodens (mm), höchstens die Schranktiefe
SHELF_DEPTH_MM = 400

def find_template(model: str) -> Template | None:
    """Vorlage zu einem Modellnamen (für das Ergänzen fehlender Werte älterer Dateien)."""
    return next((t for t in TEMPLATES if t.model == model), None)


def template_matches(t: Template, query: str) -> bool:
    """Suchfilter für die Vorlagenliste: alle Wörter müssen in Gruppe, Modell,
    Kategorie oder Maßangabe vorkommen (Groß-/Kleinschreibung egal)."""
    hay = f"{t.group} {t.model} {t.category} {t.note}".lower()
    return all(w in hay for w in query.lower().split())
