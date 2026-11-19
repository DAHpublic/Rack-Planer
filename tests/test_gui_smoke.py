"""Rauchtest der Oberfläche (ohne Bildschirm): Fenster bauen, Seiten wechseln, exportieren,
mit Historie speichern. Wird übersprungen, wenn PySide6 nicht installiert ist."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from rackcore import FRONT, REAR, Item, find_template, load_document  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app):
    import rack_resources  # noqa: F401
    from planer2d.mainwindow import MainWindow
    w = MainWindow()
    w.show()
    yield w
    w.dirty = False
    w.close()


def _item(model: str, **kw) -> Item:
    t = find_template(model)
    return Item(name=kw.pop("name", t.model), model=t.model, category=t.category,
                height_u=t.height_u, rackmount=t.rackmount, width_mm=t.width_mm,
                power_w=t.power_w, depth_mm=t.depth_mm, rails=t.rails, **kw)


def test_add_on_both_sides_and_conflict(win):
    win.add_item(_item("Server 2 HE"))
    server = win.rack.items[-1]
    assert server.mount_side == FRONT and server.position == 11
    win.set_side(REAR)
    win.add_item(_item("Steckdosenleiste 19\" (1 HE)"))
    pdu = win.rack.items[-1]
    assert pdu.mount_side == REAR and pdu.position == 12     # hinten von oben befüllt
    assert win.rack.conflicts()                               # Schienen des Servers
    assert win.depth_banner.isVisibleTo(win)


def test_exports(win, tmp_path):
    from planer2d.export import export_pdf, export_png, export_svg
    win.add_item(_item("Switch 24 Port (1 HE)"))
    export_pdf(win.rack, str(tmp_path / "a.pdf"), (FRONT, REAR))
    assert export_png(win.rack, str(tmp_path / "a.png"), REAR)
    export_svg(win.rack, str(tmp_path / "a.svg"), FRONT)
    assert (tmp_path / "a.pdf").read_bytes()[:4] == b"%PDF"
    assert (tmp_path / "a.png").read_bytes()[:4] == b"\x89PNG"
    assert "<svg" in (tmp_path / "a.svg").read_text(encoding="utf-8")


def test_save_with_history(win, tmp_path, app):
    f = tmp_path / "s.rack.json"
    win.add_item(_item("Switch 24 Port (1 HE)", name="Alt"))
    win.path = f
    assert win.save_file()
    assert win.open_path(f)
    asked = []
    win._ask_history = lambda: (asked.append(1), win.enable_history())   # statt Pop-up
    win.rack.items[0].name = "Neu"
    win.mark_dirty()
    app.processEvents()
    assert asked == [1]                                       # Angebot erscheint einmal
    win.mark_dirty()
    app.processEvents()
    assert asked == [1]
    assert win.save_file()
    doc = load_document(f)
    assert doc.history_enabled and len(doc.history) == 1
    assert doc.history[0].rack["items"][0]["name"] == "Alt"
    assert json.loads(f.read_text(encoding="utf-8"))["items"][0]["name"] == "Neu"
    # Tab „Historie“: alten Stand ansehen und wiederherstellen
    win.show_history()
    assert win.hist_list.count() == 2
    win.hist_list.setCurrentRow(1)
    assert win.view.read_only and win.view.rack.items[0].name == "Alt"
    assert win.rack.items[0].name == "Neu"                    # aktueller Stand unverändert
    win.restore_preview()
    assert not win.view.read_only and win.rack.items[0].name == "Alt"
    win.undo()
    assert win.rack.items[0].name == "Neu"


def test_tutorial_runs_through(win, app):
    from planer2d.tutorial import TutorialOverlay
    win.start_tutorial()
    ov = win.findChild(TutorialOverlay)
    assert ov is not None
    for _ in range(len(ov.steps)):
        ov.next()
        app.processEvents()
    assert not ov.isVisible()


def test_non_rack_on_shelf_uses_screw_holes(win):
    """FRITZ!Box (4,8 cm) auf einem Fachboden: Bodenplatte + Gerät → 1⅔ HE statt 3 HE."""
    t = find_template("Fachboden 400 mm (2-Punkt)")
    shelf = win.add_shelf(template=t)
    assert shelf.depth_mm == 400 and win.rack.span(shelf) == 1
    fb = find_template("FRITZ!Box 7590 AX")
    dev = Item(name="FB", model=fb.model, category=fb.category, height_u=fb.height_u,
               rackmount=False, width_mm=fb.width_mm, height_cm=fb.height_cm,
               depth_mm=fb.depth_mm)
    win._place_on_shelf(dev, shelf)
    assert win.rack.span(shelf) == pytest.approx(1 + 2 / 3)
    full = win.add_shelf(template=find_template("Fachboden volle Tiefe (4-Punkt)"))
    assert full.depth_mm == win.rack.depth_mm == 800 and full.rails


def test_single_toolbar(win):
    assert not win.menuBar().actions()                        # keine zweite Menüleiste
    texts = [a.text() for a in win.toolbar.actions() if a.text()]
    assert "PDF …" not in texts and "Bild …" not in texts
    assert win.act_profile.isChecked()
    win.act_profile.trigger()
    assert not win.view.show_profile


def test_pdf_separate_pages(win, tmp_path):
    import re
    from planer2d.export import export_pdf
    win.add_item(_item("Server 2 HE"))
    one, two = tmp_path / "one.pdf", tmp_path / "two.pdf"
    export_pdf(win.rack, str(one), (FRONT, REAR))
    export_pdf(win.rack, str(two), (FRONT, REAR), separate_pages=True)

    def pages(p):
        return len(re.findall(rb"/Type\s*/Page[^s]", p.read_bytes()))
    assert pages(one) == 1 and pages(two) == 2


def test_fields_not_squeezed_in_small_window(win, app):
    win.add_item(_item("Server 2 HE"))
    for _ in range(4):
        win.add_extra_ip()
    win.resize(win.minimumSizeHint())
    app.processEvents()
    assert win.minimumSizeHint().height() < 700                # passt auch auf kleine Bildschirme
    want = win.p_ip.sizeHint().height()
    assert win.p_ip.height() >= want
    assert all(le.height() >= want for _, le in win.p_extra_ips)


def test_license_dialog_shows_all_texts(app):
    from planer2d.licenses import LICENSE_FILES, LicenseDialog, resource_root
    for _title, rel, _md in LICENSE_FILES:
        assert (resource_root() / rel).is_file(), rel
    dlg = LicenseDialog()
    assert dlg.tabs.count() == len(LICENSE_FILES)
    assert "MIT License" in dlg.tabs.widget(0).toPlainText()
    assert "LGPL" in dlg.tabs.widget(1).toPlainText()
    dlg.close()


def test_profile_checkbox_and_title(win, app):
    assert win.windowTitle().endswith("Rack-Planer 2.06 (Desktop-Version)")
    cb = win.cb_profile
    assert cb.isChecked() and win.view.show_profile
    cb.setChecked(False)
    assert not win.act_profile.isChecked() and not win.view.show_profile
    win.act_profile.trigger()
    assert cb.isChecked() and win.view.show_profile
    from planer2d.tutorial import tutorial_steps
    assert any("Häkchen" in s.text and "Seitenansicht" in s.text for s in tutorial_steps(win))
