"""Hauptfenster der Desktop-Version."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPushButton, QTabWidget, QListWidget, QListWidgetItem, QSpinBox, QSplitter, QToolButton, QTreeWidget, QTreeWidgetItem,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from rackcore import (
    APP_NAME, CAT_SHELF, CAT_USV, CATEGORIES, CATEGORY_COLORS, DEPTH_PRESETS, EPS, FILE_SUFFIX,
    FRONT, MAX_IPS, REAR, SHELF_DEPTH_MM, SHELF_WIDTH_MM, SIDE_LABEL, SIDE_SHORT, SIDES,
    TEMPLATES, U_MM, Item, Rack, RackDocument, Template, duplicate_ips, fmt_date, fmt_u, ip_is_valid, ip_key, load_document, now_iso, other_side, save_document, snap_third,
    template_matches, today_iso, units_for_cm,
)

from rackcore.version import version_label

from . import EDITION
from .banners import (
    BannerHost, DepthBanner, InfoBanner, PreviewBanner, RailBanner, WarnBanner,
)
from .dialogs import DeviceDialog, ExportDialog
from .export import export_pdf, export_png, export_svg
from .licenses import show_licenses
from .scene import RackView
from .theme import CONFLICT_RED, IP_BAD_CSS, IP_DUP_CSS, UI_ACCENT, UI_MUTED, UNDO_LIMIT
from .tutorial import TutorialOverlay, show_about, tutorial_steps

FILE_FILTER = "Rack-Planer-Projekt (*.rack.json *.json)"


class _PropsScroll(QScrollArea):
    """Hält das Eigenschaften-Feld in seiner natürlichen Größe. Ist das Fenster zu
    niedrig (kleiner Bildschirm, Skalierung, viele IP-Adressen), wird gescrollt,
    statt die Eingabefelder zusammenzudrücken."""

    def __init__(self, inner: QWidget):
        super().__init__()
        self.setWidget(inner)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    def _extra_w(self) -> int:
        return self.verticalScrollBar().sizeHint().width() + 2

    def sizeHint(self) -> QSize:
        h = self.widget().sizeHint()
        return QSize(h.width() + self._extra_w(), h.height())

    def minimumSizeHint(self) -> QSize:
        m = self.widget().minimumSizeHint()
        return QSize(m.width() + self._extra_w(), min(m.height(), 140))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.doc = RackDocument()
        self.rack = self.doc.rack
        self.path: Path | None = None
        self.dirty = False
        self._loading = False
        self._last_dir = ""          # zuletzt benutzter Ordner (nur während der Sitzung)
        # Rückgängig/Wiederholen: Zustände des Schranks als JSON-Text
        self._undo: list[str] = []
        self._redo: list[str] = []
        self._state = ""             # aktueller Zustand
        self._saved_state = ""       # zuletzt gespeicherter Zustand
        self._merge_key = ""         # Tippen im selben Feld = ein Rückgängig-Schritt
        self._dups: dict[str, list[Item]] = {}
        self._file_state = ""        # Zustand des Schranks wie in der Datei gespeichert
        self._history_offered = False
        self._conflict_uids: set[str] = set()
        self._hint_shown = False

        self.view = RackView(self.rack)
        self.view.selectedChanged.connect(self.on_selected)
        self.view.moveRequested.connect(self.on_move_requested)
        self.view.shelfMoveRequested.connect(self.move_on_shelf)
        self.view.deleteRequested.connect(self.delete_selected)
        self.view.sideSwitchRequested.connect(self.show_item)

        self.banner = InfoBanner()
        self.banner.addUpsRequested.connect(self.add_ups)

        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(6, 6, 6, 6)
        self.preview_banner = PreviewBanner()
        self.preview_banner.restoreRequested.connect(self.restore_preview)
        self.preview_banner.closeRequested.connect(lambda: self.hist_list.setCurrentRow(0))
        self._preview: dict | None = None     # angezeigter früherer Stand (nur ansehen)
        self.depth_banner = DepthBanner()
        self.depth_banner.showRequested.connect(self.show_item)
        self.rail_banner = RailBanner()
        self.dup_banner = WarnBanner()
        # Banner schweben über der Ansicht und verschieben sie nicht
        self.banner_host = BannerHost(self.view, [
            self.preview_banner, self.depth_banner, self.dup_banner, self.banner,
            self.rail_banner])
        cl.addWidget(self.banner_host, 1)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)        # Seitenleisten nie auf 0 zusammenschieben
        self.left_panel = self._build_left()
        splitter.addWidget(self.left_panel)
        splitter.addWidget(center)
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 640, 360])
        self.setCentralWidget(splitter)

        self._build_actions()
        self.status = QLabel()
        self.statusBar().addPermanentWidget(self.status)
        self.resize(1360, 900)
        self.load_document(self.doc)

    # --- Aufbau ------------------------------------------------------------
    def _build_left(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 0, 6)

        g = QGroupBox("Schrank")
        self.rack_box = g
        f = QFormLayout(g)
        self.rack_name = QLineEdit()
        self.rack_name.textEdited.connect(self.on_rack_name)
        self.rack_height = QSpinBox()
        self.rack_height.setRange(1, 60)
        self.rack_height.setSuffix(" HE")
        self.rack_height.setKeyboardTracking(False)
        self.rack_height.valueChanged.connect(self.on_rack_height)
        f.addRow("Bezeichnung:", self.rack_name)
        f.addRow("Höhe:", self.rack_height)
        presets = QHBoxLayout()
        for n in (6, 9, 12, 15, 22, 42, 47):
            b = QPushButton(str(n))
            b.setFixedWidth(34)
            b.setToolTip(f"{n} HE")
            b.clicked.connect(lambda _=False, n=n: self.rack_height.setValue(n))
            presets.addWidget(b)
        presets.addStretch()
        f.addRow("Standard:", presets)
        self.rack_depth = QSpinBox()
        self.rack_depth.setRange(100, 2000)
        self.rack_depth.setSingleStep(50)
        self.rack_depth.setSuffix(" mm")
        self.rack_depth.setKeyboardTracking(False)
        self.rack_depth.setToolTip(
            "Nutzbare Einbautiefe von der vorderen Montageebene bis zur Rückseite.\n"
            "Geräte vorne und hinten teilen sich diese Tiefe: 800 mm Schrank mit einer\n"
            "50 mm tiefen Steckdosenleiste hinten lässt vorne noch 750 mm frei.")
        self.rack_depth.valueChanged.connect(self.on_rack_depth)
        f.addRow("Tiefe:", self.rack_depth)
        dpresets = QHBoxLayout()
        for n in DEPTH_PRESETS:
            b = QPushButton(f"{n // 10}")
            b.setFixedWidth(38)
            b.setToolTip(f"{n} mm")
            b.clicked.connect(lambda _=False, n=n: self.rack_depth.setValue(n))
            dpresets.addWidget(b)
        dpresets.addStretch()
        f.addRow("Tiefe (cm):", dpresets)
        asof = QHBoxLayout()
        self.rack_asof = QDateEdit()
        self.rack_asof.setCalendarPopup(True)
        self.rack_asof.setDisplayFormat("dd.MM.yyyy")
        self.rack_asof.setToolTip("Aktueller Stand der Planung – erscheint auf Exporten unter "
                                  "dem Titel. Neue Dateien: Erstellungsdatum.")
        self.rack_asof.dateChanged.connect(self.on_as_of)
        today = QPushButton("Heute")
        today.clicked.connect(lambda: self.rack_asof.setDate(QDate.currentDate()))
        asof.addWidget(self.rack_asof, 1)
        asof.addWidget(today)
        f.addRow("Stand:", asof)
        self.fine_grid = QCheckBox("Feinraster ⅓ HE (jedes Schraubenloch)")
        self.fine_grid.setToolTip("Geräte lassen sich in Schritten von ⅓ HE verschieben")
        self.fine_grid.toggled.connect(self.on_fine_grid)
        f.addRow("", self.fine_grid)
        lay.addWidget(g)

        g = QGroupBox("Vorlagen")
        self.tpl_box = g
        v = QVBoxLayout(g)
        self.tpl_search = QLineEdit()
        self.tpl_search.setPlaceholderText("Suchen, z. B. 7590, LWL, Switch …")
        self.tpl_search.setClearButtonEnabled(True)
        self.tpl_search.setToolTip("Filtert die Vorlagen. Enter fügt die markierte Vorlage hinzu.")
        self.tpl_search.textChanged.connect(self.filter_templates)
        self.tpl_search.returnPressed.connect(lambda: self.add_from_tree(self.tree.currentItem()))
        v.addWidget(self.tpl_search)
        self.tpl_none = QLabel("Keine passende Vorlage gefunden.")
        self.tpl_none.setStyleSheet(f"color:{UI_MUTED};")
        self.tpl_none.hide()
        v.addWidget(self.tpl_none)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Gerät", "HE"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setRootIsDecorated(True)
        groups: dict[str, QTreeWidgetItem] = {}
        for t in TEMPLATES:
            parent = groups.get(t.group)
            if parent is None:
                parent = QTreeWidgetItem(self.tree, [t.group])
                parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
                f2 = parent.font(0)
                f2.setBold(True)
                parent.setFont(0, f2)
                groups[t.group] = parent
            ti = QTreeWidgetItem(parent, [t.model, str(t.height_u)])
            ti.setData(0, Qt.UserRole, t)
            tip = f"{t.category} · {t.height_u} HE"
            if t.height_cm:
                tip += f" (Höhe {t.height_cm:g} cm)"
            tip += " · Rackmontage" if t.rackmount else " · nicht rackfähig (Fachboden)"
            if t.note:
                tip += f"\nMaße (B × T × H): {t.note}"
            if t.power_w:
                tip += f"\nca. {t.power_w:g} W"
            if t.depth_mm:
                tip += f"\nTiefe {t.depth_mm} mm"
            if t.rails:
                tip += " · auf Einbauschienen (blockiert die Gegenseite)"
            ti.setToolTip(0, tip)
            if not t.rackmount:
                ti.setForeground(0, QColor(UI_ACCENT))
                ti.setForeground(1, QColor(UI_ACCENT))
        self.tree.expandAll()
        self.tree.itemDoubleClicked.connect(lambda it, _c: self.add_from_tree(it))
        v.addWidget(self.tree)
        b = QPushButton("Vorlage hinzufügen")
        b.clicked.connect(lambda: self.add_from_tree(self.tree.currentItem()))
        v.addWidget(b)
        row = QHBoxLayout()
        b1 = QPushButton("Eigenes Gerät …")
        b1.clicked.connect(self.add_custom)
        b2 = QPushButton("Fachboden")
        b2.clicked.connect(lambda: self.add_shelf())
        row.addWidget(b1)
        row.addWidget(b2)
        v.addLayout(row)
        legend = QLabel(f"<span style='color:{UI_ACCENT}'>Orange</span> = nicht rackfähig, "
                        "wird auf einen Fachboden gestellt und lässt sich dort frei "
                        "per Drag & Drop verschieben")
        legend.setWordWrap(True)
        legend.setStyleSheet(f"color:{UI_MUTED}; font-size: 8pt;")
        v.addWidget(legend)
        lay.addWidget(g, 1)
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 6, 6)

        self.tabs = QTabWidget()
        self.list_box = self.tabs
        g = QWidget()
        v = QVBoxLayout(g)
        v.setContentsMargins(4, 6, 4, 4)
        self.list = QTreeWidget()
        self.list.setHeaderLabels(["Gerät", "HE", "Seite", "IP-Adresse", "W"])
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setItemsExpandable(False)
        self.list.setIndentation(14)
        self.list.setUniformRowHeights(True)
        self.list.setTextElideMode(Qt.ElideRight)
        hdr = self.list.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setMinimumSectionSize(28)
        self.list.headerItem().setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
        self.list.currentItemChanged.connect(self.on_list_selection)
        v.addWidget(self.list)
        self.tabs.addTab(g, "Geräte im Schrank")
        self.tabs.addTab(self._build_history_tab(), "Historie")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        lay.addWidget(self.tabs, 1)

        g = QGroupBox("Eigenschaften")
        self.props = g
        f = QFormLayout(g)
        self.p_name = QLineEdit()
        self.p_name.textEdited.connect(lambda t: self.set_prop("name", t, merge="name"))
        self.p_ip = QLineEdit()
        self.p_ip.setPlaceholderText("z. B. 192.168.178.1")
        self.p_ip.textEdited.connect(self.on_ip_edited)
        self.ip_box = QWidget()
        ipl = QVBoxLayout(self.ip_box)
        ipl.setContentsMargins(0, 0, 0, 0)
        ipl.setSpacing(4)
        ipl.addWidget(self.p_ip)
        self.p_extra_ips: list[tuple[QWidget, QLineEdit]] = []
        for i in range(MAX_IPS - 1):
            roww = QWidget()
            rl = QHBoxLayout(roww)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            le = QLineEdit()
            le.setPlaceholderText(f"{i + 2}. IP-Adresse")
            le.textEdited.connect(lambda t, i=i: self.on_extra_ip_edited(i, t))
            rm = QToolButton()
            rm.setText("✕")
            rm.setToolTip("Diese IP-Adresse entfernen")
            rm.clicked.connect(lambda _c=False, i=i: self.remove_extra_ip(i))
            rl.addWidget(le, 1)
            rl.addWidget(rm)
            roww.setVisible(False)
            ipl.addWidget(roww)
            self.p_extra_ips.append((roww, le))
        self.p_add_ip = QPushButton("+ Weitere IP-Adresse")
        self.p_add_ip.clicked.connect(self.add_extra_ip)
        ipl.addWidget(self.p_add_ip)
        self.p_model = QLabel()
        self.p_cat = QComboBox()
        self.p_cat.addItems(CATEGORIES)
        self.p_cat.activated.connect(lambda _i: self.set_prop("category", self.p_cat.currentText()))
        self.p_height = QSpinBox()
        self.p_height.setRange(1, 60)
        self.p_height.setSuffix(" HE")
        self.p_height.setKeyboardTracking(False)
        self.p_height.valueChanged.connect(self.on_height)
        self.p_height_cm = QDoubleSpinBox()
        self.p_height_cm.setRange(0.5, 250)
        self.p_height_cm.setDecimals(1)
        self.p_height_cm.setSingleStep(0.5)
        self.p_height_cm.setSuffix(" cm")
        self.p_height_cm.setKeyboardTracking(False)
        self.p_height_cm.valueChanged.connect(self.on_height_cm)
        self.p_offset = QSpinBox()
        self.p_offset.setRange(0, SHELF_WIDTH_MM)
        self.p_offset.setSingleStep(5)
        self.p_offset.setSuffix(" mm von links")
        self.p_offset.setKeyboardTracking(False)
        self.p_offset.valueChanged.connect(self.on_offset)
        self.p_pos = QDoubleSpinBox()
        self.p_pos.setDecimals(2)
        self.p_pos.setRange(1, 60)
        self.p_pos.setPrefix("ab HE ")
        self.p_pos.setKeyboardTracking(False)
        self.p_pos.valueChanged.connect(self.on_pos)
        self.p_width = QSpinBox()
        self.p_width.setRange(20, SHELF_WIDTH_MM)
        self.p_width.setSuffix(" mm")
        self.p_width.setKeyboardTracking(False)
        self.p_width.valueChanged.connect(self.on_width)
        self.p_power = QDoubleSpinBox()
        self.p_power.setRange(0, 10000)
        self.p_power.setDecimals(0)
        self.p_power.setSuffix(" W")
        self.p_power.setKeyboardTracking(False)
        self.p_power.valueChanged.connect(
            lambda v: self.set_prop("power_w", v, rebuild=False, merge="power"))
        self.p_mount = QLabel()
        self.p_mount.setWordWrap(True)
        self.p_side = QComboBox()
        for sd in SIDES:
            self.p_side.addItem(f"{SIDE_LABEL[sd]}", sd)
        self.p_side.setToolTip("Seite, an der das Gerät montiert ist. Von dort aus belegt es "
                               "seine Tiefe.")
        self.p_side.activated.connect(lambda _i: self.on_side(self.p_side.currentData()))
        self.p_depth = QSpinBox()
        self.p_depth.setRange(0, 2000)
        self.p_depth.setSingleStep(10)
        self.p_depth.setSuffix(" mm")
        self.p_depth.setSpecialValueText("unbekannt")
        self.p_depth.setKeyboardTracking(False)
        self.p_depth.valueChanged.connect(
            lambda v: self.set_prop("depth_mm", int(v), merge="depth"))
        self.p_rails = QCheckBox("Auf Einbauschienen")
        self.p_rails.setToolTip("Schienen werden vorne und hinten am Rahmen befestigt und "
                                "blockieren\ndiese HE auf der Gegenseite (typisch für USV, "
                                "Server, Rack-NAS).")
        self.p_rails.toggled.connect(lambda c: self.set_prop("rails", c))
        self.p_depth_info = QLabel()
        self.p_depth_info.setWordWrap(True)
        f.addRow("Gerätename:", self.p_name)
        self.p_show_name = QCheckBox("Namen in der Grafik anzeigen")
        self.p_show_name.toggled.connect(lambda c: self.set_prop("show_name", c))
        f.addRow("", self.p_show_name)
        f.addRow("IP-Adresse(n):", self.ip_box)
        f.addRow("Modell:", self.p_model)
        f.addRow("Kategorie:", self.p_cat)
        f.addRow("Höhe:", self.p_height)
        f.addRow("Höhe (cm):", self.p_height_cm)
        f.addRow("Position:", self.p_pos)
        f.addRow("Breite:", self.p_width)
        f.addRow("Auf Fachboden:", self.p_offset)
        f.addRow("Leistung:", self.p_power)
        f.addRow("Montage:", self.p_side)
        f.addRow("Tiefe:", self.p_depth)
        f.addRow("", self.p_rails)
        f.addRow("", self.p_depth_info)
        f.addRow("Einbau:", self.p_mount)
        self.p_shelf_btn = QPushButton("Auf Fachboden stellen")
        self.p_shelf_btn.clicked.connect(self.put_selected_on_shelf)
        f.addRow(self.p_shelf_btn)
        row = QHBoxLayout()
        up = QPushButton("▲ Hoch")
        up.clicked.connect(lambda: self.nudge(1))
        down = QPushButton("▼ Runter")
        down.clicked.connect(lambda: self.nudge(-1))
        dele = QPushButton("Entfernen")
        dele.clicked.connect(self.delete_selected)
        row.addWidget(up)
        row.addWidget(down)
        row.addWidget(dele)
        f.addRow(row)
        lay.addWidget(_PropsScroll(g))
        return w

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        self.hist_tab = w
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 6, 4, 4)
        self.hist_on = QCheckBox("Historie für diese Datei führen")
        self.hist_on.setToolTip("Beim Speichern bleibt der bisherige Stand in derselben Datei "
                                "erhalten.")
        self.hist_on.toggled.connect(self.on_history_toggled)
        v.addWidget(self.hist_on)
        self.hist_info = QLabel()
        self.hist_info.setWordWrap(True)
        self.hist_info.setStyleSheet(f"color:{UI_MUTED};")
        v.addWidget(self.hist_info)
        self.hist_list = QListWidget()
        self.hist_list.currentRowChanged.connect(self.on_history_row)
        v.addWidget(self.hist_list, 1)
        row = QHBoxLayout()
        self.hist_restore = QPushButton("Wiederherstellen")
        self.hist_restore.setToolTip("Diesen Stand als aktuellen Stand übernehmen "
                                     "(Strg + Z macht es rückgängig)")
        self.hist_restore.clicked.connect(self.restore_preview)
        self.hist_copy = QPushButton("Als eigene Datei …")
        self.hist_copy.setToolTip("Diesen Stand als eigene Projektdatei speichern")
        self.hist_copy.clicked.connect(self.save_preview_copy)
        row.addWidget(self.hist_restore)
        row.addWidget(self.hist_copy)
        v.addLayout(row)
        return w

    def _build_actions(self):
        """Eine einzige Leiste: Datei, Export, Bearbeiten, Seiten und Menüs für Ansicht/Hilfe.
        Alle Tastenkürzel hängen am Fenster und funktionieren daher auch aus den Menüs."""
        tb = self.addToolBar("Werkzeuge")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.toolbar = tb

        def act(text, slot, shortcut=None, tip="", checkable=False):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            if tip:
                a.setToolTip(tip)
            a.setCheckable(checkable)
            a.triggered.connect(slot)
            self.addAction(a)
            return a

        def menu_button(text: str, actions, default=None, tip: str = "") -> QAction:
            btn = QToolButton()
            menu = QMenu(btn)
            for a in actions:
                if a is None:
                    menu.addSeparator()
                else:
                    menu.addAction(a)
            btn.setMenu(menu)
            if default is not None:
                btn.setDefaultAction(default)
                btn.setPopupMode(QToolButton.MenuButtonPopup)
            else:
                btn.setText(text)
                btn.setPopupMode(QToolButton.InstantPopup)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            if tip:
                btn.setToolTip(tip)
            return tb.addWidget(btn)

        tb.addAction(act("Neu", self.new_file, QKeySequence.New, "Neuer Schrank (Strg + N)"))
        tb.addAction(act("Öffnen …", self.open_file, QKeySequence.Open, "Projekt öffnen (Strg + O)"))
        save = act("Speichern", self.save_file, QKeySequence.Save, "Speichern (Strg + S)")
        save_as = act("Speichern unter …", self.save_file_as, QKeySequence.SaveAs)
        self.act_save = menu_button("Speichern", [save, save_as], default=save)
        tb.addSeparator()
        pdf = act("als PDF …", self.export_pdf, "Ctrl+P",
                  "Vorder- und/oder Rückseite als PDF (Strg + P)")
        img = act("als Bild (PNG/SVG) …", self.export_image, "Ctrl+E",
                  "Eine Seite als PNG oder SVG (Strg + E)")
        self.act_export = menu_button("Exportieren", [pdf, img],
                                      tip="Als PDF oder Bild exportieren")
        tb.addSeparator()
        self.act_undo = act("Rückgängig", self.undo, QKeySequence.Undo, "Rückgängig (Strg + Z)")
        self.act_redo = act("Wiederholen", self.redo, QKeySequence.Redo, "Wiederholen (Strg + Y)")
        self.act_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        grp = QActionGroup(self)
        self.act_front = act("Vorderseite", lambda: self.set_side(FRONT),
                             tip="Vorderseite anzeigen (Strg + R wechselt)", checkable=True)
        self.act_rear = act("Rückseite", lambda: self.set_side(REAR),
                            tip="Rückseite anzeigen (Strg + R wechselt)", checkable=True)
        for a in (self.act_front, self.act_rear):
            grp.addAction(a)
            tb.addAction(a)
        self.act_front.setChecked(True)
        self.act_profile = act("Seitenansicht", self.on_view_options,
                               tip="Seitenansicht mit der Tiefe ein-/ausblenden",
                               checkable=True)
        self.act_profile.setChecked(True)
        # Häkchen in der Leiste (gleichbedeutend mit „Ansicht → Seitenansicht“)
        self.cb_profile = QCheckBox("Seitenansicht")
        self.cb_profile.setChecked(True)
        self.cb_profile.setToolTip("Seitenansicht mit der Tiefe rechts neben dem Schrank "
                                   "ein-/ausblenden")
        self.cb_profile.setStyleSheet("QCheckBox { margin: 0 6px; }")
        self.cb_profile.toggled.connect(
            lambda on: on != self.act_profile.isChecked() and self.act_profile.trigger())
        self.act_profile.toggled.connect(self.cb_profile.setChecked)
        tb.addWidget(self.cb_profile)
        tb.addSeparator()
        flip = act("Seite wechseln", lambda: self.set_side(other_side(self.view.side)), "Ctrl+R")
        self.act_other = act("Gegenseite andeuten", self.on_view_options, checkable=True)
        self.act_other.setChecked(True)
        menu_button("Ansicht", [
            flip, self.act_other, self.act_profile, None,
            act("Vergrößern", lambda: self.view.zoom(1.2), QKeySequence.ZoomIn),
            act("Verkleinern", lambda: self.view.zoom(1 / 1.2), QKeySequence.ZoomOut),
            act("Anpassen", self.view.fit, "Ctrl+0"), None,
            act("Vorlage suchen", self._focus_search, QKeySequence.Find),
            act("Historie anzeigen", self.show_history, "Ctrl+H"),
        ])
        menu_button("Hilfe", [
            act("Tutorial", self.start_tutorial, "F1"),
            act("Infos über Rack-Planer", lambda: show_about(self)),
            None,
            act("Lizenzen", lambda: show_licenses(self)),
            act("Über Qt", lambda: QMessageBox.aboutQt(self, "Über Qt")),
        ])

    # --- Zustand ------------------------------------------------------------
    def load_document(self, doc: RackDocument):
        """Neues oder geöffnetes Projekt anzeigen; der Verlauf beginnt neu."""
        self.doc = doc
        self._history_offered = False
        self._end_preview(refresh=False)
        self._show_rack(doc.rack, "", fit=True)
        self._state = self._saved_state = self._capture()
        self._file_state = self._state if self.path else ""
        self._loading = True
        self.hist_on.setChecked(doc.history_enabled)
        self._loading = False
        self._refresh_history_list()
        self._undo.clear()
        self._redo.clear()
        self._merge_key = ""
        self.dirty = False
        self._update_undo_actions()
        self.update_title()

    def _show_rack(self, rack: Rack, select_uid: str, fit: bool):
        self._loading = True
        self.rack = rack
        self.view.rack = rack
        self.view.selected_uid = select_uid if rack.get(select_uid) else ""
        self.doc.rack = rack
        self.rack_name.setText(rack.name)
        self.rack_height.setValue(rack.height_u)
        self.rack_depth.setValue(rack.depth_mm)
        d = QDate.fromString(rack.as_of[:10], "yyyy-MM-dd")
        self.rack_asof.setDate(d if d.isValid() else QDate.currentDate())
        self._loading = False
        self.refresh()
        if fit:
            self.view.fit()
        self.on_selected(self.view.selected_uid)

    def _capture(self) -> str:
        return json.dumps(self.rack.to_dict(), sort_keys=True, ensure_ascii=False)

    def mark_dirty(self, merge: str = ""):
        """Nach jeder Änderung aufrufen: legt einen Rückgängig-Schritt an.
        Aufeinanderfolgende Änderungen mit gleichem merge-Schlüssel (z. B. Tippen im
        Namensfeld) werden zu einem Schritt zusammengefasst."""
        new = self._capture()
        if new != self._state:
            if not (merge and merge == self._merge_key):
                self._undo.append(self._state)
                del self._undo[:-UNDO_LIMIT]
            self._redo.clear()
            self._state = new
        self._merge_key = merge
        self.dirty = self._state != self._saved_state
        self._update_undo_actions()
        self.update_title()
        self._maybe_offer_history()

    def _update_undo_actions(self):
        self.act_undo.setEnabled(bool(self._undo))
        self.act_redo.setEnabled(bool(self._redo))

    def undo(self):
        if self._undo:
            self._redo.append(self._state)
            self._restore(self._undo.pop())

    def redo(self):
        if self._redo:
            self._undo.append(self._state)
            self._restore(self._redo.pop())

    def _restore(self, state: str):
        old_height = self.rack.height_u
        rack = Rack.from_dict(json.loads(state))
        self._state = state
        self._merge_key = ""
        self._show_rack(rack, self.view.selected_uid, fit=rack.height_u != old_height)
        self.dirty = self._state != self._saved_state
        self._update_undo_actions()
        self.update_title()

    def _focus_search(self):
        self.tpl_search.setFocus()
        self.tpl_search.selectAll()

    def filter_templates(self, text: str):
        first = None
        any_visible = False
        for gi in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(gi)
            visible = 0
            for ci in range(group.childCount()):
                child = group.child(ci)
                ok = template_matches(child.data(0, Qt.UserRole), text)
                child.setHidden(not ok)
                if ok:
                    visible += 1
                    first = first or child
            group.setHidden(visible == 0)
            any_visible = any_visible or visible > 0
        self.tree.expandAll()
        self.tpl_none.setVisible(not any_visible)
        if text.strip() and first is not None:
            self.tree.setCurrentItem(first)
            self.tree.scrollToItem(first)

    def update_title(self):
        name = self.path.name if self.path else "Unbenannt"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} – {version_label(EDITION)}")

    def refresh(self, rebuild_scene: bool = True):
        if rebuild_scene:
            self.view.refresh()
        self.banner.update_for(self.rack.missing_ups())
        self._dups = duplicate_ips(self.rack)
        self.dup_banner.update_for(self._dups)
        conflicts = self.rack.conflicts()
        self._conflict_uids = {u for c in conflicts for u in c.uids}
        self.depth_banner.update_for(conflicts)
        self.rail_banner.update_for(self.rack, self.view.side)
        self._restyle_ips()
        self._refresh_list()
        self._update_depth_info()
        power = self.rack.total_power()
        r = self.rack
        def num(v: float) -> str:
            return f"{v:,.0f}".replace(",", ".")
        self.status.setText(
            f"{SIDE_LABEL[self.view.side]}   |   Belegt vorne {fmt_u(r.used_u(FRONT))} HE, "
            f"hinten {fmt_u(r.used_u(REAR))} HE von {r.height_u} HE   |   "
            f"Tiefe {num(r.depth_mm)} mm   |   Leistung: {num(power)} W   |   "
            f"Wärmelast: {num(power)} W ≈ {num(power * 3.412)} BTU/h")
        self.update_title()

    def _refresh_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        rows = sorted(self.rack.top_level(), key=lambda i: -i.position)
        for it in rows:
            row = self._add_list_row(it, None)
            for d in self.rack.on_shelf(it.uid):
                self._add_list_row(d, row)
        self.list.expandAll()
        self.list.blockSignals(False)

    def _add_list_row(self, it: Item, parent: QTreeWidgetItem | None) -> QTreeWidgetItem:
        if it.shelf_id:
            where, where_tip = "", "steht auf dem Fachboden"
        else:
            span = self.rack.span(it)
            where = (fmt_u(it.position) if span == 1
                     else f"{fmt_u(it.position)}–{fmt_u(it.position + span - 1)}")
            where_tip = f"HE {where}"
        ips = it.all_ips()
        ip_text = (ips[0] + (f" +{len(ips) - 1}" if len(ips) > 1 else "")) if ips else ""
        power = f"{it.power_w:g}" if it.power_w and not it.is_shelf else ""
        side = self.rack.side_of(it)
        cols = [it.name or it.model, where, "" if it.shelf_id else SIDE_SHORT[side], ip_text,
                power]
        row = QTreeWidgetItem(parent, cols) if parent else QTreeWidgetItem(self.list, cols)
        row.setData(0, Qt.UserRole, it.uid)
        pm = QPixmap(10, 10)
        pm.fill(QColor(CATEGORY_COLORS.get(it.category, "#888")))
        row.setIcon(0, QIcon(pm))
        name_tip = it.name or it.model
        if it.model and it.model != it.name:
            name_tip += f"\n{it.model}"
        row.setToolTip(0, name_tip)
        row.setToolTip(1, where_tip)
        row.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
        if side != self.view.side:
            for c in (0, 1, 2):
                row.setForeground(c, QColor(UI_MUTED))
        top = self.rack.top_of(it)
        if top.uid in self._conflict_uids:
            row.setForeground(0, QColor(CONFLICT_RED))
            msgs = [c.text for c in self.rack.conflicts() if top.uid in c.uids]
            row.setToolTip(0, name_tip + "\n\nTiefenkonflikt:\n" + "\n".join(msgs))
        if ips:
            dup = [a for a in ips if ip_key(a) in self._dups]
            bad = [a for a in ips if not ip_is_valid(a)]
            tip = "\n".join(ips)
            if dup:
                tip += "\n\nDoppelt vergeben: " + ", ".join(dup)
            if bad:
                tip += "\n\nUngültig: " + ", ".join(bad)
            row.setToolTip(3, tip)
            if dup or bad:
                row.setForeground(3, QColor("#ff7b72"))
        if it.uid == self.view.selected_uid:
            self.list.setCurrentItem(row)
        return row

    def selected(self) -> Item | None:
        return self.rack.get(self.view.selected_uid)

    def select(self, uid: str):
        self.view.selected_uid = uid
        self.refresh()
        self.on_selected(uid)

    def on_list_selection(self, cur, _prev):
        if cur is None:
            return
        uid = cur.data(0, Qt.UserRole)
        if uid != self.view.selected_uid:
            self.view.selected_uid = uid
            it = self.rack.get(uid)
            if it is not None and self.rack.side_of(it) != self.view.side:
                self.set_side(self.rack.side_of(it))     # zeigt das Gerät auf seiner Seite
            else:
                self.view.refresh()
            self.on_selected(uid)

    def on_selected(self, uid: str):
        it = self.rack.get(uid)
        self._loading = True
        self.props.setEnabled(it is not None)
        if it is None:
            for wdg in (self.p_name, self.p_ip):
                wdg.clear()
            for roww, _le in self.p_extra_ips:
                roww.setVisible(False)
            self.p_model.clear()
            self.p_mount.clear()
        else:
            self.p_name.setText(it.name)
            self.p_show_name.setChecked(it.show_name)
            self.p_ip.setText(it.ip)
            self._style_ip(it.ip)
            self._load_extra_ips(it)
            self.p_model.setText(it.model or "–")
            shelf = it.is_shelf
            self.p_ip.setEnabled(not shelf)
            self.p_cat.setEnabled(not shelf)
            self.p_power.setEnabled(not shelf)
            if not shelf:
                self.p_cat.setCurrentText(it.category)
            self.p_height.setRange(1, max(1, self.rack.height_u))
            self.p_height.setValue(it.height_u)
            # Nicht rackfähige Geräte: Höhe in cm, HE werden daraus berechnet
            non_rack = not shelf and not it.rackmount
            self.p_height.setEnabled(not non_rack)
            self.p_height_cm.setEnabled(non_rack)
            self.p_height_cm.setValue(it.height_cm if non_rack else it.height_u * U_MM / 10)
            self.p_offset.setEnabled(bool(it.shelf_id))
            self.p_offset.setValue(max(0, it.offset_mm) if it.shelf_id else 0)
            top = self.rack.get(it.shelf_id) if it.shelf_id else it
            self.p_pos.setRange(1, max(1, self.rack.height_u))
            self.p_pos.setValue(top.position)
            self.p_width.setEnabled(bool(it.shelf_id))
            self.p_width.setValue(it.width_mm)
            self.p_power.setValue(it.power_w)
            top_side = self.rack.side_of(it)
            self.p_side.setCurrentIndex(SIDES.index(top_side))
            self.p_side.setEnabled(not it.shelf_id)
            self.p_side.setToolTip("Geräte auf einem Fachboden: Seite des Fachbodens"
                                   if it.shelf_id else "Seite, an der das Gerät montiert ist. "
                                   "Von dort aus belegt es seine Tiefe.")
            self.p_depth.setValue(it.depth_mm)
            self.p_rails.setChecked(it.rails)
            self.p_rails.setEnabled(not it.shelf_id and (it.rackmount or shelf))
            if shelf:
                n = len(self.rack.on_shelf(it.uid))
                self.p_mount.setText(f"Fachboden mit {n} Gerät(en)")
            elif it.shelf_id:
                self.p_mount.setText("steht auf einem Fachboden (Position = Fachboden)")
            elif it.rackmount:
                self.p_mount.setText("19\"-Rackmontage")
            else:
                self.p_mount.setText(f"<span style='color:{UI_ACCENT}'>nicht rackfähig – "
                                     "ohne Fachboden eingesetzt</span>")
            self.p_shelf_btn.setVisible(not shelf and not it.rackmount and not it.shelf_id)
        self._loading = False
        self._update_depth_info()

    def _update_depth_info(self):
        """Hinweis unter „Tiefe“: freie Tiefe am Platz des ausgewählten Geräts."""
        it = self.selected()
        if it is None:
            self.p_depth_info.clear()
            return
        r = self.rack
        top = r.top_of(it)
        side = top.mount_side
        span = r.span(top)
        free = r.free_depth(top.position, span, side, top.uid)
        need = r.depth_of(top)
        blockers = r.rail_blockers(top.position, span, side, top.uid)
        facing = r.facing(top.position, span, side, top.uid)
        other = SIDE_SHORT[other_side(side)]
        if blockers:
            txt = (f"<span style='color:{CONFLICT_RED}'>Blockiert: „{blockers[0].label}“ "
                   f"({other}) sitzt auf Einbauschienen.</span>")
        elif top.rails and facing:
            txt = (f"<span style='color:{CONFLICT_RED}'>Die Schienen blockieren "
                   f"„{facing[0].label}“ ({other}).</span>")
        elif need > free:
            txt = (f"<span style='color:{CONFLICT_RED}'>Zu tief: {need} mm benötigt, hier sind "
                   f"nur {free} mm frei.</span>")
        else:
            txt = f"Hier frei: {free} von {r.depth_mm} mm"
            if facing:
                txt += f" ({other}: " + ", ".join(
                    f"{o.label} {r.depth_of(o)} mm" for o in facing) + ")"
            if need:
                txt += f" · Reserve {free - need} mm"
        self.p_depth_info.setText(f"<small>{txt}</small>")

    # --- Schrank ----------------------------------------------------------------
    def on_rack_name(self, text: str):
        self.rack.name = text
        self.mark_dirty(merge="rack_name")
        self.refresh()

    def on_rack_depth(self, value: int):
        if self._loading or value == self.rack.depth_mm:
            return
        self.rack.depth_mm = value
        self.mark_dirty(merge="rack_depth")
        self.refresh()

    def on_as_of(self, date: QDate):
        if self._loading:
            return
        iso = date.toString("yyyy-MM-dd")
        if iso == self.rack.as_of:
            return
        self.rack.as_of = iso
        self.mark_dirty(merge="as_of")
        self.refresh()

    def set_side(self, side: str):
        """Vorder- oder Rückseite anzeigen."""
        self.view.side = side
        (self.act_front if side == FRONT else self.act_rear).setChecked(True)
        self.refresh()
        self.on_selected(self.view.selected_uid)

    def on_view_options(self):
        self.view.show_other = self.act_other.isChecked()
        self.view.show_profile = self.act_profile.isChecked()
        self.view.refresh()
        self.view.fit()

    def show_item(self, uid: str):
        """Gerät auswählen und auf seiner Seite zeigen (Banner, Doppelklick auf Gegenseite)."""
        it = self.rack.get(uid)
        if it is None:
            return
        self.view.selected_uid = uid
        self.set_side(self.rack.side_of(it))

    def on_fine_grid(self, checked: bool):
        self.view.fine = checked
        self.p_pos.setSingleStep(1 / 3 if checked else 1)
        self.statusBar().showMessage(
            "Feinraster ⅓ HE aktiv" if checked else "Raster: ganze HE", 3000)

    def on_rack_height(self, value: int):
        if self._loading:
            return
        need = self.rack.required_height()
        if value < need:
            QMessageBox.warning(
                self, APP_NAME,
                f"Der Schrank kann nicht auf {value} HE verkleinert werden – es sind Geräte "
                f"bis HE {need} eingebaut. Bitte zuerst Geräte verschieben oder entfernen.")
            self._loading = True
            self.rack_height.setValue(self.rack.height_u)
            self._loading = False
            return
        self.rack.height_u = value
        self.mark_dirty()
        self.refresh()
        self.view.fit()

    # --- Hinzufügen ---------------------------------------------------------------
    def add_from_tree(self, ti: QTreeWidgetItem | None):
        if ti is None or ti.data(0, Qt.UserRole) is None:
            QMessageBox.information(self, APP_NAME, "Bitte zuerst eine Vorlage auswählen.")
            return
        t: Template = ti.data(0, Qt.UserRole)
        if t.category == CAT_SHELF:
            self.add_shelf(template=t)
            return
        self.add_item(Item(name=t.model, model=t.model, category=t.category,
                           height_u=t.height_u, rackmount=t.rackmount,
                           width_mm=t.width_mm, power_w=t.power_w, height_cm=t.height_cm,
                           depth_mm=t.depth_mm, rails=t.rails))

    def add_custom(self):
        dlg = DeviceDialog(self, self.view.side, self.rack.depth_mm)
        if dlg.exec() == QDialog.Accepted:
            item = dlg.item()
            self.add_item(item, side=item.mount_side)

    def add_ups(self):
        self.add_item(Item(name="USV", model="USV 2 HE", category=CAT_USV, height_u=2,
                           power_w=30, depth_mm=480, rails=True), side=FRONT)

    def _no_space(self, span: float):
        QMessageBox.warning(self, APP_NAME,
                            f"Im Schrank ist kein zusammenhängender Platz mit {fmt_u(span)} HE "
                            "frei.\n"
                            "Schrank vergrößern oder Geräte verschieben.")

    def add_item(self, item: Item, side: str | None = None) -> bool:
        """Gerät einbauen – auf der angezeigten Seite, sofern nicht anders angegeben
        (eigene Geräte bringen ihre Seite aus dem Dialog mit)."""
        item.mount_side = side if side is not None else self.view.side
        if item.mount_side != self.view.side:
            self.set_side(item.mount_side)
        if not item.rackmount:
            return self._add_non_rack(item)
        pos = self.rack.find_free(item.height_u, item.mount_side)
        if not pos:
            self._no_space(item.height_u)
            return False
        item.position = pos
        self.rack.items.append(item)
        self.mark_dirty()
        self.select(item.uid)
        return True

    def _shelves_fitting(self, item: Item) -> list[Item]:
        res = []
        for s in (i for i in self.rack.top_level(self.view.side) if i.is_shelf):
            if self.rack.shelf_gap(s.uid, min(item.width_mm, SHELF_WIDTH_MM)) < 0:
                continue
            new_span = self.rack.shelf_span(s, extra=item)
            if not self.rack.nearest_free(s.position, new_span, ignore=s.uid,
                                          side=s.mount_side):
                continue
            res.append(s)
        return res

    def _add_non_rack(self, item: Item) -> bool:
        shelves = self._shelves_fitting(item)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Fachboden einbauen?")
        box.setText(f"„{item.name}“ ist nicht für den Rackeinbau vorgesehen.")
        box.setInformativeText(
            "Soll ein Fachboden eingebaut werden, auf dem das Gerät steht?"
            + ("\n\nEs gibt bereits einen Fachboden mit genügend Platz." if shelves else ""))
        b_new = box.addButton("Neuen Fachboden einbauen", QMessageBox.AcceptRole)
        b_exist = box.addButton("Auf vorhandenen Fachboden", QMessageBox.AcceptRole) \
            if shelves else None
        b_none = box.addButton("Ohne Fachboden", QMessageBox.DestructiveRole)
        box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.setDefaultButton(b_exist or b_new)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_new:
            shelf = self.add_shelf(extra=item, select=False)
            if shelf is None:
                return False
            self._place_on_shelf(item, shelf)
        elif b_exist is not None and clicked is b_exist:
            self._place_on_shelf(item, shelves[0])
        elif clicked is b_none:
            pos = self.rack.find_free(item.height_u, item.mount_side)
            if not pos:
                self._no_space(item.height_u)
                return False
            item.position = pos
            self.rack.items.append(item)
        else:
            return False
        self.mark_dirty()
        self.select(item.uid)
        return True

    def _place_on_shelf(self, item: Item, shelf: Item):
        item.shelf_id = shelf.uid
        item.position = 0
        item.mount_side = shelf.mount_side
        item.rails = False
        if item.width_mm > SHELF_WIDTH_MM:
            item.width_mm = SHELF_WIDTH_MM
        item.offset_mm = max(0, self.rack.shelf_gap(shelf.uid, item.width_mm, exclude=item.uid))
        self.rack.items.append(item)
        # Fachboden ggf. verschieben, falls der höhere Aufbau sonst nicht passt
        if not self.rack.is_free(shelf.position, self.rack.span(shelf), ignore=shelf.uid,
                                 side=shelf.mount_side):
            shelf.position = self.rack.nearest_free(shelf.position, self.rack.span(shelf),
                                                    ignore=shelf.uid, side=shelf.mount_side)

    def add_shelf(self, extra: Item | None = None, select: bool = True,
                  template: Template | None = None) -> Item | None:
        """Fachboden einbauen (Vorlage kurz/400 mm/volle Tiefe; ohne Vorlage 400 mm).
        extra: Gerät, das darauf gestellt werden soll – dessen Höhe wird mit eingeplant."""
        t = template
        if t is not None and t.full_depth:
            depth = self.rack.depth_mm
        else:
            depth = t.depth_mm if t is not None else SHELF_DEPTH_MM
        shelf = Item(name="Fachboden", model=t.model if t else "", category=CAT_SHELF,
                     height_u=1, rackmount=True, show_name=False, mount_side=self.view.side,
                     depth_mm=min(depth, self.rack.depth_mm), rails=bool(t and t.rails))
        span = self.rack.shelf_span(shelf, extra=extra)
        pos = self.rack.find_free(span, shelf.mount_side)
        if not pos:
            self._no_space(span)
            return None
        shelf.position = pos
        self.rack.items.append(shelf)
        self.mark_dirty()
        if select:
            self.select(shelf.uid)
        return shelf

    def put_selected_on_shelf(self):
        it = self.selected()
        if it is None or it.rackmount or it.shelf_id:
            return
        self.rack.items.remove(it)
        # Platz des Geräts zunächst freigeben, dann wie neu hinzufügen
        if not self._add_non_rack(it):
            self.rack.items.append(it)
            self.refresh()

    # --- Bearbeiten -----------------------------------------------------------------
    def set_prop(self, attr: str, value, rebuild: bool = True, merge: str = ""):
        it = self.selected()
        if it is None or self._loading:
            return
        setattr(it, attr, value)
        self.mark_dirty(merge=f"{merge}:{it.uid}" if merge else "")
        self.refresh(rebuild_scene=rebuild)

    def _ip_problem(self, text: str) -> tuple[str, str]:
        """(Stylesheet, Tooltip) für ein IP-Feld des ausgewählten Geräts."""
        text = text.strip()
        if not text:
            return "", ""
        if not ip_is_valid(text):
            return IP_BAD_CSS, "Keine gültige IP-Adresse"
        devs = self._dups.get(ip_key(text))
        it = self.selected()
        if devs and it is not None:
            others = list(dict.fromkeys(d.name or d.model for d in devs if d.uid != it.uid))
            msg = ("Doppelt: auch bei " + ", ".join(others)) if others \
                else "Doppelt: an diesem Gerät mehrfach eingetragen"
            return IP_DUP_CSS, msg
        return "", ""

    def _style_line_ip(self, le: QLineEdit, text: str):
        css, tip = self._ip_problem(text)
        le.setStyleSheet(css)
        le.setToolTip(tip)

    def _style_ip(self, text: str):
        self._style_line_ip(self.p_ip, text)

    def _restyle_ips(self):
        if self.selected() is None:
            return
        self._style_ip(self.p_ip.text())
        for roww, le in self.p_extra_ips:
            if roww.isVisible() or le.text():
                self._style_line_ip(le, le.text())

    def on_ip_edited(self, text: str):
        self.set_prop("ip", text.strip(), merge="ip")
        self._style_ip(text)

    def _load_extra_ips(self, it: Item):
        shelf = it.is_shelf
        for i, (roww, le) in enumerate(self.p_extra_ips):
            used = i < len(it.ips) and not shelf
            roww.setVisible(used)
            le.setText(it.ips[i] if used else "")
            self._style_line_ip(le, le.text())
        self.p_add_ip.setVisible(not shelf)
        self.p_add_ip.setEnabled(len(it.ips) < MAX_IPS - 1)

    def add_extra_ip(self):
        it = self.selected()
        if it is None or len(it.ips) >= MAX_IPS - 1:
            return
        it.ips = [*it.ips, ""]
        self._loading = True
        self._load_extra_ips(it)
        self._loading = False
        self.p_extra_ips[len(it.ips) - 1][1].setFocus()

    def remove_extra_ip(self, index: int):
        it = self.selected()
        if it is None or index >= len(it.ips):
            return
        it.ips = [a for i, a in enumerate(it.ips) if i != index]
        self.mark_dirty()
        self.refresh()
        self._loading = True
        self._load_extra_ips(it)
        self._loading = False

    def on_extra_ip_edited(self, index: int, text: str):
        it = self.selected()
        if it is None or self._loading or index >= len(it.ips):
            return
        ips = list(it.ips)
        ips[index] = text.strip()
        self.set_prop("ips", ips, merge=f"ips{index}")
        self._style_line_ip(self.p_extra_ips[index][1], text)

    def on_height(self, value: int):
        it = self.selected()
        if it is None or self._loading or value == it.height_u:
            return
        self._apply_height(it, value, it.height_cm)

    def on_height_cm(self, value: float):
        it = self.selected()
        if it is None or self._loading or it.rackmount or abs(value - it.height_cm) < 0.05:
            return
        self._apply_height(it, units_for_cm(value), value)

    def _apply_height(self, it: Item, units: int, height_cm: float):
        top = self.rack.get(it.shelf_id) if it.shelf_id else it
        old = it.height_u, it.height_cm
        it.height_u, it.height_cm = units, height_cm
        new_pos = self.rack.nearest_free(top.position, self.rack.span(top), ignore=top.uid,
                                         side=top.mount_side)
        if new_pos and it.shelf_id:
            top.position = new_pos
        elif new_pos != top.position:
            it.height_u, it.height_cm = old
            QMessageBox.warning(self, APP_NAME,
                                f"Für {units} HE ist an dieser Position nicht genug Platz.")
            self.on_selected(it.uid)
            return
        self.mark_dirty()
        self.refresh()
        self.on_selected(it.uid)

    def on_pos(self, value: float):
        it = self.selected()
        if it is None or self._loading:
            return
        top = self.rack.get(it.shelf_id) if it.shelf_id else it
        value = snap_third(value) if self.view.fine else round(value)
        if abs(value - top.position) > EPS and not self.try_move(top.uid, value):
            self._loading = True
            self.p_pos.setValue(top.position)
            self._loading = False

    def on_width(self, value: int):
        it = self.selected()
        if it is None or self._loading or not it.shelf_id:
            return
        offset = it.offset_mm
        if self.rack.shelf_overlaps(it.shelf_id, offset, value, exclude=it.uid):
            # Notfalls nach links ausweichen bzw. eine andere Lücke suchen
            offset = self.rack.shelf_gap(it.shelf_id, value, exclude=it.uid)
        if offset < 0:
            QMessageBox.warning(self, APP_NAME,
                                f"Auf dem Fachboden ist kein Platz für {value} mm Breite.")
            self._loading = True
            self.p_width.setValue(it.width_mm)
            self._loading = False
            return
        it.width_mm, it.offset_mm = value, offset
        self.mark_dirty()
        self.refresh()
        self.on_selected(it.uid)

    def on_offset(self, value: int):
        it = self.selected()
        if it is None or self._loading or not it.shelf_id or value == it.offset_mm:
            return
        if not self.move_on_shelf(it.uid, it.shelf_id, value):
            self._loading = True
            self.p_offset.setValue(it.offset_mm)
            self._loading = False

    def move_on_shelf(self, uid: str, shelf_uid: str, offset: int) -> bool:
        dev, shelf = self.rack.get(uid), self.rack.get(shelf_uid)
        if dev is None or shelf is None or not self.rack.can_place_on_shelf(dev, shelf, offset):
            self.statusBar().showMessage("Dort ist auf dem Fachboden kein Platz frei.", 3000)
            return False
        dev.shelf_id, dev.offset_mm = shelf.uid, offset
        dev.mount_side = shelf.mount_side
        self.mark_dirty()
        self.refresh()
        self.on_selected(self.view.selected_uid)
        return True

    def try_move(self, uid: str, pos: float) -> bool:
        it = self.rack.get(uid)
        if it is None:
            return False
        if not self.rack.is_free(pos, self.rack.span(it), ignore=uid, side=it.mount_side):
            self.statusBar().showMessage("Dort ist kein Platz frei.", 3000)
            return False
        it.position = pos
        self.mark_dirty()
        self.refresh()
        self.on_selected(self.view.selected_uid)
        return True

    def on_side(self, side: str):
        """Montageseite ändern: Das Gerät belegt ab der neuen Seite seine Tiefe."""
        it = self.selected()
        if it is None or self._loading or it.shelf_id or side == it.mount_side:
            return
        span = self.rack.span(it)
        pos = it.position
        if not self.rack.is_free(pos, span, ignore=it.uid, side=side):
            pos = self.rack.nearest_free(pos, span, ignore=it.uid, side=side)
        if not pos:
            QMessageBox.warning(self, APP_NAME, f"Auf der {SIDE_LABEL[side]} ist kein Platz "
                                                f"mit {span} HE frei.")
            self.on_selected(it.uid)
            return
        it.mount_side, it.position = side, pos
        for d in self.rack.on_shelf(it.uid):
            d.mount_side = side
        self.mark_dirty()
        self.statusBar().showMessage(
            f"„{it.label}“ ist jetzt {SIDE_SHORT[side]} montiert (ab HE {fmt_u(pos)}).", 4000)
        self.set_side(side)

    def on_move_requested(self, uid: str, pos: float):
        self.try_move(uid, pos)

    def nudge(self, delta: int):
        it = self.selected()
        if it is None:
            return
        top = self.rack.get(it.shelf_id) if it.shelf_id else it
        span = self.rack.span(top)
        step = delta / 3 if self.view.fine else delta
        pos = snap_third(top.position + step) if self.view.fine else round(top.position + step)
        # Über belegte Bereiche hinwegspringen
        while 1 - EPS <= pos and pos + span - 1 <= self.rack.height_u + EPS:
            if self.rack.is_free(pos, span, ignore=top.uid, side=top.mount_side):
                self.try_move(top.uid, pos)
                return
            pos = snap_third(pos + step)
        self.statusBar().showMessage("Kein freier Platz in dieser Richtung.", 3000)

    def delete_selected(self):
        it = self.selected()
        if it is None:
            return
        if it.is_shelf:
            n = len(self.rack.on_shelf(it.uid))
            if n and QMessageBox.question(
                    self, APP_NAME,
                    f"Den Fachboden mit {n} Gerät(en) darauf entfernen?") != QMessageBox.Yes:
                return
        self.rack.remove(it.uid)
        self.view.selected_uid = ""
        self.mark_dirty()
        self.refresh()
        self.on_selected("")

    # --- Dateien --------------------------------------------------------------------
    def maybe_save(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, APP_NAME, "Änderungen speichern?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save_file()
        return r == QMessageBox.Discard

    def new_file(self):
        if not self.maybe_save():
            return
        self.path = None
        self.dirty = False
        self.load_document(RackDocument())

    def open_file(self):
        if not self.maybe_save():
            return
        fn, _ = QFileDialog.getOpenFileName(self, "Projekt öffnen", self._dialog_dir(),
                                            FILE_FILTER)
        if fn:
            self.open_path(Path(fn))

    def open_path(self, path: Path) -> bool:
        try:
            doc = load_document(path)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
            QMessageBox.critical(self, APP_NAME,
                                 f"Die Datei „{path.name}“ konnte nicht geöffnet werden:\n{e}")
            return False
        self.path = path
        self._last_dir = str(path.parent)
        self.load_document(doc)
        if doc.notes:
            QMessageBox.information(self, APP_NAME,
                                    f"„{path.name}“ stammt aus einer älteren Version.\n\n"
                                    + "\n\n".join(doc.notes))
        return True

    def _dialog_dir(self, filename: str = "") -> str:
        """Startordner für Datei-Dialoge: zuletzt benutzter Ordner dieser Sitzung,
        sonst der Ordner des geöffneten Projekts. Wird nirgends gespeichert (portabel)."""
        folder = self._last_dir or (str(self.path.parent) if self.path else "")
        if not filename:
            return folder
        return str(Path(folder) / filename) if folder else filename

    def _base_name(self) -> str:
        if self.path:
            n = self.path.name
            return n[:-len(FILE_SUFFIX)] if n.lower().endswith(FILE_SUFFIX) else self.path.stem
        return self.rack.name or "Rack"

    def save_file(self) -> bool:
        if self.path is None:
            return self.save_file_as()
        doc = self.doc
        added = False
        if doc.history_enabled and self._file_state and self._file_state != self._state:
            # bisherigen Stand der Datei in die Historie übernehmen
            added = doc.add_snapshot(json.loads(self._file_state), doc.saved_at)
        doc.rack = self.rack
        prev_saved = doc.saved_at
        doc.saved_at = now_iso()
        try:
            save_document(doc, self.path)
        except OSError as e:
            if added:
                doc.history.pop()
            doc.saved_at = prev_saved
            QMessageBox.critical(self, APP_NAME, f"Speichern fehlgeschlagen:\n{e}")
            return False
        self._last_dir = str(self.path.parent)
        self._saved_state = self._state = self._file_state = self._capture()
        self.dirty = False
        self.update_title()
        self._refresh_history_list()
        msg = f"Gespeichert: {self.path}"
        if added:
            msg += f"  ·  bisheriger Stand in der Historie ({len(doc.history)} Einträge)"
        self.statusBar().showMessage(msg, 5000)
        return True

    def save_file_as(self) -> bool:
        fn, _ = QFileDialog.getSaveFileName(
            self, "Projekt speichern",
            str(self.path) if self.path else self._dialog_dir(f"{self.rack.name}{FILE_SUFFIX}"),
            FILE_FILTER)
        if not fn:
            return False
        if not fn.lower().endswith(".json"):
            fn += FILE_SUFFIX
        new = Path(fn)
        if self.path is None or new != self.path:
            self._file_state = ""        # neue Datei: es gibt noch keinen alten Stand
        self.path = new
        return self.save_file()

    # --- Historie ---------------------------------------------------------------
    def _maybe_offer_history(self):
        """Gespeicherte Datei wurde geändert: einmal anbieten, eine Historie anzulegen."""
        doc = self.doc
        if (self.path is None or not self.dirty or doc.history_enabled
                or doc.history_declined or self._history_offered):
            return
        self._history_offered = True
        # erst nach der laufenden Eingabe fragen (z. B. Tippen im Namensfeld)
        QTimer.singleShot(0, self._ask_history)

    def _ask_history(self):
        old = json.loads(self._file_state).get("as_of", "") if self._file_state else ""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Historie anlegen?")
        box.setText("Du änderst eine gespeicherte Datei.")
        box.setInformativeText(
            "Soll eine Historie angelegt werden? Dann bleibt der bisherige Stand"
            + (f" vom {fmt_date(old)}" if old else "")
            + " beim Speichern in derselben Datei erhalten und lässt sich jederzeit im Tab "
            "„Historie“ ansehen oder wiederherstellen.")
        yes = box.addButton("Historie anlegen (empfohlen)", QMessageBox.AcceptRole)
        box.addButton("Ohne Historie weiter", QMessageBox.RejectRole)
        box.setDefaultButton(yes)
        box.exec()
        if box.clickedButton() is yes:
            self.enable_history()
        else:
            self.decline_history()

    def enable_history(self):
        self._loading = True
        self.hist_on.setChecked(True)
        self._loading = False
        self.doc.history_enabled = True
        self.doc.history_declined = False
        msg = "Historie aktiviert: Beim Speichern bleibt der bisherige Stand in der Datei."
        if self.rack.as_of < today_iso():
            self.rack.as_of = today_iso()
            self._show_rack(self.rack, self.view.selected_uid, fit=False)
            self.mark_dirty()
            msg += " Der aktuelle Stand wurde auf heute gesetzt."
        self._refresh_history_list()
        self.statusBar().showMessage(msg, 6000)

    def decline_history(self):
        self.doc.history_declined = True

    def on_history_toggled(self, on: bool):
        if self._loading:
            return
        if on:
            self.enable_history()
        else:
            self.doc.history_enabled = False
            self._refresh_history_list()
            if self.doc.history:
                self.statusBar().showMessage(
                    "Historie pausiert – vorhandene Einträge bleiben in der Datei.", 5000)

    def show_history(self):
        self.tabs.setCurrentWidget(self.hist_tab)

    def _refresh_history_list(self):
        doc = self.doc
        self.hist_list.blockSignals(True)
        self.hist_list.clear()
        cur = QListWidgetItem(f"Aktueller Stand ({fmt_date(self.rack.as_of)})"
                              + (" – ungespeichert" if self.dirty else ""))
        f = cur.font()
        f.setBold(True)
        cur.setFont(f)
        cur.setData(Qt.UserRole, None)
        self.hist_list.addItem(cur)
        for idx in range(len(doc.history) - 1, -1, -1):
            snap = doc.history[idx]
            when = snap.saved_at.replace("T", " ")[:16]
            d, _, t = when.partition(" ")
            n = sum(1 for i in snap.rack.get("items", []) if i.get("category") != CAT_SHELF)
            it = QListWidgetItem(f"Stand {fmt_date(snap.as_of)}\n"
                                 f"gespeichert {fmt_date(d)} {t} · {n} Gerät(e)".rstrip())
            it.setData(Qt.UserRole, idx)
            self.hist_list.addItem(it)
        self.hist_list.setCurrentRow(0)
        self.hist_list.blockSignals(False)
        if not self.path:
            info = "Die Historie wird in der Projektdatei gespeichert – zuerst speichern."
        elif not doc.history:
            info = ("Noch keine früheren Stände. " + (
                "Beim nächsten Speichern wird der bisherige Stand hier abgelegt."
                if doc.history_enabled else
                "Aktiviere die Historie, dann bleibt bei jedem Speichern der bisherige Stand "
                "erhalten."))
        else:
            info = "Klicke einen Stand an, um ihn im Schrank anzusehen."
        self.hist_info.setText(info)
        self._update_history_buttons()

    def _update_history_buttons(self):
        on_old = self._preview is not None
        self.hist_restore.setEnabled(on_old)
        self.hist_copy.setEnabled(on_old)

    def on_tab_changed(self, index: int):
        if self.tabs.widget(index) is not self.hist_tab:
            self._end_preview()
        else:
            self._refresh_history_list()

    def on_history_row(self, row: int):
        it = self.hist_list.item(row)
        idx = it.data(Qt.UserRole) if it is not None else None
        if idx is None:
            self._end_preview()
        else:
            self._start_preview(self.doc.history[idx])

    def _start_preview(self, snap):
        """Früheren Stand im Schrank anzeigen – nur ansehen, nichts bearbeiten."""
        self._preview = snap.rack
        rack = snap.to_rack()
        self.view.rack = rack
        self.view.read_only = True
        self.view.selected_uid = ""
        self.view.refresh()
        self.preview_banner.show_for(snap.as_of, snap.saved_at)
        for w in (self.left_panel, self.props):
            w.setEnabled(False)
        self.act_undo.setEnabled(False)
        self.act_redo.setEnabled(False)
        self._update_history_buttons()

    def _end_preview(self, refresh: bool = True):
        if self._preview is None:
            return
        self._preview = None
        self.view.rack = self.rack
        self.view.read_only = False
        self.preview_banner.hide()
        self.left_panel.setEnabled(True)
        self._update_undo_actions()
        self._update_history_buttons()
        if refresh:
            self.refresh()
            self.on_selected(self.view.selected_uid)

    def restore_preview(self):
        if self._preview is None:
            return
        rack = Rack.from_dict(json.loads(json.dumps(self._preview)))
        self.hist_list.blockSignals(True)
        self.hist_list.setCurrentRow(0)
        self.hist_list.blockSignals(False)
        self._end_preview(refresh=False)
        self._show_rack(rack, "", fit=True)
        self.mark_dirty()
        self._refresh_history_list()
        self.statusBar().showMessage(
            f"Stand vom {fmt_date(rack.as_of)} wiederhergestellt (Strg + Z macht es "
            "rückgängig).", 6000)

    def save_preview_copy(self):
        if self._preview is None:
            return
        rack = Rack.from_dict(json.loads(json.dumps(self._preview)))
        fn, _ = QFileDialog.getSaveFileName(
            self, "Stand als eigene Datei speichern",
            self._dialog_dir(f"{self._base_name()} Stand {rack.as_of}{FILE_SUFFIX}"),
            FILE_FILTER)
        if not fn:
            return
        try:
            save_document(RackDocument(rack=rack, saved_at=now_iso()), fn)
        except OSError as e:
            QMessageBox.critical(self, APP_NAME, f"Speichern fehlgeschlagen:\n{e}")
            return
        self.statusBar().showMessage(f"Gespeichert: {fn}", 5000)

    # --- Export ----------------------------------------------------------------
    def _sides_used(self) -> set[str]:
        return {i.mount_side for i in self.rack.top_level()}

    def export_pdf(self):
        dlg = ExportDialog(self, "pdf", self.view.side, self._sides_used())
        dlg.separate.setChecked(getattr(self, "_pdf_separate", False))
        if dlg.exec() != QDialog.Accepted:
            return
        sides = dlg.sides()
        self._pdf_separate = dlg.separate.isChecked()
        fn, _ = QFileDialog.getSaveFileName(self, "Als PDF exportieren",
                                            self._dialog_dir(f"{self._base_name()}.pdf"),
                                            "PDF-Dokument (*.pdf)")
        if not fn:
            return
        if not fn.lower().endswith(".pdf"):
            fn += ".pdf"
        try:
            export_pdf(self.rack, fn, sides, dlg.power.isChecked(), self._pdf_separate)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"PDF-Export fehlgeschlagen:\n{e}")
            return
        self._last_dir = str(Path(fn).parent)
        self.statusBar().showMessage(f"PDF exportiert: {fn}", 5000)

    def export_image(self):
        dlg = ExportDialog(self, "image", self.view.side, self._sides_used())
        if dlg.exec() != QDialog.Accepted:
            return
        fmt = dlg.image_format()
        side = dlg.sides()[0]
        suffix = "Vorderseite" if side == FRONT else "Rückseite"
        filt = "PNG-Bild (*.png)" if fmt == "png" else "SVG-Grafik (*.svg)"
        fn, _ = QFileDialog.getSaveFileName(
            self, "Als Bild exportieren",
            self._dialog_dir(f"{self._base_name()} {suffix}.{fmt}"), filt)
        if not fn:
            return
        if not fn.lower().endswith(f".{fmt}"):
            fn += f".{fmt}"
        try:
            if fmt == "png":
                if not export_png(self.rack, fn, side, dlg.scale.currentData(),
                                  dlg.transparent.isChecked(), dlg.power.isChecked()):
                    raise OSError("Die Datei konnte nicht geschrieben werden.")
            else:
                export_svg(self.rack, fn, side, dlg.power.isChecked())
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"Bildexport fehlgeschlagen:\n{e}")
            return
        self._last_dir = str(Path(fn).parent)
        self.statusBar().showMessage(f"Bild exportiert: {fn}", 5000)

    # --- Hilfe -----------------------------------------------------------------
    def start_tutorial(self):
        if self.findChild(TutorialOverlay):
            return
        TutorialOverlay(self, tutorial_steps(self)).start()

    def closeEvent(self, e):
        if self.maybe_save():
            e.accept()
        else:
            e.ignore()

    def showEvent(self, e):
        super().showEvent(e)
        self.view.fit()
        if not self._hint_shown:
            self._hint_shown = True
            self.statusBar().showMessage(
                "Neu hier? Hilfe → Tutorial (F1) stellt alle Funktionen kurz vor.", 10000)
