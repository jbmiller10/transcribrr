import os
import logging
from typing import Optional

from app.path_utils import resource_path

try:  # pragma: no cover - exercised in packaged app
    from PyQt6.QtGui import QIcon, QPixmap
    from PyQt6.QtCore import QSize, QRectF, Qt
    try:
        from PyQt6.QtSvg import QSvgRenderer  # type: ignore
    except Exception:  # QtSvg may be missing in some runtimes
        QSvgRenderer = None  # type: ignore
except Exception:  # pragma: no cover
    # Minimal stubs for test import; tests don't render icons
    QIcon = object  # type: ignore
    QPixmap = object  # type: ignore
    QSize = object  # type: ignore
    QSvgRenderer = None  # type: ignore

logger = logging.getLogger("transcribrr")


def _render_svg_to_pixmap(svg_path: str, size: int = 32):
    """Render an SVG into a QPixmap of a given size.

    Returns None if QtSvg is unavailable or rendering fails.
    """
    if QSvgRenderer is None:  # QtSvg not available
        return None
    try:
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return None
        pm = QPixmap(size, size)
        # Transparent background
        try:
            pm.fill(Qt.GlobalColor.transparent)
        except Exception:
            # Fallback if Qt namespace differs
            pm.fill(0)
        from PyQt6.QtGui import QPainter

        p = QPainter(pm)
        # Render into the full pixmap rect to ensure scaling
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        return pm
    except Exception as e:
        logger.debug(f"SVG render failed for {svg_path}: {e}")
        return None


def load_icon(path: str, *, size: int = 32) -> "QIcon":
    """Load an icon from a relative or absolute path with SVG fallback.

    - Resolves relative paths through resource_path().
    - If loading an SVG and QIcon cannot load via plugins, renders with QSvgRenderer.
    - Returns an empty QIcon if the path does not exist.
    """
    abs_path = path if os.path.isabs(path) else resource_path(path)

    if not os.path.exists(abs_path):
        logger.warning(f"Icon path does not exist: {abs_path}")
        try:
            return QIcon()  # type: ignore
        except Exception:
            return QIcon  # type: ignore

    # Try native QIcon loading first
    try:
        icon = QIcon(abs_path)  # type: ignore
        # If it's a non-SVG or the icon loaded, return it
        if not abs_path.lower().endswith(".svg") or not getattr(icon, "isNull", lambda: False)():
            return icon
    except Exception:
        # Fall through to SVG rendering below
        pass

    # Attempt manual SVG rendering
    pm = _render_svg_to_pixmap(abs_path, size=size)
    if pm is not None:
        try:
            ic = QIcon(pm)  # type: ignore
            return ic
        except Exception:
            pass

    # Last resort: return whatever QIcon() yields (likely null)
    try:
        return QIcon(abs_path)  # type: ignore
    except Exception:
        return QIcon  # type: ignore
