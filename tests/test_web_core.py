"""Webversion (HTML/PHP): Der Rechenkern im Browser (web/app/*.js) muss dieselben Ergebnisse
liefern wie rackcore. Verglichen werden Dateiformat/Migration, Belegung, Tiefenkonflikte und
IP-Prüfung. Braucht Node.js; ohne Node werden die Tests übersprungen."""
import copy
import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from rackcore import (
    FRONT, REAR, TEMPLATES, Item, Rack, RackDocument, duplicate_ips, ip_is_valid, ip_key,
)

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js nicht installiert")


@pytest.fixture(scope="module")
def js():
    p = subprocess.Popen([NODE, str(ROOT / "tests" / "js" / "parity_worker.js")], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True, encoding="utf-8")

    def call(msg):
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()
        out = json.loads(p.stdout.readline())
        assert "exception" not in out, out["exception"]
        return out["result"]

    call({"templates": [asdict(t) for t in TEMPLATES], "eval": "1"})
    yield call
    p.stdin.close()
    p.wait(5)


def norm(o):
    if isinstance(o, dict):
        return {k: norm(v) for k, v in o.items()}
    if isinstance(o, list):
        return [norm(v) for v in o]
    if isinstance(o, float) and o.is_integer():
        return int(o)
    return o


def sample_rack() -> Rack:
    r = Rack("Test", 12, 600, "2026-11-01")
    r.items = [
        Item("Server", "Server", 2, ip="192.168.1.10/24", position=11, depth_mm=750, rails=True,
             uid="a" * 32),
        Item("Switch", "Switch", 1, ip="192.168.001.010", position=9, depth_mm=250, uid="b" * 32,
             mount_side=REAR),
        Item("Panel", "Patchpanel", 1, position=11, depth_mm=100, uid="c" * 32, mount_side=REAR),
        Item("Fachboden", "Fachboden", 1, position=3, depth_mm=400, uid="d" * 32, show_name=False),
        Item("DS923+", "NAS", 4, rackmount=False, width_mm=199, height_cm=16.6, shelf_id="d" * 32,
             depth_mm=223, uid="e" * 32, ips=["fe80::1%eth0", "10.0.0.1 255.255.255.0"]),
        Item("Tief", "Server", 1, position=1, depth_mm=900, uid="f" * 32),
    ]
    r.normalize()
    return r


def test_file_format_and_migration_match(js):
    old = {"app": "Rack-Planer", "version": 1, "name": "Alt", "height_u": 12, "items": [
        {"name": "NAS", "category": "NAS", "model": "RackStation RS2423+", "height_u": 2,
         "position": 5, "uid": "1" * 32},
        {"name": "Boden", "category": "Fachboden", "height_u": 1, "position": 1, "uid": "2" * 32},
        {"name": "Box", "category": "Router", "model": "FRITZ!Box 7590 AX", "height_u": 2,
         "rackmount": False, "width_mm": 251, "shelf_id": "2" * 32, "uid": "3" * 32}]}
    new = RackDocument(rack=sample_rack(), created="2026-10-01", saved_at="2026-11-01T10:00:00",
                       history_enabled=True)
    new.add_snapshot(Rack("Vorher", 12).to_dict(), "2026-10-15T08:00:00")
    for data in (old, new.to_dict(), {"name": "Leer", "items": [], "history": []}):
        py = RackDocument.from_dict(copy.deepcopy(data), "2026-05-05")
        out = js({"read": data, "file_date": "2026-05-05"})
        assert norm(out["doc"]) == norm(py.to_dict())
        assert out["notes"] == py.notes


@pytest.mark.parametrize("text", [
    "192.168.1.10", "192.168.001.010/24", "10.0.0.1 255.255.255.0", "10.0.0.1/255.255.0.255",
    "10.0.0.1/33", "fe80::1%eth0", "2001:DB8:0:0:0:0:0:1/64", "1::2::3",
    "300.1.1.1", "abc", "", "  192.168.1.1 / 16 ", "::", "1:2:3:4:5:6:7:8", "1:2:3:4:5:6:7:8:9",
])
def test_ip_rules_match(js, text):
    out = js({"eval": f"[C.ipIsValid({json.dumps(text)}), C.ipKey({json.dumps(text)})]"})
    assert out == [ip_is_valid(text), ip_key(text)]


def test_rack_rules_match(js):
    r = sample_rack()
    expr = """(() => { const r = C.Rack.fromDict(%s);
      return { conflicts: r.conflicts(), used: [r.usedU(), r.usedU("front"), r.usedU("rear")],
        req: r.requiredHeight(), free: [r.findFree(2, "front"), r.findFree(1, "rear"), r.findFree(1.6666666666666667)],
        near: r.nearestFree(6, 3, "", "front"), fd: r.freeDepth(9, 1, "front"),
        dups: [...C.duplicateIps(r)].map(([ip, d]) => [ip, d.map((x) => x.uid)]),
        span: r.span(r.get("%s")), power: r.powerSummary(), ups: r.missingUps() }; })()""" % (
        json.dumps(r.to_dict()), "d" * 32)
    out = js({"eval": expr})
    assert out["conflicts"] == [{"kind": c.kind, "uids": list(c.uids), "pos": c.pos, "span": c.span,
                                 "text": c.text} for c in r.conflicts()]
    assert out["used"] == [r.used_u(), r.used_u(FRONT), r.used_u(REAR)]
    assert out["req"] == r.required_height()
    assert out["free"] == [r.find_free(2, FRONT), r.find_free(1, REAR), r.find_free(5 / 3)]
    assert out["near"] == r.nearest_free(6, 3, side=FRONT)
    assert out["fd"] == r.free_depth(9, 1, FRONT)
    assert out["dups"] == [[ip, [d.uid for d in devs]] for ip, devs in duplicate_ips(r).items()]
    assert out["span"] == r.span(r.get("d" * 32))
    assert out["power"] == r.power_summary()
    assert out["ups"] == r.missing_ups()


def test_builtin_templates_are_shared():
    """Desktop und Web lesen dieselbe Datei rackcore/vorlagen.json."""
    data = json.loads((ROOT / "rackcore" / "vorlagen.json").read_text(encoding="utf-8"))
    assert [d["model"] for d in data["vorlagen"]] == [t.model for t in TEMPLATES]
    assert len({t.model for t in TEMPLATES}) == len(TEMPLATES), "Modellnamen müssen eindeutig sein"
