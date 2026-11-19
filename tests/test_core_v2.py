"""Tests für Version 2: IP-Vergleich, Vorder-/Rückseite, Tiefe, Dateiformat, Historie."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rackcore import (  # noqa: E402
    CAT_ACCESSORY, CAT_NAS, CAT_SERVER, CAT_SHELF, CAT_SWITCH, FORMAT_VERSION, FRONT, REAR,
    TEMPLATES, Item, Rack, RackDocument, duplicate_ips, find_template, ip_is_valid, ip_key,
    load_document, save_document, split_ips,
)


def dev(name="Gerät", cat=CAT_SWITCH, h=1, pos=1, **kw) -> Item:
    return Item(name=name, category=cat, height_u=h, position=pos, **kw)


# --- doppelte IP-Adressen: Subnetzmaske spielt keine Rolle ------------------------
def test_ip_key_ignores_any_mask_notation():
    same = ["192.168.1.10", "192.168.1.10/24", "192.168.1.10/16", "192.168.1.10/255.255.255.0",
            "192.168.1.10 255.255.0.0", " 192.168.1.10 / 24 ", "192.168.001.010"]
    assert {ip_key(a) for a in same} == {"192.168.1.10"}
    assert ip_key("FE80::1/64") == ip_key("fe80:0:0::1") == ip_key("fe80::1%eth0")
    assert ip_key("192.168.1.11/24") != ip_key("192.168.1.10/24")


def test_ip_validation_with_masks():
    assert ip_is_valid("192.168.1.10 255.255.255.0")
    assert ip_is_valid("192.168.1.10/255.255.255.0")
    assert not ip_is_valid("192.168.1.10/33")
    assert not ip_is_valid("192.168.1.10 255.0.255.0")
    assert not ip_is_valid("192.168.1.10 foo bar")


def test_duplicate_ips_with_different_masks():
    r = Rack()
    r.items += [dev("A", ip="10.0.0.5/8"), dev("B", pos=2, ip="10.0.0.5/24"),
                dev("C", pos=3, ips=["10.0.0.5 255.255.255.0"])]
    dups = duplicate_ips(r)
    assert list(dups) == ["10.0.0.5"]
    assert [d.name for d in dups["10.0.0.5"]] == ["A", "B", "C"]


def test_split_ips_keeps_mask_with_address():
    assert split_ips("192.168.1.10 255.255.255.0, 10.0.0.1") == [
        "192.168.1.10 255.255.255.0", "10.0.0.1"]
    assert split_ips("10.0.0.1; 10.0.0.2 10.0.0.3") == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]


# --- Vorder- und Rückseite ---------------------------------------------------------
def test_front_and_rear_share_units():
    r = Rack(height_u=12, depth_mm=800)
    r.items.append(dev("Switch", pos=5, depth_mm=250))
    assert not r.is_free(5, 1, side=FRONT)
    assert r.is_free(5, 1, side=REAR)               # hinten ist HE 5 noch frei
    r.items.append(dev("PDU", pos=5, depth_mm=50, mount_side=REAR))
    assert not r.is_free(5, 1, side=REAR)
    assert r.find_free(1, REAR) == 12
    assert r.used_u(FRONT) == 1 and r.used_u(REAR) == 1 and r.used_u() == 1


def test_depth_capacity_example():
    """80 cm Schrank, hinten 5 cm Steckdosenleiste → vorne noch 75 cm frei."""
    r = Rack(depth_mm=800)
    pdu = dev("PDU", cat=CAT_ACCESSORY, pos=3, depth_mm=50, mount_side=REAR)
    r.items.append(pdu)
    assert r.free_depth(3, 1, FRONT) == 750
    assert r.free_depth(4, 1, FRONT) == 800
    r.items.append(dev("Server", cat=CAT_SERVER, pos=3, depth_mm=750))
    assert r.conflicts() == []
    r.items[-1].depth_mm = 760
    c = r.conflicts()
    assert [x.kind for x in c] == ["depth"]
    assert "810 mm" in c[0].text and "800 mm" in c[0].text


def test_rails_block_other_side():
    r = Rack(depth_mm=1000)
    nas = dev("NAS", cat=CAT_NAS, h=2, pos=5, depth_mm=300, rails=True)
    pdu = dev("PDU", cat=CAT_ACCESSORY, pos=6, depth_mm=50, mount_side=REAR)
    r.items += [nas, pdu]
    c = r.conflicts()
    assert [x.kind for x in c] == ["rails"]
    assert c[0].pos == 6 and c[0].span == 1
    assert r.conflict_uids() == {nas.uid, pdu.uid}
    assert r.rail_blockers(6, 1, REAR) == [nas]
    pdu.position = 7                               # oberhalb der Schienen: kein Konflikt
    assert r.conflicts() == []


def test_too_deep_for_rack():
    r = Rack(depth_mm=600)
    r.items.append(dev("Server", cat=CAT_SERVER, h=2, pos=1, depth_mm=750))
    assert [x.kind for x in r.conflicts()] == ["too_deep"]


def test_shelf_depth_includes_devices():
    r = Rack(depth_mm=600)
    s = Item(name="Fachboden", category=CAT_SHELF, position=1, depth_mm=350, show_name=False)
    r.items += [s, Item(name="DS", category=CAT_NAS, rackmount=False, height_u=4,
                        depth_mm=420, shelf_id=s.uid, offset_mm=0)]
    assert r.depth_of(s) == 420


def test_shelf_devices_follow_shelf_side():
    r = Rack.from_dict({"items": [
        {"name": "F", "category": CAT_SHELF, "position": 1, "uid": "s", "mount_side": "rear"},
        {"name": "D", "category": CAT_NAS, "rackmount": False, "shelf_id": "s", "uid": "d"}]})
    assert r.get("d").mount_side == REAR
    assert r.side_of(r.get("d")) == REAR


def test_templates_have_depth():
    assert all(t.depth_mm > 0 or t.full_depth for t in TEMPLATES)
    assert find_template("HD6500").depth_mm == 1020 and find_template("HD6500").rails
    assert find_template("RackStation RS4021xs+").height_u == 3
    assert not find_template("Patchpanel 24 Port (1 HE)").rails
    assert find_template("Server 2 HE").rails and find_template("USV 2 HE").rails


# --- Dateiformat ---------------------------------------------------------------------
def test_new_rack_as_of_is_creation_date():
    import datetime
    assert Rack().as_of == datetime.date.today().isoformat()


def test_load_v1_file_fills_depth_from_templates(tmp_path):
    f = tmp_path / "alt.rack.json"
    f.write_text(json.dumps({"app": "Rack-Planer", "version": 1, "name": "Alt", "height_u": 12,
                             "items": [
                                 {"name": "Server", "category": "Server", "model": "Server 2 HE",
                                  "height_u": 2, "position": 1, "uid": "a"},
                                 {"name": "X", "category": "Sonstiges", "model": "",
                                  "height_u": 1, "position": 5, "uid": "b"}]}),
                 encoding="utf-8")
    doc = load_document(f)
    r = doc.rack
    assert r.get("a").depth_mm == 750 and r.get("a").rails
    assert r.get("b").depth_mm == 0                 # unbekannt
    assert all(i.mount_side == FRONT for i in r.items)
    assert r.depth_mm == 800                        # 600 reicht nicht für 750 mm Server
    assert r.as_of                                  # Dateidatum
    assert doc.notes and not doc.history_enabled


def test_v2_file_is_readable_by_v1_loader(tmp_path):
    """Abwärtskompatibel: Version 1.01 liest nur name/height_u/items und ignoriert
    unbekannte Felder – das muss mit Dateien aus Version 2 weiterhin klappen."""
    r = Rack("Neu", 9)
    r.items.append(dev("Switch", pos=9, depth_mm=250, mount_side=REAR, rails=False))
    doc = RackDocument(rack=r)
    doc.history_enabled = True
    doc.add_snapshot(r.to_dict(), "2026-01-01T10:00:00")
    f = tmp_path / "neu.rack.json"
    save_document(doc, f)
    data = json.loads(f.read_text(encoding="utf-8"))
    assert data["name"] == "Neu" and data["height_u"] == 9 and len(data["items"]) == 1
    assert data["format"] == FORMAT_VERSION
    old_fields = {"name", "category", "height_u", "ip", "model", "rackmount", "width_mm",
                  "power_w", "position", "shelf_id", "offset_mm", "height_cm", "show_name",
                  "ips", "uid"}
    assert old_fields <= set(data["items"][0])


def test_history_roundtrip(tmp_path):
    r = Rack("Schrank", 12)
    r.as_of = "2026-01-10"
    r.items.append(dev("Alt", pos=12))
    doc = RackDocument(rack=r, history_enabled=True)
    first = r.to_dict()
    assert doc.add_snapshot(first, "2026-01-10T09:00:00")
    assert not doc.add_snapshot(first, "2026-01-11T09:00:00")      # doppelt: übersprungen
    r.items[0].name = "Neu"
    r.as_of = "2026-02-01"
    f = tmp_path / "h.rack.json"
    save_document(doc, f)
    back = load_document(f)
    assert back.history_enabled
    assert len(back.history) == 1
    old = back.history[0].to_rack()
    assert old.items[0].name == "Alt" and old.as_of == "2026-01-10"
    assert back.rack.items[0].name == "Neu" and back.rack.as_of == "2026-02-01"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["h.rack.json"]    # eine Datei
