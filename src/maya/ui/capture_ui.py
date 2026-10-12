"""Local screenshot review, black-box redaction, and per-monitor region selection."""

from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout
from PIL import ImageDraw

from .widgets import button, label


# --- Redaction maps displayed preview coordinates to original image pixels. ---
class RedactionCanvas(QLabel):
    """Fit an image to the available area; drag to black out sensitive regions permanently in the pending copy."""

    def __init__(self, image, editable: bool):
        """Retain an independent image; a discard never modifies the original captured pixels."""
        super().__init__()
        self.image = image.copy().convert("RGB")
        self.refresh_pixmap()
        self.editable = editable
        self.start = None
        self.end = None
        self.draw_rect = QRect()
        self.setMinimumSize(380, 220)
        self.setCursor(Qt.CrossCursor if editable else Qt.ArrowCursor)
        self.setAlignment(Qt.AlignCenter)

    def refresh_pixmap(self) -> None:
        """Decode the preview only after pixels change, avoiding full PNG encoding on every drag event."""
        from io import BytesIO

        stream = BytesIO()
        self.image.save(stream, "PNG")
        self.pixmap = QPixmap()
        self.pixmap.loadFromData(stream.getvalue())

    def paintEvent(self, event) -> None:
        """Paint a letterboxed preview and current rectangle without scaling image coordinates incorrectly."""
        fit = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.draw_rect = QRect(
            (self.width() - fit.width()) // 2, (self.height() - fit.height()) // 2, fit.width(), fit.height()
        )
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#e6e9df"))
        painter.drawPixmap(self.draw_rect.topLeft(), fit)
        if self.start is not None and self.end is not None:
            painter.setPen(QPen(QColor("#e6b958"), 2))
            painter.drawRect(QRect(self.start, self.end).normalized())

    def mousePressEvent(self, event) -> None:
        """Begin an explicit redaction only inside the displayed image."""
        if self.editable and event.button() == Qt.LeftButton and self.draw_rect.contains(event.pos()):
            self.start = self.end = event.pos()
            self.update()

    def mouseMoveEvent(self, event) -> None:
        """Update the user-drawn box; final mapping is clipped to the image."""
        if self.start is not None:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        """Black out the selected source pixels so hidden data is removed from the actual outbound image."""
        if self.start is None or self.draw_rect.width() <= 0:
            return
        selected = QRect(self.start, event.pos()).normalized().intersected(self.draw_rect)
        if selected.width() > 2 and selected.height() > 2:
            sx, sy = self.image.width / self.draw_rect.width(), self.image.height / self.draw_rect.height()
            bounds = (
                int((selected.left() - self.draw_rect.left()) * sx),
                int((selected.top() - self.draw_rect.top()) * sy),
                int((selected.right() - self.draw_rect.left() + 1) * sx),
                int((selected.bottom() - self.draw_rect.top() + 1) * sy),
            )
            ImageDraw.Draw(self.image).rectangle(bounds, fill="black")
            self.refresh_pixmap()
        self.start = self.end = None
        self.update()


class ImagePreview(QDialog):
    """Preview is a mandatory step before any newly captured image becomes sendable."""

    def __init__(self, image, editable: bool = True, parent=None):
        """Show image and outbound-data explanation; attached images remain editable until accepted."""
        super().__init__(parent)
        self.setWindowTitle("Review screenshot — Maya")
        self.resize(880, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Review your screen context", "heading"))
        layout.addWidget(
            label(
                "Drag a box to black out private information. This image is sent to the selected provider only when you press Send."
                if editable
                else "This is the in-memory screenshot attached to this turn."
            )
        )
        self.canvas = RedactionCanvas(image, editable)
        layout.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        row.addWidget(label(f"{image.width} × {image.height} pixels · stored in memory only"))
        row.addStretch()
        row.addWidget(button("Discard" if editable else "Close", self.reject))
        if editable:
            row.addWidget(button("Attach screenshot", self.accept, True))
        layout.addLayout(row)


# --- Region selection shows the frozen monitor image; no continuous screen recording occurs. ---
class RegionSelector(QDialog):
    """Drag-select on a single current monitor, mapping its Qt logical space to captured physical pixels."""

    def __init__(self, image, screen, parent=None):
        """Use per-screen geometry so mixed DPI does not depend on one virtual-desktop scale factor."""
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.image = image
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CrossCursor)
        self.start = None
        self.end = None
        self.selected = None
        from io import BytesIO

        buffer = BytesIO()
        image.save(buffer, "PNG")
        self.pixmap = QPixmap()
        self.pixmap.loadFromData(buffer.getvalue())

    def paintEvent(self, event) -> None:
        """Draw a frozen image with a dim mask and live region dimensions."""
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)
        painter.fillRect(self.rect(), QColor(10, 26, 23, 115))
        painter.setPen(QPen(QColor("#f0cd7a"), 2))
        if self.start is not None and self.end is not None:
            rect = QRect(self.start, self.end).normalized()
            painter.drawRect(rect)
            painter.drawText(rect.topLeft() + QPoint(0, -8), f"{rect.width()} × {rect.height()}")
        painter.setPen(QColor("#ffffff"))
        painter.drawText(25, 35, "Drag a region on this monitor · Esc to cancel")

    def mousePressEvent(self, event) -> None:
        """Start selection with the left mouse button."""
        if event.button() == Qt.LeftButton:
            self.start = self.end = event.pos()

    def mouseMoveEvent(self, event) -> None:
        """Keep the selection within this monitor's visible bounds."""
        if self.start is not None:
            self.end = QPoint(max(0, min(self.width(), event.x())), max(0, min(self.height(), event.y())))
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        """Return a physical-pixel crop; tiny selections cancel without attaching an image."""
        if self.start is None:
            return
        rect = QRect(self.start, event.pos()).normalized().intersected(self.rect())
        if rect.width() < 8 or rect.height() < 8:
            self.reject()
            return
        sx, sy = self.image.width / self.width(), self.image.height / self.height()
        self.selected = self.image.crop(
            (
                int(rect.left() * sx),
                int(rect.top() * sy),
                int((rect.right() + 1) * sx),
                int((rect.bottom() + 1) * sy),
            )
        )
        self.accept()

    def keyPressEvent(self, event) -> None:
        """Cancel the capture workflow on Escape without submitting or changing the pending image."""
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
