"""Consistent SVG icon primitives rendered by Qt's PySide6 bindings."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QWidget


ICON_PATHS: dict[str, str] = {
    "upload": "M4 17.5a3 3 0 0 1 .6-5.9A5.5 5.5 0 0 1 15 9.5a4 4 0 0 1 4.4 6 M12 18V8.5 M8.7 11.8 12 8.5l3.3 3.3",
    "folder": "M3.5 7.5h6l2-2h9v12.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z",
    "info": "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z M12 10.5v5 M12 7.5h.01",
    "gear": "M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6z M12 3.5v2 M12 18.5v2 M3.5 12h2 M18.5 12h2 M6 6l1.4 1.4 M16.6 16.6L18 18 M18 6l-1.4 1.4 M7.4 16.6L6 18",
    "file": "M6 3.5h8l4 4v13H6z M14 3.5v4h4 M9 12h6 M9 15.5h6",
    "waveform": "M4 12v0 M8 9v6 M12 5v14 M16 8v8 M20 10v4",
    "chevron_down": "M7 9l5 5 5-5",
    "chevron_right": "M9 6l6 6-6 6",
}


def svg_icon(kind: str, color: str = "#52627a", size: int = 24) -> QIcon:
    """Return a crisp, monochrome QIcon backed by an inline SVG."""
    try:
        path = ICON_PATHS[kind]
    except KeyError as error:  # pragma: no cover - programming contract guard
        raise ValueError(f"Unknown icon kind: {kind}") from error
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24">
      <path d="{path}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>'''
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class IconLabel(QLabel):
    """A fixed-size QLabel for icons that belong in a layout."""

    def __init__(
        self,
        kind: str,
        color: str = "#52627a",
        size: int = 24,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setPixmap(svg_icon(kind, color, size).pixmap(size, size))
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
