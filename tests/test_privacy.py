"""Memory reset and native capture privacy have explicit, observable boundaries."""

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtWidgets import QDialog, QMenu, QMessageBox, QWidget
import sqlite3

from maya.core.config import Settings
from maya.core.storage import HistoryStore
from maya.core.types import Message
from maya.platform.secrets import SecretStore
from maya.ui.privacy import CaptureGuard
from maya.ui.settings import SettingsDialog


def test_empty_install_and_clear_memories_preserve_chats(tmp_path):
    history = HistoryStore(tmp_path / "test.db")
    settings = Settings()
    assert history.memories() == [] and settings.display_name == "" and not settings.custom_profiles
    chat = history.create_chat("Synthetic conversation")
    history.add_message(chat, Message("user", "A synthetic question"))
    history.remember("Use concise explanations", "general")
    history.remember("Prefer Python examples", "python")
    history.clear_memories()
    assert history.memories() == [] and history.relevant_memories("Python", "python") == []
    assert len(history.chats()) == 1
    history.clear_memories()  # Already-empty resets remain safe.
    history.remember("A new preference", "general")
    assert len(history.memories()) == 1


def test_forget_all_confirmation_cancel_and_accept(qapp, tmp_path, monkeypatch):
    history = HistoryStore(tmp_path / "test.db")
    history.remember("Synthetic preference", "general")
    dialog = SettingsDialog(Settings(), SecretStore(enabled=False), history, tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    dialog.forget_all_memories()
    assert len(history.memories()) == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    dialog.forget_all_memories()
    assert history.memories() == [] and dialog.memory_list.count() == 0
    dialog.deleteLater()
    qapp.processEvents()


def test_memory_empty_state_and_failed_clear_preserve_selection_and_draft(qapp, tmp_path, monkeypatch):
    history = HistoryStore(tmp_path / "test.db")
    dialog = SettingsDialog(Settings(), SecretStore(enabled=False), history, tmp_path)
    assert "No saved memories" in dialog.memory_summary.text()
    assert not dialog.forget_all_button.isEnabled() and not dialog.forget_memory_button.isEnabled()
    dialog.memory_text.setText("Use concise examples")
    dialog.add_memory()
    assert "1 saved memory" in dialog.memory_summary.text() and dialog.forget_all_button.isEnabled()
    dialog.memory_list.setCurrentRow(0)
    assert dialog.update_memory_button.isEnabled() and dialog.forget_memory_button.isEnabled()
    original = history.clear_memories

    def fail():
        raise sqlite3.OperationalError("synthetic disk failure with private details")

    notices = []
    monkeypatch.setattr(history, "clear_memories", fail)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: notices.append(args[2]))
    dialog.forget_all_memories()
    assert len(history.memories()) == 1 and dialog.memory_list.currentRow() == 0
    assert dialog.memory_text.text() == "Use concise examples" and "private details" not in notices[0]
    monkeypatch.setattr(history, "clear_memories", original)
    dialog.forget_all_memories()
    assert not history.memories() and "No saved memories" in dialog.memory_summary.text()
    assert not dialog.forget_all_button.isEnabled() and not dialog.update_memory_button.isEnabled()
    dialog.deleteLater()
    qapp.processEvents()


def test_memory_reload_failure_has_no_false_empty_state(qapp, tmp_path, monkeypatch):
    history = HistoryStore(tmp_path / "test.db")
    dialog = SettingsDialog(Settings(), SecretStore(enabled=False), history, tmp_path)
    history.remember("Synthetic preference", "general")
    dialog.reload_memory()
    assert dialog.forget_all_button.isEnabled()

    def fail():
        raise sqlite3.OperationalError("synthetic private path")

    monkeypatch.setattr(history, "memories", fail)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    dialog.reload_memory()
    assert "could not be loaded" in dialog.memory_summary.text()
    assert not dialog.forget_all_button.isEnabled() and not dialog.update_memory_button.isEnabled()
    dialog.deleteLater()
    qapp.processEvents()


class SyntheticDesktop:
    """No Windows calls are made by popup lifecycle tests."""

    def __init__(self):
        self.calls = []
        self.accepted = True
        self.affinity = 0x11

    def exclude_capture(self, handle):
        self.calls.append(handle)
        return self.accepted

    def capture_affinity(self, handle):
        return self.affinity


def test_guard_covers_dialog_menu_handle_changes_and_stops(qapp):
    desktop = SyntheticDesktop()
    guard = CaptureGuard(desktop)
    dialog = QDialog()
    dialog.setWindowTitle("Synthetic settings")
    menu = QMenu()
    menu.addAction("Synthetic action")
    child = QWidget(dialog)
    try:
        guard.start()
        dialog.show()
        qapp.processEvents()
        assert dialog.property("maya_capture_verified")
        # Menus and replacement handles use the same path as ordinary windows.
        assert guard.eventFilter(menu, QEvent(QEvent.Show)) is False
        assert menu.property("maya_capture_verified")
        calls = len(desktop.calls)
        guard.eventFilter(dialog, QEvent(QEvent.WinIdChange))
        assert len(desktop.calls) == calls + 1
        guard.eventFilter(child, QEvent(QEvent.Show))
        assert len(desktop.calls) == calls + 1
        assert "Windows exclusion confirmed" in guard.report()
        guard.stop()
        dialog.hide()
        calls = len(desktop.calls)
        dialog.show()
        qapp.processEvents()
        assert len(desktop.calls) == calls
    finally:
        guard.stop()
        for widget in (dialog, menu):
            widget.hide()
            widget.deleteLater()
        qapp.processEvents()


def test_guard_reports_failed_and_unverified_requests_without_false_guarantees(qapp):
    desktop = SyntheticDesktop()
    guard = CaptureGuard(desktop)
    window = QWidget(None, Qt.Tool)
    window.setWindowTitle("Synthetic reader")
    try:
        window.show()
        desktop.accepted = False
        guard.protect(window)
        assert not window.property("maya_capture_verified")
        assert "exclusion unavailable" in guard.report()
        desktop.accepted = True
        desktop.affinity = None
        guard.protect(window)
        assert window.property("maya_capture_requested") and not window.property("maya_capture_verified")
        assert "read-back unavailable" in guard.report()
        desktop.affinity = 1  # An old Windows monitor-only fallback is not capture exclusion.
        guard.protect(window)
        assert not window.property("maya_capture_verified")
        assert "monitor-only fallback" in guard.report()
    finally:
        window.hide()
        window.deleteLater()
        qapp.processEvents()
