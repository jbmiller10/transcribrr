from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import Qt, QRectF


class SVGToggleButton(QPushButton):
    def __init__(self, svg_files, parent=None):
        super().__init__(parent)
        self.svg_renderers = {key: QSvgRenderer(svg_path) for key, svg_path in svg_files.items()}
        self.current_svg = next(iter(self.svg_renderers.keys()))
        self.pixmaps = {}
        self.render_svgs()

    def render_svgs(self):
        for key, renderer in self.svg_renderers.items():
            pixmap = QPixmap(self.size())
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            rect = QRectF(pixmap.rect())
            renderer.render(painter, rect)
            painter.end()
            self.pixmaps[key] = pixmap

    def set_svg(self, key):
        if key in self.svg_renderers:
            self.current_svg = key
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.current_svg in self.pixmaps:
            pixmap = self.pixmaps[self.current_svg]
            painter.drawPixmap(self.rect(), pixmap)
        painter.end()

    def resizeEvent(self, event):
        self.render_svgs()
        super().resizeEvent(event)
