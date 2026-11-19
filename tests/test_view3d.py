"""Tests der 3D-Ansicht im Desktop-Programm (ohne Bildschirm): 3D-Ansicht zeichnen, Geräte anklicken und
verschieben, Ansichten umschalten, exportieren, Dateien mit dem 2D-Hauptfenster austauschen.
Wird übersprungen, wenn PySide6 nicht installiert ist."""
import json
import math
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest

from rackcore import FRONT, REAR, Item, find_template, load_document


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app):
    import rack_resources  # noqa: F401
    from planer2d.mainwindow3d import MainWindow3D
    w = MainWindow3D()
    w.resize(1400, 900)
    w.show()
    app.processEvents()
    w.show_3d()                     # diese Tests prüfen die 3D-Ansicht
    app.processEvents()
    yield w
    w.dirty = False
    w.close()


def _item(model: str, **kw) -> Item:
    t = find_template(model)
    return Item(name=kw.pop("name", t.model), model=t.model, category=t.category,
                height_u=t.height_u, rackmount=t.rackmount, width_mm=t.width_mm,
                power_w=t.power_w, depth_mm=t.depth_mm, rails=t.rails,
                height_cm=t.height_cm, **kw)


def _screen_point(win, uid: str):
    """Bildschirmpunkt in der Mitte der sichtbaren Front eines Geräts."""
    from planer2d.view3d import Projector
    v = win.view3d
    v.repaint()
    b = next(b for b in v._drawn if b.uid == uid and b.decor or b.uid == uid)
    proj = Projector(v.cam, v.width(), v.height())
    for (axis, sign), poly in b.polys:
        if axis == 2:
            c = poly.boundingRect().center()
            return QPoint(int(c.x()), int(c.y()))
    c = proj.point(b.center)
    return QPoint(int(c.x()), int(c.y()))


def test_starts_in_2d_and_switches_views(app):
    import rack_resources  # noqa: F401
    from planer2d.mainwindow3d import MainWindow3D
    win = MainWindow3D()
    win.show()
    app.processEvents()
    try:
        _check_start_and_switch(win)
    finally:
        win.dirty = False
        win.close()


def _check_start_and_switch(win):
    assert not win.is_3d and win.stack.currentWidget() is win.view
    assert win.act_front.isChecked() and win.cb_profile.isEnabled()
    assert win.windowTitle().endswith("Rack-Planer 2.05 (Desktop-Version)")
    # Leiste: Vorderseite | Rückseite | 3D
    acts = win.toolbar.actions()
    assert acts.index(win.act_front) < acts.index(win.act_rear) < acts.index(win.act_3d)
    win.act_3d.trigger()
    assert win.is_3d and win.stack.currentWidget() is win.view3d
    assert not win.cb_profile.isEnabled()                # Seitenansicht nur in 2D
    win.act_front.trigger()
    assert not win.is_3d and win.stack.currentWidget() is win.view
    win.act_rear.trigger()
    assert win.view.side == REAR and win.stack.currentWidget() is win.view
    win.act_3d.trigger()
    assert win.is_3d and win.stack.currentWidget() is win.view3d
    assert win.view.side == REAR          # neue Geräte weiterhin hinten


def test_render_and_pick(win, app):
    win.add_item(_item("Server 2 HE", name="ESXi"))
    server = win.rack.items[-1]
    win.view3d.preset("front", animate=False)
    pt = _screen_point(win, server.uid)
    assert win.view3d.pick(pt) == server.uid
    QTest.mouseClick(win.view3d, Qt.LeftButton, Qt.NoModifier, pt)
    assert win.view.selected_uid == server.uid
    assert win.p_name.text() == "ESXi"                         # Eigenschaften folgen
    # Klick ins Leere hebt die Auswahl auf
    QTest.mouseClick(win.view3d, Qt.LeftButton, Qt.NoModifier, QPoint(5, win.view3d.height() - 40))
    assert win.view.selected_uid == ""


def test_rotate_and_side_follows_camera(win, app):
    v = win.view3d
    v.preset("front", animate=False)
    assert v.facing_side() == FRONT and win.view.side == FRONT
    v.preset("rear", animate=False)
    assert v.facing_side() == REAR and win.view.side == REAR
    win.add_item(_item("Steckdosenleiste 19\" (1 HE)"))
    assert win.rack.items[-1].mount_side == REAR
    yaw = v.cam.yaw
    QTest.mousePress(v, Qt.LeftButton, Qt.NoModifier, QPoint(20, 300))
    QTest.mouseMove(v, QPoint(120, 320))
    QTest.mouseRelease(v, Qt.LeftButton, Qt.NoModifier, QPoint(120, 320))
    assert v.cam.yaw != pytest.approx(yaw)
    d = v.cam.dist
    v.zoom(1.5)
    assert v.cam.dist < d


def test_drag_device_up_and_down(win, app):
    win.add_item(_item("Switch 24 Port (1 HE)"))
    sw = win.rack.items[-1]
    assert sw.position == 12
    v = win.view3d
    v.preset("front", animate=False)
    pt = _screen_point(win, sw.uid)
    from planer2d.view3d import Projector
    from rackcore import U_MM
    proj = Projector(v.cam, v.width(), v.height())
    # Pixel pro HE in der Montageebene
    a = proj.point((0, 0, win.rack.depth_mm / 2))
    b = proj.point((0, 4 * U_MM, win.rack.depth_mm / 2))
    per_u = (a.y() - b.y()) / 4
    QTest.mousePress(v, Qt.LeftButton, Qt.NoModifier, pt)
    for k in range(1, 6):
        QTest.mouseMove(v, QPoint(pt.x(), int(pt.y() + k * per_u)))
    assert v._ghost is not None
    QTest.mouseRelease(v, Qt.LeftButton, Qt.NoModifier, QPoint(pt.x(), int(pt.y() + 5 * per_u)))
    assert sw.position == 7
    win.undo()
    assert win.rack.get(sw.uid).position == 12


def test_conflicts_marked_in_3d(win, app):
    win.add_item(_item("Server 2 HE"))
    win.set_side(REAR)
    win.add_item(_item("Steckdosenleiste 19\" (1 HE)"))
    assert win.rack.conflicts()
    assert win.view3d.conflict_uids == win.rack.conflict_uids()
    assert win.depth_banner.isVisibleTo(win)
    # „Anzeigen“ im Banner: bleibt in 3D und wählt das Gerät
    uid = next(iter(win.rack.conflict_uids()))
    win.show_item(uid)
    assert win.is_3d and win.view.selected_uid == uid


def test_shelf_and_non_rack_devices(win, app):
    shelf = win.add_shelf(template=find_template("Fachboden 400 mm (2-Punkt)"))
    fb = _item("FRITZ!Box 7590 AX")
    win._place_on_shelf(fb, shelf)
    from planer2d.view3d import build_boxes
    boxes = build_boxes(win.rack)
    fb_box = next(b for b in boxes if b.uid == fb.uid)
    plate = next(b for b in boxes if b.uid == shelf.uid)
    assert fb_box.lo[1] >= plate.hi[1] - 1e-6               # steht auf dem Fachboden
    assert fb_box.hi[2] <= win.rack.depth_mm / 2           # innerhalb des Schranks
    assert fb_box.hi[0] - fb_box.lo[0] == pytest.approx(fb.width_mm * 444 / 450 - 1, abs=1)


def test_rear_devices_mirror_depth(win, app):
    from planer2d.view3d import build_boxes
    win.set_side(REAR)
    win.add_item(_item("Steckdosenleiste 19\" (1 HE)"))
    pdu = win.rack.items[-1]
    boxes = [b for b in build_boxes(win.rack) if b.uid == pdu.uid]
    zmin = min(b.lo[2] for b in boxes)
    zmax = max(b.hi[2] for b in boxes)
    half = win.rack.depth_mm / 2
    assert zmin < -half and zmax == pytest.approx(-half + 50 - 4, abs=1)


def test_painter_order_is_stable(app):
    """Alle Ansichten zeichnen fehlerfrei, und Quader überdecken sich nur in der richtigen
    Reihenfolge (was näher an der Kamera liegt, kommt später)."""
    from planer2d.view3d import Camera, _separates, build_boxes, overlaps, render
    from rackcore import Rack
    rack = Rack(height_u=12)
    for pos, model in ((12, "Switch 24 Port (1 HE)"), (10, "Server 2 HE"), (5, "USV 2 HE")):
        it = _item(model)
        it.position = pos
        rack.items.append(it)
    img = QImage(400, 300, QImage.Format_ARGB32)
    for yaw in range(-180, 180, 45):
        for pitch in (-30, 10, 60):
            cam = Camera()
            cam.target = (0, 260, 0)
            cam.yaw, cam.pitch, cam.dist = math.radians(yaw), math.radians(pitch), 2600
            p = QPainter(img)
            drawn = render(p, cam, build_boxes(rack), 400, 300)
            p.end()
            eye = cam.pos
            index = {id(b): i for i, b in enumerate(drawn)}
            for a in drawn:
                for b in drawn:
                    if a is b or not overlaps(a, b):
                        continue
                    if _separates(a, b, eye) == -1:
                        assert index[id(a)] < index[id(b)]


def test_export_3d_png_and_svg(win, tmp_path):
    win.add_item(_item("Switch 24 Port (1 HE)", ip="192.168.1.2"))
    png, svg = tmp_path / "a.png", tmp_path / "a.svg"
    assert win.write_3d_image(str(png), "png")
    assert win.write_3d_image(str(svg), "svg")
    assert png.read_bytes()[:4] == b"\x89PNG"
    assert "<svg" in svg.read_text(encoding="utf-8")
    img = QImage(str(png))
    assert img.width() >= 1600                               # doppelte Auflösung


def test_files_compatible_with_2d(win, app, tmp_path):
    """Datei aus der 3D-Version öffnet die 2D-Version unverändert und umgekehrt –
    inklusive Tiefe, Montageseite und Historie."""
    from planer2d.mainwindow import MainWindow
    f = tmp_path / "s.rack.json"
    win.add_item(_item("Server 2 HE", name="Alt", ip="10.0.0.1"))
    win.set_side(REAR)
    win.add_item(_item("Steckdosenleiste 19\" (1 HE)"))
    win.path = f
    assert win.save_file()
    assert win.open_path(f)
    win._ask_history = lambda: win.enable_history()
    win.rack.items[0].name = "Neu"
    win.mark_dirty()
    app.processEvents()
    assert win.save_file()
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert saved["format"] == 2 and saved["items"][1]["mount_side"] == REAR

    w2 = MainWindow()
    try:
        assert w2.open_path(f)
        assert w2.rack.to_dict() == win.rack.to_dict()
        assert w2.doc.history_enabled and len(w2.doc.history) == 1
        w2.rack.items[1].depth_mm = 77
        w2.mark_dirty()
        assert w2.save_file()
    finally:
        w2.dirty = False
        w2.close()
    assert win.open_path(f)
    assert win.rack.items[1].depth_mm == 77 and win.rack.items[1].mount_side == REAR
    assert win.view3d.rack is win.rack
    doc = load_document(f)
    assert len(doc.history) == 2


def test_history_preview_in_3d(win, app, tmp_path):
    f = tmp_path / "h.rack.json"
    win.add_item(_item("Switch 24 Port (1 HE)", name="Alt"))
    win.path = f
    assert win.save_file()
    assert win.open_path(f)
    win._ask_history = lambda: win.enable_history()
    win.rack.items[0].name = "Neu"
    win.mark_dirty()
    app.processEvents()
    assert win.save_file()
    win.show_history()
    win.hist_list.setCurrentRow(1)
    assert win.view3d.read_only and win.view3d.rack.items[0].name == "Alt"
    win.hist_list.setCurrentRow(0)
    assert not win.view3d.read_only and win.view3d.rack.items[0].name == "Neu"


def test_tutorial_and_menus(win, app):
    from planer2d.tutorial import TutorialOverlay
    texts = [a.text() for a in win.findChildren(type(win.act_3d))]
    assert "3D-Ansicht als Bild (PNG/SVG) …" in texts
    assert "Infos über Rack-Planer" in texts
    win.show_3d()
    win.start_tutorial()
    assert not win.is_3d                                  # Tutorial beginnt in 2D
    ov = win.findChild(TutorialOverlay)
    assert ov is not None and any("3D" in s.title for s in ov.steps)
    for _ in range(len(ov.steps)):
        ov.next()
        app.processEvents()
    assert not ov.isVisible()


def test_profile_holes_for_every_unit(app):
    """19"-Profile: drei Löcher je HE und Nummern, vorne und hinten, auch ohne Beschriftung."""
    from rackcore import Rack
    from planer2d.view3d import HOLE_OFFSETS, build_boxes
    rack = Rack(height_u=12)
    for labels in (True, False):
        profiles = [b for b in build_boxes(rack, labels=labels)
                    if b.lo[1] == 0 and b.hi[0] - b.lo[0] == 38 and b.decor]
        assert len(profiles) == 4
    assert len(HOLE_OFFSETS) == 3
    assert HOLE_OFFSETS[1] - HOLE_OFFSETS[0] == pytest.approx(15.875)
    img = QImage(300, 600, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    for b in profiles:
        fn = next(iter(b.decor.values()))
        fn(p, 38, rack.height_u * 44.45)
    p.end()


def test_unified_version(win):
    from rackcore.version import APP_VERSION
    import planer2d
    assert APP_VERSION == "2.05" == planer2d.APP_VERSION
    assert planer2d.EDITION == "Desktop-Version"


def test_app_starts_combined_window():
    import planer2d.app as desktop
    from planer2d.mainwindow3d import MainWindow3D
    assert desktop.MainWindow3D is MainWindow3D


def _drag(v, start: QPoint, end: QPoint, steps: int = 8):
    QTest.mousePress(v, Qt.LeftButton, Qt.NoModifier, start)
    for k in range(1, steps + 1):
        QTest.mouseMove(v, QPoint(start.x() + (end.x() - start.x()) * k // steps,
                                  start.y() + (end.y() - start.y()) * k // steps))
    QTest.mouseRelease(v, Qt.LeftButton, Qt.NoModifier, end)


def test_drag_device_to_other_shelf_in_3d(win, app):
    """Kleine Geräte lassen sich in 3D von einem Fachboden auf einen anderen ziehen."""
    from planer2d.view3d import PLATE_H, Projector
    from rackcore import U_MM
    win.show_3d()
    upper = win.add_shelf(template=find_template("Fachboden 400 mm (2-Punkt)"))
    fb = _item("FRITZ!Box 7590 AX")
    win._place_on_shelf(fb, upper)
    lower = win.add_shelf(template=find_template("Fachboden 400 mm (2-Punkt)"))
    lower.position = 3                                    # Platz für das Gerät darüber
    assert upper.position > lower.position and fb.shelf_id == upper.uid
    v = win.view3d
    v.preset("front", animate=False)
    win.refresh()
    start = _screen_point(win, fb.uid)
    proj = Projector(v.cam, v.width(), v.height())
    z = win.rack.depth_mm / 2
    a = proj.point((0, (upper.position - 1) * U_MM + PLATE_H, z))
    b = proj.point((0, (lower.position - 1) * U_MM + PLATE_H, z))
    end = QPoint(start.x() + 40, int(start.y() + (b.y() - a.y())))
    _drag(v, start, end)
    assert fb.shelf_id == lower.uid
    assert fb.offset_mm > 0                               # nach rechts gezogen
    assert fb.mount_side == lower.mount_side
    win.undo()
    assert win.rack.get(fb.uid).shelf_id == upper.uid
    # Ins Leere gezogen: bleibt, wo es ist
    win.refresh()
    start = _screen_point(win, fb.uid)
    _drag(v, start, QPoint(start.x(), 10))
    assert win.rack.get(fb.uid).shelf_id == upper.uid
