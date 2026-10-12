"""Opt-in local clipboard overlay adapting the supplied Win32 viewer to Maya's Qt lifecycle."""

import hashlib

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QCheckBox, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from maya.core.safety import redact
from .widgets import button, label


class ClipboardWindow(QWidget):
    """Topmost, translucent text viewer; watching is session-only and never calls an AI provider."""

    def __init__(self, controller, clipboard=None):
        """Qt's native Windows clipboard notifications replace unsafe raw memory/GDI ownership."""
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.controller = controller
        self.clipboard = clipboard or QApplication.clipboard()
        self.connected = False
        self.digest = ""
        self.setWindowTitle("Maya — local clipboard")
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowOpacity(215 / 255)
        self.resize(480, 320)
        self.setMinimumSize(360, 240)
        box = QVBoxLayout(self)
        row = QHBoxLayout()
        self.watch = QCheckBox("Watch copied text")
        self.watch.toggled.connect(self.set_watching)
        row.addWidget(self.watch)
        row.addStretch()
        row.addWidget(button("Close", self.close))
        box.addLayout(row)
        box.addWidget(label("Local preview only · Use in chat adds a draft; Send is a separate action."))
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.installEventFilter(self)
        self.viewer.setPlaceholderText("Turn on Watch copied text to preview your clipboard here.")
        self.viewer.setStyleSheet(
            "QPlainTextEdit { background: #263f38; color: #ffffff; font: 15px 'Segoe UI'; border-radius: 8px; padding: 10px; }"
        )
        box.addWidget(self.viewer, 1)
        footer = QHBoxLayout()
        self.state = label("Watching OFF", "eyebrow")
        footer.addWidget(self.state, 1)
        self.use_button = button("Use in chat", self.use_in_chat)
        self.use_button.setEnabled(False)
        footer.addWidget(self.use_button)
        box.addLayout(footer)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(80)
        self.debounce.timeout.connect(self.read_clipboard)

    def set_watching(self, enabled: bool) -> None:
        """Subscribe only while explicitly enabled and visible; turning OFF clears all viewer content."""
        allowed = enabled and self.isVisible() and not self.controller.paused and not self.controller.quitting
        if not allowed:
            if self.connected:
                self.clipboard.dataChanged.disconnect(self.schedule_read)
                self.connected = False
            self.debounce.stop()
            self.viewer.clear()
            self.digest = ""
            self.use_button.setEnabled(False)
            self.state.setText("Watching OFF")
            if self.watch.isChecked():
                self.watch.setChecked(False)
            return
        if not self.connected:
            self.clipboard.dataChanged.connect(self.schedule_read)
            self.connected = True
        self.schedule_read()

    def schedule_read(self) -> None:
        """Coalesce a burst of notifications into one UI update without a polling loop."""
        if self.connected:
            self.debounce.start()

    def read_clipboard(self) -> None:
        """Display bounded plain text, mask recognizable secrets and handle empty/non-text content."""
        if not self.connected or not self.isVisible():
            return
        try:
            mime = self.clipboard.mimeData()
            value = mime.text() if mime is not None and mime.hasText() else ""
        except (RuntimeError, OSError):
            self.state.setText("Clipboard busy · copy again to retry")
            self.viewer.clear()
            self.digest = ""
            self.use_button.setEnabled(False)
            return
        limited = len(value) > 100000
        text, masked = redact(value[:100000].replace("\x00", ""))
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        if digest != self.digest:
            self.digest = digest
            self.viewer.setPlainText(text)  # Plain text: clipboard HTML never executes or renders links.
            self.viewer.verticalScrollBar().setValue(0)
        self.use_button.setEnabled(bool(text.strip()))
        self.state.setText(
            "Watching ON · "
            + (
                "text shortened to 100,000 characters"
                if limited
                else "recognizable secrets masked"
                if masked
                else "copied text"
                if text
                else "no text copied"
            )
        )

    def use_in_chat(self) -> None:
        """Explicitly move the reviewed text to the shared draft; never submit or save it automatically."""
        value = self.viewer.toPlainText()
        if not value.strip():
            return
        self.controller.set_question((self.controller.question + "\n" + value).strip()[:200000])
        self.controller.show_normal()
        self.close()

    def scroll_text(self, delta: int) -> None:
        """Keep the reference's global Alt+Shift+Up/Down scrolling while focus remains in another app."""
        bar = self.viewer.verticalScrollBar()
        bar.setValue(bar.value() + delta)

    def keyPressEvent(self, event) -> None:
        """Escape closes and disables watching; native editor keys handle arrows/PageUp/Home/End."""
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, watched, event) -> bool:
        """Preserve the reference's arrow/page/home/end scrolling when the viewer is focused."""
        if watched is self.viewer and event.type() == QEvent.KeyPress and not event.modifiers():
            bar = self.viewer.verticalScrollBar()
            steps = {
                Qt.Key_Up: -1,
                Qt.Key_Down: 1,
                Qt.Key_PageUp: -bar.pageStep(),
                Qt.Key_PageDown: bar.pageStep(),
            }
            if event.key() in steps:
                self.scroll_text(steps[event.key()])
                return True
            if event.key() in {Qt.Key_Home, Qt.Key_End}:
                bar.setValue(bar.minimum() if event.key() == Qt.Key_Home else bar.maximum())
                return True
            if event.key() == Qt.Key_Escape:
                self.close()
                return True
        return super().eventFilter(watched, event)

    def hideEvent(self, event) -> None:
        """Hiding, closing or quitting always detaches notifications and discards the local preview."""
        self.set_watching(False)
        super().hideEvent(event)
