"""Dialoge: eigenes Gerät und Export."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QRadioButton, QSpinBox,
)

from rackcore import (
    CAT_OTHER, CATEGORIES, FRONT, MAX_IPS, SHELF_WIDTH_MM, SIDE_LABEL, SIDE_SHORT, SIDES,
    Item, split_ips, units_for_cm,
)

from .export import PNG_SCALES
from .theme import UI_MUTED

class DeviceDialog(QDialog):
    """Eigenes Gerät anlegen."""

    def __init__(self, parent=None, side: str = FRONT, rack_depth: int = 600):
        super().__init__(parent)
        self.setWindowTitle("Eigenes Gerät hinzufügen")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("z. B. Hypervisor 01")
        self.ip = QLineEdit()
        self.ip.setPlaceholderText("z. B. 192.168.1.10, 10.0.0.10 (bis zu 5)")
        self.category = QComboBox()
        self.category.addItems(CATEGORIES)
        self.category.setCurrentText(CAT_OTHER)
        self.height = QSpinBox()
        self.height.setRange(1, 20)
        self.height.setSuffix(" HE")
        self.rackmount = QCheckBox("Für den Rackeinbau (19\") geeignet")
        self.rackmount.setChecked(True)
        self.width = QSpinBox()
        self.width.setRange(20, SHELF_WIDTH_MM)
        self.width.setValue(200)
        self.width.setSuffix(" mm")
        self.width.setEnabled(False)
        self.height_cm = QDoubleSpinBox()
        self.height_cm.setRange(0.5, 250)
        self.height_cm.setDecimals(1)
        self.height_cm.setSingleStep(0.5)
        self.height_cm.setValue(5.0)
        self.height_cm.setSuffix(" cm")
        self.height_cm.setEnabled(False)
        self.height_cm.valueChanged.connect(
            lambda v: self.height.setValue(units_for_cm(v)) if not self.rackmount.isChecked()
            else None)
        self.rackmount.toggled.connect(self._mount_toggled)
        self.power = QDoubleSpinBox()
        self.power.setRange(0, 10000)
        self.power.setDecimals(0)
        self.power.setSuffix(" W")
        self.depth = QSpinBox()
        self.depth.setRange(0, 2000)
        self.depth.setSingleStep(10)
        self.depth.setSuffix(" mm")
        self.depth.setSpecialValueText("unbekannt")
        self.depth.setValue(min(300, rack_depth))
        self.side = QComboBox()
        for sd in SIDES:
            self.side.addItem(f"{SIDE_LABEL[sd]} ({SIDE_SHORT[sd]} montiert)", sd)
        self.side.setCurrentIndex(SIDES.index(side))
        self.rails = QCheckBox("Auf Einbauschienen (blockiert die Gegenseite)")
        form.addRow("Gerätename:", self.name)
        form.addRow("IP-Adresse(n):", self.ip)
        form.addRow("Kategorie:", self.category)
        form.addRow("", self.rackmount)
        form.addRow("Höhe:", self.height)
        form.addRow("Höhe (non-Rack):", self.height_cm)
        form.addRow("Breite (auf Fachboden):", self.width)
        form.addRow("Leistungsaufnahme:", self.power)
        form.addRow("Tiefe:", self.depth)
        form.addRow("Montage:", self.side)
        form.addRow("", self.rails)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Hinzufügen")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _mount_toggled(self, rack: bool):
        self.width.setEnabled(not rack)
        self.height_cm.setEnabled(not rack)
        self.height.setEnabled(rack)
        self.rails.setEnabled(rack)
        if not rack:
            self.height.setValue(units_for_cm(self.height_cm.value()))

    def item(self) -> Item:
        cat = self.category.currentText()
        rack = self.rackmount.isChecked()
        ips = split_ips(self.ip.text())
        return Item(name=self.name.text().strip() or cat, category=cat,
                    height_u=self.height.value(), ip=(ips[0] if ips else ""),
                    ips=ips[1:MAX_IPS],
                    rackmount=rack,
                    width_mm=SHELF_WIDTH_MM if rack else self.width.value(),
                    height_cm=0.0 if rack else self.height_cm.value(),
                    power_w=self.power.value(), depth_mm=self.depth.value(),
                    mount_side=self.side.currentData(), rails=self.rails.isChecked() and rack)


class ExportDialog(QDialog):
    """Optionen für den PDF- oder Bildexport."""

    def __init__(self, parent, mode: str, current_side: str, sides_used: set[str]):
        super().__init__(parent)
        self.mode = mode
        form = QFormLayout(self)
        if mode == "pdf":
            self.setWindowTitle("Als PDF exportieren")
            self.cb = {}
            row = QHBoxLayout()
            for sd in SIDES:
                cb = QCheckBox(SIDE_LABEL[sd])
                cb.setChecked(sd == current_side or sd in sides_used)
                cb.toggled.connect(self._validate)
                row.addWidget(cb)
                self.cb[sd] = cb
            row.addStretch()
            form.addRow("Seiten:", row)
            self.separate = QCheckBox("Jede Seite auf eine eigene PDF-Seite")
            self.separate.setChecked(False)
            self.separate.setToolTip("Aus: Vorder- und Rückseite nebeneinander auf einer A4-Seite.\n"
                                     "An: Vorderseite auf Seite 1, Rückseite auf Seite 2 "
                                     "(jeweils größer).")
            self.separate.toggled.connect(self._validate)
            form.addRow("", self.separate)
            self.hint = QLabel()
            self.hint.setStyleSheet(f"color:{UI_MUTED};")
            form.addRow("", self.hint)
            self.transparent = None
        else:
            self.setWindowTitle("Als Bild exportieren")
            self.fmt = QComboBox()
            self.fmt.addItem("PNG (Rastergrafik)", "png")
            self.fmt.addItem("SVG (Vektorgrafik, beliebig skalierbar)", "svg")
            self.fmt.currentIndexChanged.connect(self._validate)
            form.addRow("Format:", self.fmt)
            row = QHBoxLayout()
            self.side_group = QButtonGroup(self)
            for sd in SIDES:
                rb = QRadioButton(SIDE_LABEL[sd])
                rb.setChecked(sd == current_side)
                rb.setProperty("side", sd)
                self.side_group.addButton(rb)
                row.addWidget(rb)
            row.addStretch()
            form.addRow("Seite:", row)
            self.scale = QComboBox()
            for label, v in PNG_SCALES.items():
                self.scale.addItem(label, v)
            self.scale.setCurrentIndex(1)
            form.addRow("Auflösung:", self.scale)
            self.transparent = QCheckBox("Transparenter Hintergrund")
            form.addRow("", self.transparent)
        self.power = QCheckBox("Max. Stromlast und Wärmelast anzeigen")
        self.power.setChecked(False)
        self.power.setToolTip("Summe der Leistungsaufnahme aller Geräte (W, A bei 230 V) und "
                              "Wärmelast (W, BTU/h) unter dem Schrank")
        form.addRow("Zusatz:", self.power)
        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.button(QDialogButtonBox.Ok).setText("Exportieren …")
        self.bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        form.addRow(self.bb)
        self._validate()

    def _validate(self):
        if self.mode == "pdf":
            n = sum(c.isChecked() for c in self.cb.values())
            self.bb.button(QDialogButtonBox.Ok).setEnabled(n > 0)
            self.separate.setEnabled(n > 1)
            if n < 2:
                self.hint.setText("Eine Seite des Schranks auf einer A4-Seite.")
            elif self.separate.isChecked():
                self.hint.setText("Vorder- und Rückseite auf je einer eigenen A4-Seite.")
            else:
                self.hint.setText("Beide Seiten stehen nebeneinander auf einer A4-Seite.")
        else:
            png = self.fmt.currentData() == "png"
            self.scale.setEnabled(png)
            self.transparent.setEnabled(png)

    def sides(self) -> list[str]:
        if self.mode == "pdf":
            return [sd for sd in SIDES if self.cb[sd].isChecked()]
        return [self.side_group.checkedButton().property("side")]

    def image_format(self) -> str:
        return self.fmt.currentData()
