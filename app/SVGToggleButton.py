from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QSize, Qt, QRectF

class SVGToggleButton(QPushButton):
    def __init__(self, svg_files, parent=None):
        super().__init__(parent)
        # Initialize a dictionary to store QSvgRenderer instances for each SVG
        self.svg_renderers = {key: QSvgRenderer(svg_path) for key, svg_path in svg_files.items()}
        self.current_svg = next(iter(self.svg_renderers.keys()))  # Default to the first key
        self.pixmaps = {}
        self.render_svgs()

    def render_svgs(self):
        for key, renderer in self.svg_renderers.items():
            pixmap = QPixmap(self.size())
            pixmap.fill(Qt.GlobalColor.transparent)  # Ensure transparent background for SVG, note the enum change
            painter = QPainter(pixmap)
            rect = QRectF(pixmap.rect())  # Convert QRect to QRectF
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
        self.render_svgs()  # Re-render SVGs when button size changes
        super().resizeEvent(event)