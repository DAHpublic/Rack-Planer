"""Tests für das Datenmodell (ohne Oberfläche). Aufruf: python -m pytest"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rackcore import (  # noqa: E402
    CAT_FIREWALL, CAT_NAS, CAT_SERVER, CAT_SHELF, CAT_SWITCH, CAT_USV, TEMPLATES, Item, Rack,
    duplicate_ips, fmt_u, ip_is_valid, ip_key, load_rack, save_rack, template_matches,
    units_for_cm,
)


def dev(name="Gerät", cat=CAT_SWITCH, h=1, pos=1, **kw) -> Item:
    return Item(name=name, category=cat, height_u=h, position=pos, **kw)


def shelf(pos=1) -> Item:
    return Item(name="Fachboden", category=CAT_SHELF, height_u=1, position=pos, show_name=False)


# --- Belegung ---------------------------------------------------------------------
def test_is_free_and_bounds():
    r = Rack(height_u=12)
    r.items.append(dev(h=2, pos=5))          # belegt HE 5–6
    assert not r.is_free(5, 1)
    assert not r.is_free(6, 1)
    assert not r.is_free(4, 2)
    assert r.is_free(4, 1)
    assert r.is_free(7, 6)                   # HE 7–12
    assert not r.is_free(7, 7)               # ragt über HE 12 hinaus
    assert not r.is_free(0, 1)


def test_find_free_fills_from_top():
    r = Rack(height_u=12)
    assert r.find_free(1) == 12
    r.items.append(dev(pos=12))
    assert r.find_free(2) == 10
    r.items.append(dev(h=11, pos=1))
    assert r.find_free(1) == 0               # voll


def test_thirds():
    r = Rack(height_u=12)
    r.items.append(dev(pos=5))
    assert not r.is_free(5 + 2 / 3, 1)
    assert r.is_free(6, 1)
    assert fmt_u(10 + 1 / 3) == "10⅓"
    assert fmt_u(10 + 2 / 3) == "10⅔"
    assert fmt_u(10) == "10"


def test_shelf_span_grows_with_load():
    r = Rack(height_u=12)
    s = shelf(pos=3)
    r.items.append(s)
    assert r.span(s) == 1
    r.items.append(Item(name="DS", category=CAT_NAS, height_u=4, rackmount=False,
                        width_mm=199, shelf_id=s.uid, offset_mm=0))
    assert r.span(s) == pytest.approx(4 + 1 / 3)      # Bodenplatte ⅓ HE + 4 HE Gerät
    assert r.used_u() == pytest.approx(4 + 1 / 3)
    assert r.required_height() == 7


def test_shelf_overlap_and_gap():
    r = Rack(height_u=12)
    s = shelf()
    r.items.append(s)
    r.items.append(Item(name="A", category=CAT_NAS, rackmount=False, width_mm=200,
                        shelf_id=s.uid, offset_mm=0))
    assert r.shelf_overlaps(s.uid, 100, 100)
    assert not r.shelf_overlaps(s.uid, 200, 250)
    assert r.shelf_overlaps(s.uid, 200, 251)       # breiter als der Fachboden
    assert r.shelf_gap(s.uid, 250) == 200
    assert r.shelf_gap(s.uid, 251) == -1


def test_remove_shelf_removes_devices_on_it():
    r = Rack()
    s = shelf()
    r.items += [s, Item(name="A", category=CAT_NAS, rackmount=False, shelf_id=s.uid)]
    r.remove(s.uid)
    assert r.items == []


def test_missing_ups():
    r = Rack()
    r.items.append(dev(cat=CAT_FIREWALL))
    r.items.append(dev(cat=CAT_SERVER, pos=2))
    assert r.missing_ups() == [CAT_FIREWALL, CAT_SERVER]
    r.items.append(dev(cat=CAT_USV, pos=3))
    assert r.missing_ups() == []


def test_units_for_cm():
    assert units_for_cm(4.4) == 1
    assert units_for_cm(4.5) == 2
    assert units_for_cm(16.6) == 4


# --- IP-Adressen --------------------------------------------------------------------
def test_ip_validation():
    assert ip_is_valid("")
    assert ip_is_valid("192.168.1.10")
    assert ip_is_valid("10.0.0.1/24")
    assert ip_is_valid("fe80::1")
    assert not ip_is_valid("192.168.1.300")
    assert not ip_is_valid("abc")


def test_ip_key_ignores_prefix_and_spaces():
    assert ip_key(" 192.168.1.10/24 ") == ip_key("192.168.1.10")


def test_duplicate_ips():
    r = Rack()
    a = dev("Switch", ip="192.168.1.10")
    b = dev("Firewall", pos=2, ip="192.168.1.11", ips=["192.168.1.10/24"])
    c = dev("NAS", pos=3, ip="192.168.1.12")
    r.items += [a, b, c]
    dups = duplicate_ips(r)
    assert list(dups) == ["192.168.1.10"]
    assert [d.name for d in dups["192.168.1.10"]] == ["Switch", "Firewall"]


def test_duplicate_ip_on_same_device_and_empty_ignored():
    r = Rack()
    r.items.append(dev("Server", ip="10.0.0.5", ips=["10.0.0.5", ""]))
    r.items.append(dev("Leer", pos=2, ip=""))
    assert list(duplicate_ips(r)) == ["10.0.0.5"]


def test_shelf_is_not_counted_for_ips():
    r = Rack()
    s = shelf()
    s.ip = "10.0.0.1"
    r.items += [s, dev(pos=3, ip="10.0.0.1")]
    assert duplicate_ips(r) == {}


# --- Vorlagen-Suche ---------------------------------------------------------------------
def test_template_search():
    names = [t.model for t in TEMPLATES if template_matches(t, "7590")]
    assert names == ["FRITZ!Box 7590 AX"]
    lwl = [t for t in TEMPLATES if template_matches(t, "lwl lc")]
    assert lwl and all("LC" in t.model for t in lwl)
    assert all(template_matches(t, "") for t in TEMPLATES)
    assert not any(template_matches(t, "gibtesnicht") for t in TEMPLATES)


# --- Speichern/Laden ---------------------------------------------------------------------
def test_save_and_load_roundtrip(tmp_path):
    r = Rack("Büro", 15)
    s = shelf(pos=2)
    r.items += [dev("Switch", ip="192.168.1.2", ips=["10.0.0.2"], pos=15, power_w=25), s,
                Item(name="FRITZ!Box", category="Router", rackmount=False, width_mm=251,
                     height_u=2, height_cm=4.8, shelf_id=s.uid, offset_mm=10)]
    f = tmp_path / "test.rack.json"
    save_rack(r, f)
    back = load_rack(f)
    assert back.to_dict() == r.to_dict()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["test.rack.json"]   # keine Reste


def test_save_failure_keeps_old_file(tmp_path, monkeypatch):
    f = tmp_path / "test.rack.json"
    save_rack(Rack("Alt"), f)
    before = f.read_text(encoding="utf-8")

    def boom(*_a, **_k):
        raise OSError("Datenträger voll")
    monkeypatch.setattr("rackcore.fileformat.os.replace", boom)
    with pytest.raises(OSError):
        save_rack(Rack("Neu"), f)
    assert f.read_text(encoding="utf-8") == before
    assert [p.name for p in tmp_path.iterdir()] == ["test.rack.json"]


def test_load_old_file_without_new_fields(tmp_path):
    f = tmp_path / "alt.rack.json"
    f.write_text(json.dumps({"name": "Alt", "height_u": 9, "items": [
        {"name": "Fachboden", "category": "Fachboden", "height_u": 1, "position": 1,
         "uid": "s1"},
        {"name": "DS", "category": "NAS", "height_u": 4, "rackmount": False,
         "shelf_id": "s1", "unbekannt": 1, "uid": "d1"},
    ]}), encoding="utf-8")
    r = load_rack(f)
    assert r.get("s1").show_name is False
    assert r.get("d1").offset_mm == 0
    assert r.get("d1").height_cm == pytest.approx(17.8)
