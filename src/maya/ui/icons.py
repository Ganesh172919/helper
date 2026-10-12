"""Small native line icons with consistent strokes instead of platform-dependent emoji glyphs."""

from functools import lru_cache

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


@lru_cache(maxsize=8)
def line_icon(name: str) -> QIcon:
    """Draw restrained UI symbols at two scales; callers supply readable names and tooltips."""
    if name not in {"navigation", "settings", "close"}:
        raise ValueError("Unknown Maya line icon")
    icon = QIcon()
    for size in (16, 32):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size / 24, size / 24)
        painter.setPen(QPen(QColor("#375b51"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if name == "navigation":
            painter.drawRoundedRect(QRectF(3, 4, 18, 16), 3, 3)
            painter.drawLine(QPointF(9, 4), QPointF(9, 20))
            painter.drawLine(QPointF(13, 9), QPointF(17, 9))
            painter.drawLine(QPointF(13, 14), QPointF(17, 14))
        elif name == "settings":
            # Three familiar slider rails read clearly even in a small laptop header.
            for x, y in ((6, 9), (12, 15), (18, 8)):
                painter.drawLine(QPointF(x, 4), QPointF(x, 20))
                painter.setBrush(QColor("#faf8f2"))
                painter.drawEllipse(QPointF(x, y), 2.4, 2.4)
        else:
            painter.drawLine(QPointF(7, 7), QPointF(17, 17))
            painter.drawLine(QPointF(17, 7), QPointF(7, 17))
        painter.end()
        icon.addPixmap(pixmap)
    return icon
