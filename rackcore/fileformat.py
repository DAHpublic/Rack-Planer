"""Projektdatei (*.rack.json): ein Schrank inklusive Historie in einer Datei.

Aufbau (Format 2, JSON, UTF-8):

    {
      "app": "Rack-Planer", "format": 2, "version": 2,
      "name": …, "height_u": …, "depth_mm": …, "as_of": "2026-11-17", "items": [ … ],
      "created": "2026-11-17", "saved_at": "2026-11-17T21:30:00",
      "history": {"enabled": true, "declined": false,
                  "entries": [{"saved_at": …, "as_of": …, "note": "", "rack": {…}}]}
    }

Der Schrank selbst steht wie in Format 1 auf oberster Ebene; ältere Programmversionen
können neue Dateien daher weiterhin öffnen (sie ignorieren Tiefe, Seite und Historie).
Dateien aus Format 1 werden beim Laden ergänzt (siehe migrate()).
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .model import APP_NAME, DEFAULT_DEPTH_MM, DEPTH_PRESETS, FRONT, Rack, today_iso
from .templates import SHELF_DEPTH_MM, find_template

FORMAT_VERSION = 2
FILE_SUFFIX = ".rack.json"


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


@dataclass
class Snapshot:
    """Ein früherer Stand des Schranks."""
    saved_at: str           # wann dieser Stand gespeichert wurde
    as_of: str              # „Aktueller Stand“ dieses Stands
    rack: dict              # Rack.to_dict()
    note: str = ""

    def to_rack(self) -> Rack:
        return Rack.from_dict(copy.deepcopy(self.rack))

    def to_dict(self) -> dict:
        return {"saved_at": self.saved_at, "as_of": self.as_of, "note": self.note,
                "rack": self.rack}

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        rack = dict(d.get("rack") or {})
        migrate(rack, notes=None)
        return cls(str(d.get("saved_at", "")), str(d.get("as_of") or rack.get("as_of", "")),
                   rack, str(d.get("note", "")))


@dataclass
class RackDocument:
    """Inhalt einer Projektdatei: aktueller Schrank plus Historie."""
    rack: Rack = field(default_factory=Rack)
    created: str = field(default_factory=today_iso)
    saved_at: str = ""
    history: list[Snapshot] = field(default_factory=list)
    history_enabled: bool = False
    history_declined: bool = False     # Angebot „Historie anlegen“ abgelehnt
    notes: list[str] = field(default_factory=list)   # Hinweise beim Laden (nicht gespeichert)

    def add_snapshot(self, rack_dict: dict, saved_at: str, note: str = "") -> bool:
        """Früheren Stand anhängen; doppelte Stände werden übersprungen."""
        rack_dict = copy.deepcopy(rack_dict)
        if self.history and self.history[-1].rack == rack_dict:
            return False
        self.history.append(Snapshot(saved_at, str(rack_dict.get("as_of", "")), rack_dict,
                                     note))
        return True

    def to_dict(self) -> dict:
        data = {"app": APP_NAME, "format": FORMAT_VERSION, "version": FORMAT_VERSION}
        data.update(self.rack.to_dict())
        data["created"] = self.created
        data["saved_at"] = self.saved_at
        data["history"] = {"enabled": self.history_enabled, "declined": self.history_declined,
                           "entries": [s.to_dict() for s in self.history]}
        return data

    @classmethod
    def from_dict(cls, data: dict, file_date: str = "") -> "RackDocument":
        data = copy.deepcopy(data)
        notes: list[str] = []
        migrate(data, notes, file_date)
        hist = data.get("history") or {}
        if isinstance(hist, list):          # tolerant: nur Liste der Einträge
            hist = {"enabled": bool(hist), "entries": hist}
        doc = cls(rack=Rack.from_dict(data),
                  created=str(data.get("created") or data.get("as_of") or today_iso()),
                  saved_at=str(data.get("saved_at", "")),
                  history=[Snapshot.from_dict(e) for e in hist.get("entries", [])],
                  history_enabled=bool(hist.get("enabled", False)),
                  history_declined=bool(hist.get("declined", False)),
                  notes=notes)
        return doc


def _format_of(data: dict) -> int:
    try:
        return int(data.get("format", data.get("version", 1)))
    except (TypeError, ValueError):
        return 1


def migrate(data: dict, notes: list[str] | None, file_date: str = ""):
    """Ergänzt Werte, die ältere Dateien (Format 1) noch nicht kennen – in place."""
    if _format_of(data) >= 2 and "depth_mm" in data:
        return
    items = data.get("items", [])
    guessed = 0
    for d in items:
        if "depth_mm" in d:
            continue
        t = find_template(str(d.get("model", "")))
        if t is not None:
            d["depth_mm"], d["rails"] = t.depth_mm, t.rails
            guessed += 1
        elif d.get("category") == "Fachboden":
            d["depth_mm"] = SHELF_DEPTH_MM
        d.setdefault("mount_side", FRONT)
    if "depth_mm" not in data:
        depth = DEFAULT_DEPTH_MM
        deepest = max((int(d.get("depth_mm") or 0) for d in items), default=0)
        if deepest > depth:
            depth = next((p for p in DEPTH_PRESETS if p >= deepest), deepest)
        data["depth_mm"] = depth
        if notes is not None:
            notes.append(f"Die Datei enthält noch keine Schranktiefe. Sie wurde auf {depth} mm "
                         "gesetzt – bitte unter „Schrank“ prüfen.")
    if guessed and notes is not None:
        notes.append(f"Für {guessed} Gerät(e) wurden Tiefe und Einbauschienen aus den Vorlagen "
                     "ergänzt.")
    if not data.get("as_of"):
        data["as_of"] = file_date or today_iso()


# ---------------------------------------------------------------------------
# Laden/Speichern
# ---------------------------------------------------------------------------

def _file_date(path: Path) -> str:
    try:
        return _dt.date.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return ""


def load_document(path: str | Path) -> RackDocument:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Keine Rack-Planer-Projektdatei")
    return RackDocument.from_dict(data, _file_date(path))


def save_document(doc: RackDocument, path: str | Path):
    """Speichert atomar: Erst in eine Hilfsdatei im selben Ordner schreiben, dann in
    einem Schritt umbenennen. Bricht das Schreiben ab, bleibt die alte Datei unverändert
    und die Hilfsdatei wird wieder gelöscht. Außerhalb des Zielordners entsteht nichts."""
    path = Path(path)
    data = json.dumps(doc.to_dict(), indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_rack(path: str | Path) -> Rack:
    """Nur den aktuellen Schrank laden (ohne Historie)."""
    return load_document(path).rack


def save_rack(rack: Rack, path: str | Path):
    """Schrank ohne Historie speichern (neue Datei)."""
    save_document(RackDocument(rack=rack, saved_at=now_iso()), path)
