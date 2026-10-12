"""Process-level regression verifies that a second launch cannot mutate an active stream marker."""

import os
import sqlite3
import subprocess
import sys
import time
from textwrap import dedent


def test_second_instance_does_not_recover_running_history(tmp_path):
    """Run two isolated Maya processes and check the single-instance lock precedes SQLite recovery."""
    env = dict(os.environ, MAYA_DATA_DIR=str(tmp_path), QT_QPA_PLATFORM="offscreen")
    process = subprocess.Popen(
        [sys.executable, "-m", "maya", "--no-credentials"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        database = tmp_path / "history.sqlite3"
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not database.exists():
            time.sleep(0.05)
        assert database.exists() and process.poll() is None
        time.sleep(0.2)
        with sqlite3.connect(database) as db:
            db.execute("INSERT INTO chats(id,title,created) VALUES(1,'Synthetic test',0)")
            db.execute(
                "INSERT INTO messages(chat_id,role,text,status,created) VALUES(1,'assistant','partial','streaming',0)"
            )
        second = subprocess.run(
            [sys.executable, "-m", "maya", "--no-credentials"], env=env, capture_output=True, timeout=8
        )
        assert second.returncode == 0
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT status FROM messages").fetchone()[0] == "streaming"
    finally:
        process.terminate()
        process.communicate(timeout=5)


def test_quit_during_generation_saves_partial_and_exits_cleanly(tmp_path):
    """A real Qt subprocess cancels its worker during Quit and persists partial text without a thread destruction crash."""
    script = dedent("""
        from pathlib import Path
        import sys
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication
        from maya.core.config import ConfigStore, Settings
        from maya.core.storage import HistoryStore
        from maya.core.types import Model, StreamEvent
        from maya.platform.secrets import SecretStore
        from maya.ui.app import AppController
        import maya.ui.app as module
        class Provider:
            def stream(self, request, token):
                yield StreamEvent("text", "Synthetic partial")
                while True:
                    token.wait(0.1)
        module.create_provider = lambda *args: Provider()
        qapp = QApplication([])
        qapp.setQuitOnLastWindowClosed(False)
        root = Path(sys.argv[1])
        controller = AppController(ConfigStore(root), Settings(), HistoryStore(root/'history.sqlite3'), SecretStore(enabled=False))
        controller.selected_model = Model('test', 'Test', 'gemini', True, 30000, 4096)
        controller.set_question('Harmless synthetic question')
        controller.submit()
        QTimer.singleShot(200, controller.quit)
        QTimer.singleShot(5000, lambda: qapp.exit(7))
        raise SystemExit(qapp.exec_())
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        capture_output=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    with sqlite3.connect(tmp_path / "history.sqlite3") as db:
        text, status = db.execute("SELECT text,status FROM messages WHERE role='assistant'").fetchone()
        assert text == "Synthetic partial" and status == "stopped"


def test_native_windows_capture_guard_surfaces_and_handle_recreation(tmp_path):
    """Read real Windows affinity on major surfaces, including dialogs, popups and a Pin change."""
    if sys.platform != "win32" or sys.getwindowsversion().build < 19041:
        import pytest

        pytest.skip("WDA_EXCLUDEFROMCAPTURE requires Windows 10 version 2004 or newer")
    script = dedent("""
        import sys
        from pathlib import Path
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox
        from maya.core.config import ConfigStore, Settings
        from maya.core.storage import HistoryStore
        from maya.platform.secrets import SecretStore
        from maya.ui.app import AppController
        from maya.ui.settings import SettingsDialog
        from maya.ui.history import HistoryDialog
        from maya.ui.context_review import ContextReview
        from maya.core.types import Model
        qapp = QApplication([])
        qapp.setQuitOnLastWindowClosed(False)
        root = Path(sys.argv[1])
        controller = AppController(ConfigStore(root), Settings(), HistoryStore(root/'history.sqlite3'), SecretStore(enabled=False))
        controller.window_timer.stop()
        controller.capture_guard.start()
        settings = SettingsDialog(Settings(), SecretStore(enabled=False), controller.history, root)
        history = HistoryDialog(controller.history)
        menu = QMenu()
        menu.addAction('Synthetic action')
        notice = QMessageBox(QMessageBox.Information, 'Synthetic notice', 'No private context', QMessageBox.Ok)
        controller.selected_model = Model('sample', 'Synthetic model', 'gemini', True)
        controller.set_question('A synthetic question for local review')
        review = ContextReview(controller.prepared_context(), controller.settings.urls['gemini'], 'gemini')
        surfaces = [controller.main, controller.mini, controller.orb, controller.clipboard_window, settings, history, menu, notice, review]
        try:
            for widget in surfaces:
                widget.setAttribute(Qt.WA_ShowWithoutActivating)
                widget.show()
                qapp.processEvents()
                assert widget.property('maya_capture_verified'), widget.windowTitle()
                assert controller.desktop.capture_affinity(int(widget.winId())) == 0x11, widget.windowTitle()
                widget.hide()
                qapp.processEvents()
            controller.main.show()
            controller.toggle_pin()
            qapp.processEvents()
            assert not controller.settings.pin_main
            assert controller.main.property('maya_capture_verified')
            assert controller.desktop.capture_affinity(int(controller.main.winId())) == 0x11
            controller.toggle_pin()
            qapp.processEvents()
            assert controller.settings.pin_main and controller.main.property('maya_capture_verified')
            assert controller.desktop.capture_affinity(int(controller.main.winId())) == 0x11
            assert not controller.jobs and not controller.clipboard_window.connected
        finally:
            controller.capture_guard.stop()
            controller.window_timer.stop()
            controller.flush_timer.stop()
            qapp.removeNativeEventFilter(controller.hotkeys)
            for widget in surfaces:
                widget.hide()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env=dict(os.environ, QT_QPA_PLATFORM="windows"),
        capture_output=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_native_windows_compact_render_and_topmost(tmp_path):
    """Real Windows fonts/layout must keep the reader stable with chat, errors and capture controls."""
    if sys.platform != "win32":
        import pytest

        pytest.skip("Native Windows UI regression")
    script = dedent("""
        import ctypes, sys, traceback
        from pathlib import Path
        from PyQt5.QtCore import Qt, QTimer
        from PyQt5.QtWidgets import QApplication, QPushButton
        from PIL import Image
        from maya.platform.windows import set_dpi_awareness
        from maya.core.config import ConfigStore, Settings
        from maya.core.storage import HistoryStore
        from maya.core.types import Message
        from maya.platform.secrets import SecretStore
        from maya.capture import prepare
        from maya.ui.app import AppController
        from maya.ui.widgets import STYLE
        set_dpi_awareness()
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
        qapp = QApplication([])
        qapp.setQuitOnLastWindowClosed(False)
        qapp.setStyleSheet(STYLE)
        root = Path(sys.argv[1])
        controller = AppController(ConfigStore(root), Settings(), HistoryStore(root/'history.sqlite3'), SecretStore(enabled=False))
        controller.main.setAttribute(Qt.WA_ShowWithoutActivating)
        controller.capture_guard.start()
        controller.main.show()

        def finish(code):
            controller.capture_guard.stop()
            controller.window_timer.stop()
            controller.flush_timer.stop()
            qapp.removeNativeEventFilter(controller.hotkeys)
            for widget in (controller.main, controller.mini, controller.orb, controller.clipboard_window):
                widget.hide()
            qapp.exit(code)

        def check_float():
            try:
                controller.mini.resize(320, 360)
                qapp.processEvents()
                assert (controller.mini.width(), controller.mini.height()) == (320, 360)
                controller.mini.panel.context_toggle.click()
                assert not controller.settings.screen_enabled and not controller.jobs
                controller.mini.panel.screen.click()
                controller.pending_image = prepare(Image.new('RGB', (50, 50), 'white'), 512, check_blank=False)
                controller.attachment_changed.emit()
                controller.notice('The provider rejected this request. Review model capabilities and try a smaller screenshot or shorter question.')
                qapp.processEvents()
                panel = controller.mini.panel
                assert (controller.mini.width(), controller.mini.height()) == (320, 360)
                for control in (panel.send, panel.stop, panel.composer, panel.attachment, panel.status):
                    assert panel.rect().contains(control.mapTo(panel, control.rect().topLeft()))
                    assert panel.rect().contains(control.mapTo(panel, control.rect().bottomRight()))
                assert panel.notice.toolTip() == panel.notice_text
                assert not controller.jobs
                assert not controller.mini.grab().isNull()
                finish(0)
            except Exception:
                traceback.print_exc()
                finish(1)

        def check_main():
            try:
                assert (controller.main.width(), controller.main.height()) == (480, 560)
                assert controller.main.property('maya_capture_requested')
                expected_affinity = 0x11 if sys.getwindowsversion().build >= 19041 else 1
                assert controller.desktop.capture_affinity(int(controller.main.winId())) == expected_affinity
                viewport = controller.main.panel.view.scroll.viewport()
                chips = controller.main.panel.view.empty.findChildren(QPushButton)
                assert len(chips) == 3
                assert all(viewport.rect().contains(chip.mapTo(viewport, chip.rect().bottomRight())) for chip in chips)
                assert controller.main.panel.view.scroll.verticalScrollBar().maximum() == 0
                get_style = ctypes.windll.user32.GetWindowLongW
                get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
                get_style.restype = ctypes.c_long
                assert get_style(int(controller.main.winId()), -20) & 8
                assert not controller.main.grab().isNull()
                controller.main.hide()
                controller.mini.show()
                controller.message_added.emit(Message('user', 'What does git status --short do?'))
                controller.message_added.emit(Message('assistant', '**Compact changed-file status.**\\n\\n`?? notes.txt` is an untracked file.\\n\\n```shell\\ngit status --short\\n```'))
                QTimer.singleShot(150, check_float)
            except Exception:
                traceback.print_exc()
                finish(1)

        QTimer.singleShot(200, check_main)
        QTimer.singleShot(5000, lambda: finish(7))
        raise SystemExit(qapp.exec_())
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env=dict(os.environ, QT_QPA_PLATFORM="windows"),
        capture_output=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
