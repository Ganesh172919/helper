"""Search, rename, and open saved local conversations without loading every message into Qt."""

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
import sqlite3
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from maya.core.types import MayaError
from .widgets import button, label


class HistoryDialog(QDialog):
    """A bounded text search over local titles and messages; screenshots remain in memory only."""

    chat_deleted = pyqtSignal(int)

    def __init__(self, history, parent=None):
        """Build the searchable list and debounce queries while the user types."""
        super().__init__(parent)
        self.history = history
        self.chosen = None
        self.setWindowTitle("Conversation history — Maya")
        self.resize(500, 460)
        box = QVBoxLayout(self)
        box.addWidget(label("Conversations on this laptop", "heading"))
        self.search = QLineEdit()
        self.search.setMaxLength(200)
        self.search.setPlaceholderText("Search titles and messages")
        self.search.setClearButtonEnabled(True)
        box.addWidget(self.search)
        self.listing = QListWidget()
        box.addWidget(self.listing, 1)
        self.summary = label("")
        box.addWidget(self.summary)
        row = QHBoxLayout()
        self.rename_button = button("Rename", self.rename)
        self.delete_button = button("Delete", self.delete)
        self.open_button = button("Open", self.open_selected, True)
        row.addWidget(self.rename_button)
        row.addWidget(self.delete_button)
        row.addStretch()
        row.addWidget(button("Close", self.reject))
        row.addWidget(self.open_button)
        box.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda: self.timer.start())
        self.listing.currentItemChanged.connect(self.sync_actions)
        self.listing.itemDoubleClicked.connect(self.open_selected)
        self.reload()

    def reload(self, selected: int | None = None) -> None:
        """Keep the selection if still visible and show a clear empty/capped search result."""
        self.timer.stop()
        item = self.listing.currentItem()
        selected = selected if selected is not None else item.data(Qt.UserRole) if item else None
        self.listing.clear()
        try:
            chats = self.history.chats(self.search.text())
        except (sqlite3.Error, OSError):
            self.summary.setText(
                "Could not read local history. Check disk space/permissions, then reopen History."
            )
            self.sync_actions()
            return
        for chat in chats:
            item = QListWidgetItem(chat["title"])
            item.setData(Qt.UserRole, chat["id"])
            self.listing.addItem(item)
            if chat["id"] == selected:
                self.listing.setCurrentItem(item)
        count = self.listing.count()
        self.summary.setText(
            "No matching conversations."
            if not count
            else "Showing the newest 200 matches. Refine your search to find older conversations."
            if count == 200
            else f"{count} saved conversation{'s' if count != 1 else ''}"
        )
        if count and self.listing.currentRow() < 0:
            self.listing.setCurrentRow(0)
        self.sync_actions()

    def sync_actions(self, *args) -> None:
        """Disable actions when a search has no result instead of silently doing nothing."""
        enabled = self.listing.currentItem() is not None
        for widget in (self.open_button, self.rename_button, self.delete_button):
            widget.setEnabled(enabled)

    def open_selected(self, *args) -> None:
        """Return just the chosen local ID; the controller owns the shared conversation state."""
        if item := self.listing.currentItem():
            self.chosen = item.data(Qt.UserRole)
            self.accept()

    def rename(self) -> None:
        """Apply an explicit title edit, validating before any database mutation."""
        item = self.listing.currentItem()
        if not item:
            return
        title, accepted = QInputDialog.getText(self, "Rename conversation", "New title:", text=item.text())
        if accepted:
            try:
                identifier = item.data(Qt.UserRole)
                self.history.rename_chat(identifier, title)
                self.reload(identifier)
            except MayaError as exc:
                QMessageBox.information(self, "History", str(exc))
            except (sqlite3.Error, OSError):
                QMessageBox.information(
                    self, "History", "Could not rename this conversation. Check the local data folder."
                )

    def delete(self) -> None:
        """Confirm and erase one conversation and dependent feedback, never an entire search result."""
        item = self.listing.currentItem()
        if (
            item
            and QMessageBox.question(self, "Delete conversation", "Delete this saved local conversation?")
            == QMessageBox.Yes
        ):
            identifier = item.data(Qt.UserRole)
            try:
                self.history.delete_chat(identifier)
                self.chat_deleted.emit(identifier)
                self.reload()
            except (sqlite3.Error, OSError):
                QMessageBox.information(
                    self, "History", "Could not delete this conversation. Check the local data folder."
                )
