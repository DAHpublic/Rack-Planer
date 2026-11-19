"""Hauptfenster der Desktop-Version mit 2D- und 3D-Ansicht.

Erweitert das 2D-Hauptfenster (mainwindow.py): Alle Funktionen (Vorlagen, Eigenschaften,
IP-Adressen, Historie, Export, Rückgängig …) und das Dateiformat bleiben gleich. Dazu kommt
die frei drehbare 3D-Ansicht als dritte Ansicht neben „Vorderseite“ und „Rückseite“ in der
Leiste. Das Programm startet mit der gewohnten 2D-Vorderseite.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont, QImage, QPainter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (
    QFileDialog,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QToolButton,
)

from rackcore import APP_NAME, FORMAT_VERSION, FRONT, SIDE_LABEL, fmt_date
from rackcore.version import version_label

from . import APP_AUTHOR, APP_VERSION, EDITION
from .mainwindow import MainWindow
from .theme import UI_MUTED, UI_TEXT
from .tutorial import Step, TutorialOverlay, tutorial_steps
from .view3d import RackView3D

APP_TITLE = APP_NAME


class MainWindow3D(MainWindow):
    def __init__(self):
        self.view3d: RackView3D | None = None     # vor super(): refresh() wird dort gerufen
        self._first_3d = True
        super().__init__()
        self.view3d = RackView3D(self.rack)
        self.view3d.selectedChanged.connect(self.on_view3d_selected)
        self.view3d.moveRequested.connect(self.on_move_requested)
        self.view3d.shelfMoveRequested.connect(self.move_on_shelf)
        self.view3d.deleteRequested.connect(self.delete_selected)
        self.view3d.sideChanged.connect(self.on_camera_side)

        # 2D-Ansicht und 3D-Ansicht teilen sich den Platz in der Mitte
        self.stack = QStackedWidget()
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.view3d)
        self.banner_host.set_view(self.stack)
        self.stack.currentChanged.connect(self._place_banners)

        self._build_3d_actions()
        self.refresh()
        self.on_selected(self.view.selected_uid)

    # --- Aufbau --------------------------------------------------------------------
    def _build_3d_actions(self):
        self.act_3d = QAction("3D", self)
        self.act_3d.setCheckable(True)
        self.act_3d.setShortcut("Ctrl+3")
        self.act_3d.setToolTip("Frei drehbare 3D-Ansicht (Strg + 3)")
        self.act_3d.triggered.connect(self.show_3d)
        self.addAction(self.act_3d)
        self.act_front.actionGroup().addAction(self.act_3d)
        # Reihenfolge in der Leiste: Vorderseite | Rückseite | 3D | ☑ Seitenansicht
        self.toolbar.insertAction(self._action_after(self.act_rear), self.act_3d)

        # „Ansicht“-Menü: Zoomen und Anpassen wirken auf die gerade sichtbare Ansicht
        for a in self.findChildren(QAction):
            slot = {"Vergrößern": lambda: self._zoom(1.2),
                    "Verkleinern": lambda: self._zoom(1 / 1.2),
                    "Anpassen": self._fit}.get(a.text())
            if a.text() == "Infos über Rack-Planer":
                slot = self.show_about
            if slot is not None:
                a.triggered.disconnect()
                a.triggered.connect(slot)

        # Export: zusätzlich die 3D-Ansicht als Bild
        btn = self.toolbar.widgetForAction(self.act_export)
        menu: QMenu | None = btn.menu() if isinstance(btn, QToolButton) else None
        self.act_export_3d = QAction("3D-Ansicht als Bild (PNG/SVG) …", self)
        self.act_export_3d.setShortcut("Ctrl+Shift+E")
        self.act_export_3d.triggered.connect(self.export_3d_image)
        self.addAction(self.act_export_3d)
        if menu is not None:
            menu.addSeparator()
            menu.addAction(self.act_export_3d)

    def _place_banners(self, *_):
        """In 3D liegen die Banner unter Werkzeugleiste und Titel der 3D-Ansicht."""
        self.banner_host.set_top(self.view3d.banner_top() if self.is_3d else 10)

    def _action_after(self, action: QAction) -> QAction | None:
        acts = self.toolbar.actions()
        i = acts.index(action)
        return acts[i + 1] if i + 1 < len(acts) else None

    @property
    def is_3d(self) -> bool:
        act = getattr(self, "act_3d", None)
        return act is not None and act.isChecked()

    def _zoom(self, factor: float):
        (self.view3d if self.is_3d else self.view).zoom(factor)

    def _fit(self):
        if self.is_3d:
            self.view3d.fit()
        else:
            self.view.fit()

    # --- Ansicht umschalten -------------------------------------------------------
    def show_3d(self):
        self.act_3d.setChecked(True)
        self.stack.setCurrentWidget(self.view3d)
        self.cb_profile.setEnabled(False)       # Seitenansicht gibt es nur in 2D
        self.refresh()
        if self._first_3d:                      # beim ersten Mal: Blick auf die aktuelle Seite
            self._first_3d = False
            self.view3d.fit(animate=False)
            if self.view3d.facing_side() != self.view.side:
                self.view3d.preset("front" if self.view.side == FRONT else "rear",
                                   animate=False)
        self.view3d.setFocus()

    def set_side(self, side: str):
        """Vorder- oder Rückseite: in 2D die Seite anzeigen, in 3D die Kamera drehen.
        Neue Geräte werden auf dieser Seite montiert."""
        if self.view3d is None or not self.is_3d:
            super().set_side(side)
            if self.view3d is not None:
                self.stack.setCurrentWidget(self.view)
                self.cb_profile.setEnabled(True)
            return
        self.view.side = side
        self.view3d.show_side(side)
        self.refresh()
        self.on_selected(self.view.selected_uid)

    def on_camera_side(self, side: str):
        """Die Kamera schaut jetzt auf die andere Seite: neue Geräte kommen dorthin."""
        if self.is_3d and side != self.view.side:
            self.view.side = side
            self.refresh()
            self.statusBar().showMessage(
                f"Blick auf die {SIDE_LABEL[side]} – neue Geräte werden "
                f"{'vorne' if side == FRONT else 'hinten'} montiert.", 4000)

    def show_item(self, uid: str):
        if not self.is_3d:
            super().show_item(uid)
            return
        if self.rack.get(uid) is None:
            return
        self.view.selected_uid = uid
        self.refresh()
        self.on_selected(uid)
        self.view3d.focus_item(uid)

    def on_view3d_selected(self, uid: str):
        self.view.selected_uid = uid
        self.refresh()
        self.on_selected(uid)

    # --- Abgleich mit der 2D-Logik --------------------------------------------------
    def refresh(self, rebuild_scene: bool = True):
        super().refresh(rebuild_scene)
        self._sync_3d()

    def _sync_3d(self):
        v = self.view3d
        if v is None:
            return
        v.rack = self.view.rack
        v.selected_uid = self.view.selected_uid
        v.read_only = self.view.read_only
        v.fine = self.view.fine
        v.conflict_uids = {u for c in self.view.rack.conflicts() for u in c.uids}
        v.refresh()
        self._place_banners()

    def on_selected(self, uid: str):
        super().on_selected(uid)
        if self.view3d is not None and self.view3d.selected_uid != self.view.selected_uid:
            self._sync_3d()

    def _start_preview(self, snap):
        super()._start_preview(snap)
        self._sync_3d()

    def _end_preview(self, refresh: bool = True):
        super()._end_preview(refresh)
        self._sync_3d()

    def _show_rack(self, rack, select_uid: str, fit: bool):
        old_h = self.view3d.rack.height_u if self.view3d is not None else None
        super()._show_rack(rack, select_uid, fit)
        if self.view3d is not None and (fit or old_h != rack.height_u):
            self.view3d.fit(animate=False)

    def update_title(self):
        name = self.path.name if self.path else "Unbenannt"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} – {version_label(EDITION)}")

    def showEvent(self, e):
        super().showEvent(e)
        if self.view3d is not None and self.is_3d:
            self.view3d.fit(animate=False)

    # --- Export der 3D-Ansicht ---------------------------------------------------------
    def export_3d_image(self):
        fn, filt = QFileDialog.getSaveFileName(
            self, "3D-Ansicht als Bild exportieren",
            self._dialog_dir(f"{self._base_name()} 3D.png"),
            "PNG-Bild (*.png);;SVG-Grafik (*.svg)")
        if not fn:
            return
        fmt = "svg" if fn.lower().endswith(".svg") or filt.startswith("SVG") else "png"
        if not fn.lower().endswith(f".{fmt}"):
            fn += f".{fmt}"
        try:
            if not self.write_3d_image(fn, fmt):
                raise OSError("Die Datei konnte nicht geschrieben werden.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, APP_TITLE, f"Bildexport fehlgeschlagen:\n{e}")
            return
        self._last_dir = str(Path(fn).parent)
        self.statusBar().showMessage(f"Bild exportiert: {fn}", 5000)

    def write_3d_image(self, fn: str, fmt: str = "png", scale: int = 2) -> bool:
        """3D-Ansicht mit der aktuellen Kamera, Titel und Stand als PNG oder SVG."""
        w = max(800, self.view3d.width())
        h = max(600, self.view3d.height())
        if fmt == "svg":
            gen = QSvgGenerator()
            gen.setFileName(fn)
            gen.setSize(QSize(w, h))
            gen.setViewBox(QRect(0, 0, w, h))
            gen.setTitle(self.rack.name)
            gen.setDescription(version_label(EDITION))
            p = QPainter(gen)
            self._paint_export(p, w, h)
            p.end()
            return Path(fn).exists()
        img = QImage(w * scale, h * scale, QImage.Format_ARGB32)
        img.fill(QColor("#202124"))
        p = QPainter(img)
        p.scale(scale, scale)
        self._paint_export(p, w, h)
        p.end()
        return img.save(fn, "PNG")

    def _paint_export(self, p: QPainter, w: int, h: int):
        self.view3d.render_image(p, w, h)
        f = QFont()
        f.setPixelSize(22)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(UI_TEXT))
        p.drawText(QRectF(20, 14, w - 40, 30), Qt.AlignLeft | Qt.AlignVCenter, self.rack.name)
        f.setPixelSize(14)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(UI_MUTED))
        p.drawText(QRectF(20, 44, w - 40, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   f"Stand: {fmt_date(self.rack.as_of)}   ·   {self.rack.power_summary()}")

    # --- Hilfe -------------------------------------------------------------------
    def start_tutorial(self):
        if self.findChild(TutorialOverlay):
            return
        if self.is_3d:                         # Tutorial beginnt in der 2D-Ansicht
            (self.act_front if self.view.side == FRONT else self.act_rear).setChecked(True)
            self.set_side(self.view.side)

        def action_3d_rect():
            btn = self.toolbar.widgetForAction(self.act_3d)
            if btn is None or not btn.isVisible():
                return None
            return QRect(btn.mapTo(self, QPoint(0, 0)), btn.size()).adjusted(-4, -4, 4, 4)

        steps = tutorial_steps(self)
        i = next(k for k, s in enumerate(steps) if s.title.startswith("Seitenansicht ein"))
        steps.insert(i + 1, Step(
            "Die 3D-Ansicht 🧊",
            "Mit <b>3D</b> in der Leiste (<b>Strg + 3</b>) siehst du deinen Schrank räumlich; "
            "<b>Vorderseite</b> und <b>Rückseite</b> bringen dich zurück zu den 2D-Ansichten. "
            "In 3D dreht die <b>linke Maustaste</b>, auf einem Gerät verschiebt sie es nach oben "
            "oder unten. Geräte auf einem Fachboden ziehst du so auf einen anderen Fachboden. "
            "<b>Mausrad</b> zoomt, <b>mittlere Maustaste</b> oder <b>Umschalt</b> verschiebt "
            "die Ansicht, <b>Doppelklick</b> holt ein Gerät heran.",
            action_3d_rect))
        TutorialOverlay(self, steps).start()

    def show_about(self):
        QMessageBox.about(
            self, f"Infos über {APP_TITLE}",
            f"<h3 style='margin-bottom:2px'>Rack-Planer {APP_VERSION}</h3>"
            f"<p style='margin-top:0'><b>{EDITION}</b> · Dateiformat {FORMAT_VERSION}<br>"
            f"Entwickler: {APP_AUTHOR}</p>"
            "<p>Serverschränke planen: Höheneinheiten, Vorder- und Rückseite in 2D, frei "
            "drehbare 3D-Ansicht, Einbautiefe, Geräte, Fachböden, Beschriftung mit "
            "IP-Adressen, Leistung und Wärmelast, Export als PDF, PNG und SVG, Historie "
            "früherer Stände. Gleiche Projektdateien (*.rack.json) wie die Webversion.</p>"
            "<p>Portabel: Das Programm legt keine Einstellungen oder Hilfsdateien an.</p>"
            "<p>Freie Software unter der MIT-Lizenz. Verwendet Qt 6 und PySide6 (GNU LGPL v3); "
            "Details unter <b>Hilfe → Lizenzen</b> und <b>Hilfe → Über Qt</b>.</p>"
            "<p>Kurze Einführung: <b>Hilfe → Tutorial</b> (F1).</p>")
