"""Export: PDF (Vorder- und/oder Rückseite) sowie Bild (PNG oder SVG, eine Seite).

Exportiert wird nur der Schrank mit Geräten und Beschriftung, ohne Hinweise, Auswahl,
Gegenseite oder Seitenansicht. Unter dem Titel steht der „Aktuelle Stand“; auf Wunsch
steht unter dem Schrank die maximale Strom- und Wärmelast.
"""

from __future__ import annotations

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QGraphicsScene

from rackcore import APP_NAME, FRONT, SIDE_LABEL, Rack

from . import APP_AUTHOR, APP_VERSION
from .scene import build_scene
from .theme import INK, RACK_INK

PNG_SCALES = {"Normal (1×)": 1.0, "Hoch (2×)": 2.0, "Sehr hoch (4×)": 4.0}


class _PrintInk:
    """Druckfreundliche (helle) Farben während des Exports."""

    def __enter__(self):
        INK.update(RACK_INK["print"])

    def __exit__(self, *exc):
        INK.update(RACK_INK["screen"])


def _scene(rack: Rack, side: str, side_label: bool, power: bool = False):
    scene = QGraphicsScene()
    build_scene(scene, rack, "", side, show_other=False, profile=False, side_label=side_label,
                footer=rack.power_summary() if power else "")
    return scene, scene.itemsBoundingRect().adjusted(-4, -4, 4, 4)


def _best_layout(writer: QPdfWriter, w: float, h: float) -> QPageLayout:
    """A4 hoch oder quer – je nachdem, wo der Inhalt größer dargestellt wird."""
    a4 = QPageSize(QPageSize.A4)
    margins = QMarginsF(12, 12, 12, 12)
    best = None
    for orient in (QPageLayout.Portrait, QPageLayout.Landscape):
        layout = QPageLayout(a4, orient, margins, QPageLayout.Millimeter)
        page = QRectF(layout.paintRectPixels(writer.resolution()))
        scale = min(page.width() / w, page.height() / h)
        if best is None or scale > best[0] + 1e-9:
            best = (scale, layout)
    return best[1]


def _render_row(painter: QPainter, writer: QPdfWriter, scenes, gap: float):
    total_w = sum(src.width() for _, src in scenes) + gap * (len(scenes) - 1)
    total_h = max(src.height() for _, src in scenes)
    page = QRectF(writer.pageLayout().paintRectPixels(writer.resolution()))
    page.moveTo(0, 0)
    scale = min(page.width() / total_w, page.height() / total_h)
    x = page.left() + (page.width() - total_w * scale) / 2
    for scene, src in scenes:
        size = QSizeF(src.width() * scale, src.height() * scale)
        scene.render(painter, QRectF(QPointF(x, page.top()), size), src, Qt.KeepAspectRatio)
        x += size.width() + gap * scale


def export_pdf(rack: Rack, filename: str, sides=(FRONT,), power: bool = False,
               separate_pages: bool = False):
    """PDF (A4). Bei zwei Seiten stehen Vorder- und Rückseite nebeneinander oder –
    mit ``separate_pages`` – je auf einer eigenen PDF-Seite. Das Seitenformat
    (hoch/quer) wird so gewählt, dass der Schrank möglichst groß ist."""
    sides = [s for s in sides if s in SIDE_LABEL] or [FRONT]
    with _PrintInk():
        scenes = [_scene(rack, s, side_label=True, power=power) for s in sides]
        pages = [[sc] for sc in scenes] if separate_pages else [scenes]
        gap = 40.0

        def size_of(group):
            return (sum(src.width() for _, src in group) + gap * (len(group) - 1),
                    max(src.height() for _, src in group))

        writer = QPdfWriter(filename)
        writer.setTitle(f"{rack.name} – Rackplan")
        writer.setCreator(f"{APP_NAME} {APP_VERSION} ({APP_AUTHOR})")
        writer.setResolution(300)
        writer.setPageLayout(_best_layout(writer, *size_of(pages[0])))
        painter = QPainter(writer)
        try:
            for i, group in enumerate(pages):
                if i:
                    writer.setPageLayout(_best_layout(writer, *size_of(group)))
                    writer.newPage()
                _render_row(painter, writer, group, gap)
        finally:
            painter.end()


def export_png(rack: Rack, filename: str, side: str = FRONT, scale: float = 2.0,
               transparent: bool = False, power: bool = False) -> bool:
    with _PrintInk():
        scene, src = _scene(rack, side, side_label=True, power=power)
        img = QImage(QSize(round(src.width() * scale), round(src.height() * scale)),
                     QImage.Format_ARGB32)
        img.fill(Qt.transparent if transparent else QColor("#ffffff"))
        painter = QPainter(img)
        try:
            painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
            scene.render(painter, QRectF(0, 0, img.width(), img.height()), src)
        finally:
            painter.end()
    return img.save(filename, "PNG")


def export_svg(rack: Rack, filename: str, side: str = FRONT, power: bool = False):
    with _PrintInk():
        scene, src = _scene(rack, side, side_label=True, power=power)
        gen = QSvgGenerator()
        gen.setFileName(filename)
        gen.setSize(QSize(round(src.width()), round(src.height())))
        gen.setViewBox(QRectF(0, 0, src.width(), src.height()))
        gen.setTitle(f"{rack.name} – {SIDE_LABEL[side]}")
        gen.setDescription(f"Erstellt mit {APP_NAME} {APP_VERSION}")
        painter = QPainter(gen)
        try:
            painter.fillRect(QRectF(0, 0, src.width(), src.height()), QColor("#ffffff"))
            scene.render(painter, QRectF(0, 0, src.width(), src.height()), src)
        finally:
            painter.end()
