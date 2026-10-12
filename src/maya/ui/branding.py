"""Maya's original sculpted flower mark: shaded vector painting, no GPU or downloaded assets."""

import math

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt5.QtWidgets import QWidget
from .text import safe_tooltip


def paint_maya(
    painter: QPainter, bounds: QRectF, pulse: float = 1, tilt: float = 0, glow: float = 0.35
) -> None:
    """Paint luminous ceramic petals, a beveled jade base and a contained, feathered halo.

    Lighting gives a 3D appearance using ordinary Qt vector drawing. Keeping geometry normalized
    makes the same original mark work in the title, tray, taskbar and floating orb without OpenGL.
    """
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    side = min(bounds.width(), bounds.height())
    painter.translate(bounds.center())
    painter.scale(side / 100, side / 100)
    painter.rotate(tilt)
    painter.setPen(Qt.NoPen)
    glow = max(0.0, min(1.0, glow))

    # The halo fades inside the widget bounds, keeping transparent corners at every icon size.
    halo = QRadialGradient(QPointF(0, 0), 49)
    halo.setColorAt(0, QColor(249, 204, 111, int(90 + glow * 100)))
    halo.setColorAt(0.64, QColor(244, 193, 93, int(40 + glow * 75)))
    halo.setColorAt(0.84, QColor(236, 180, 82, int(glow * 68)))
    halo.setColorAt(1, QColor(236, 180, 82, 0))
    painter.setBrush(halo)
    painter.drawEllipse(QRectF(-49, -49, 98, 98))

    # A contact shadow and a thick lower bevel give the small mark actual visual depth.
    shadow = QRadialGradient(QPointF(0, 29), 32)
    shadow.setColorAt(0, QColor(15, 40, 35, 115))
    shadow.setColorAt(1, QColor(15, 40, 35, 0))
    painter.setBrush(shadow)
    painter.drawEllipse(QRectF(-35, 16, 70, 29))
    rim = QLinearGradient(-28, -28, 22, 37)
    rim.setColorAt(0, QColor("#c2dacf"))
    rim.setColorAt(0.3, QColor("#386e61"))
    rim.setColorAt(1, QColor("#102f29"))
    painter.setBrush(rim)
    painter.drawEllipse(QRectF(-35, -29, 70, 68))
    enamel = QLinearGradient(-24, -33, 19, 32)
    enamel.setColorAt(0, QColor("#91c8b3"))
    enamel.setColorAt(0.38, QColor("#447f6d"))
    enamel.setColorAt(0.78, QColor("#245346"))
    enamel.setColorAt(1, QColor("#15392f"))
    painter.setBrush(enamel)
    painter.drawEllipse(QRectF(-35, -35, 70, 65))

    # Shaped petals have a side wall, softly rounded face and reflected light rather than flat ovals.
    petal_shape = QPainterPath(QPointF(0, 7))
    petal_shape.cubicTo(-14, 3, -20, -11, -12, -25)
    petal_shape.cubicTo(-5, -37, 10, -33, 14, -22)
    petal_shape.cubicTo(20, -7, 12, 4, 0, 7)
    for index in range(6):
        painter.save()
        painter.rotate(index * 60 + 12)
        painter.translate(0, -9 * pulse)
        painter.translate(1.5, 3)
        painter.setBrush(QColor("#9e6c34"))
        painter.drawPath(petal_shape)
        painter.translate(-1.5, -3)
        petal = QLinearGradient(-13, -29, 12, 6)
        petal.setColorAt(0, QColor("#fffbe5"))
        petal.setColorAt(0.36, QColor("#f9e6af" if index % 2 else "#f3da96"))
        petal.setColorAt(0.74, QColor("#dfb56c"))
        petal.setColorAt(1, QColor("#b58340"))
        painter.setBrush(petal)
        painter.setPen(QPen(QColor(255, 248, 216, 120), 0.65))
        painter.drawPath(petal_shape)
        painter.setPen(Qt.NoPen)
        reflection = QRadialGradient(QPointF(-4, -22), 13)
        reflection.setColorAt(0, QColor(255, 255, 238, 155))
        reflection.setColorAt(1, QColor(255, 255, 238, 0))
        painter.setBrush(reflection)
        painter.drawEllipse(QRectF(-13, -31, 19, 20))
        painter.restore()
    center = QRadialGradient(QPointF(-4, -5), 14)
    center.setColorAt(0, QColor("#ffffff"))
    center.setColorAt(0.5, QColor("#fff4c9"))
    center.setColorAt(1, QColor("#cc9e51"))
    painter.setBrush(center)
    painter.drawEllipse(QRectF(-11, -11, 22, 22))
    light = QRadialGradient(QPointF(-2, -3), 21)
    light.setColorAt(0, QColor(255, 241, 181, int(30 + glow * 75)))
    light.setColorAt(1, QColor(255, 223, 135, 0))
    painter.setBrush(light)
    painter.drawEllipse(QRectF(-21, -22, 42, 42))
    painter.setBrush(QColor(255, 255, 255, 190))
    painter.drawEllipse(QRectF(-6, -7, 6, 4))

    # A small curved sheen suggests ceramic/enamel rather than a generic glossy sphere.
    sheen = QPainterPath()
    sheen.moveTo(-29, -18)
    sheen.cubicTo(-23, -28, -15, -33, -6, -32)
    sheen.cubicTo(-16, -28, -22, -25, -29, -18)
    painter.setBrush(QColor(255, 255, 255, 85))
    painter.drawPath(sheen)
    painter.restore()


def maya_icon() -> QIcon:
    """Supply actual small/large icon sizes so Windows does not blur one oversized bitmap."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        paint_maya(painter, QRectF(0, 0, size, size))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class MayaMark(QWidget):
    """A luminous sculpted mark: static at rest, gentle breathing only during visible work."""

    def __init__(self, size: int = 44):
        """Create an accessible, lightweight brand mark without taking keyboard focus."""
        super().__init__()
        self.setFixedSize(size, size)
        self.setAccessibleName("Maya glowing sculpted flower icon")
        self.setToolTip("Maya the Helper · here when you need a hand")
        self.setFocusPolicy(Qt.NoFocus)
        self.phase = 0.0
        self.active = False
        self.motion_reduced = False
        self.hovered = False
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.animate)

    def set_state(self, state: str, text: str = "") -> None:
        """Animate only during capture, classification or streaming and preserve a text status."""
        self.active = state in {"capturing", "thinking", "streaming"}
        safe_tooltip(self, "Maya · " + (text or state))
        self.sync_timer()
        self.update()

    def sync_timer(self) -> None:
        """An invisible header consumes no animation wakeups, even while the other surface streams."""
        if self.active and self.isVisible() and not self.motion_reduced:
            self.timer.start()
        else:
            self.timer.stop()

    def set_motion_reduced(self, reduced: bool) -> None:
        """Stop decorative motion immediately while preserving activity status and a constant glow."""
        self.motion_reduced = reduced
        self.phase = 0.0
        self.sync_timer()
        self.update()

    def animate(self) -> None:
        """Bound the phase; modest motion avoids distracting from the application underneath."""
        self.phase = (self.phase + 0.2) % math.tau
        self.update()

    def paintEvent(self, event) -> None:
        """Keep painter lifetime local to repaint so resizing and shutdown release resources safely."""
        painter = QPainter(self)
        paint_maya(
            painter,
            QRectF(self.rect()),
            1 + (math.sin(self.phase) * 0.035 if self.active and not self.motion_reduced else 0),
            -5 if self.hovered else 0,
            0.7 + math.sin(self.phase) * 0.2 if self.active else (0.65 if self.hovered else 0.35),
        )

    def enterEvent(self, event) -> None:
        """A small tilt acknowledges pointer hover without a continuous idle animation."""
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Return to the resting pose immediately when the pointer leaves."""
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def showEvent(self, event) -> None:
        """Resume only an already-active bloom when this surface becomes visible."""
        super().showEvent(event)
        self.sync_timer()

    def hideEvent(self, event) -> None:
        """Stop animation while hidden, including during screenshot hide/capture/restore."""
        self.timer.stop()
        super().hideEvent(event)
