"""Local application entry point for Maya the Helper."""

import argparse
import logging
from logging.handlers import RotatingFileHandler
import sys
import sqlite3
import traceback

from maya.core.config import ConfigStore, data_directory
from maya.core.storage import HistoryStore
from maya.core.types import MayaError
from maya.platform.windows import set_dpi_awareness


# --- Startup uses a per-user lock/server: a second invocation reveals the existing app. ---
def main() -> int:
    """Launch Maya with a single-instance channel, writable local data, and safe crash diagnostics.

    Returns a process exit code. Startup failures are shown in a dialog without secret values.
    --smoke-test uses an isolated temporary data directory and exits after a real Qt startup.
    """
    parser = argparse.ArgumentParser(description="Maya the Helper — local Python desktop assistant")
    parser.add_argument(
        "--smoke-test", action="store_true", help="Launch a disposable Qt instance and exit after 1 second"
    )
    parser.add_argument(
        "--no-credentials",
        action="store_true",
        help="Disable saved-key and environment-key access for local verification",
    )
    parser.add_argument(
        "--env-file", help="Read an explicit .env file; otherwise only .env in the current folder is read"
    )
    args = parser.parse_args()
    set_dpi_awareness()
    from PyQt5.QtCore import QLockFile, Qt, QTimer
    from PyQt5.QtNetwork import QLocalServer, QLocalSocket
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from maya.ui.app import AppController
    from maya.ui.widgets import STYLE

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Maya the Helper")
    app.setOrganizationName("MayaHelper")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    # Isolated checks must never load a user's .env, including its private data-directory override.
    if not (args.smoke_test or args.no_credentials):
        from pathlib import Path
        from maya.platform.environment import load_environment

        try:
            load_environment(
                Path(args.env_file) if args.env_file else Path.cwd() / ".env", bool(args.env_file)
            )
        except MayaError as exc:
            QMessageBox.critical(None, "Maya environment", str(exc))
            return 1
    temporary = None
    directory = data_directory()
    if args.smoke_test:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        temporary = TemporaryDirectory(prefix="maya-smoke-")
        directory = Path(temporary.name)
    try:
        store = ConfigStore(directory)
        settings = store.load()
    except (MayaError, OSError, ValueError) as exc:
        QMessageBox.critical(
            None,
            "Maya startup",
            str(exc)
            if isinstance(exc, MayaError)
            else "Could not open Maya's local data folder. Check permissions or use MAYA_DATA_DIR.",
        )
        return 1
    log = logging.getLogger("maya")
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(
            directory / "diagnostics.log", maxBytes=200000, backupCount=2, encoding="utf-8"
        )
    except OSError:
        QMessageBox.critical(
            None,
            "Maya startup",
            "Could not create safe diagnostics in the local data folder. Check permissions.",
        )
        return 1
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    lock = QLockFile(str(directory / "instance.lock"))
    lock.setStaleLockTime(0)
    import hashlib

    server_name = "MayaHelper-" + hashlib.sha256(str(directory).encode()).hexdigest()[:20]
    if not lock.tryLock(100):
        socket = QLocalSocket()
        socket.connectToServer(server_name)
        if socket.waitForConnected(1000):
            socket.write(b"show")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            return 0
        QMessageBox.information(
            None,
            "Maya is already open",
            "Another Maya instance is starting or shutting down. Try again shortly.",
        )
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    if not server.listen(server_name):
        QMessageBox.critical(
            None, "Maya startup", "Could not create the local single-instance channel. Restart Maya."
        )
        lock.unlock()
        return 1
    # Only the lock owner performs recovery; a second launch must not mark live streams interrupted.
    try:
        history = HistoryStore(directory / "history.sqlite3")
    except (OSError, sqlite3.Error):
        QMessageBox.critical(
            None,
            "Maya startup",
            "Could not open the history database. Check data-folder permissions or restore a backup.",
        )
        server.close()
        lock.unlock()
        return 1
    from maya.platform.secrets import SecretStore

    controller = AppController(
        store, settings, history, SecretStore(enabled=not (args.smoke_test or args.no_credentials))
    )

    def reveal() -> None:
        """Respond to a second launch using only a local IPC show request."""
        connection = server.nextPendingConnection()
        if connection:
            connection.close()
            connection.deleteLater()
        controller.show_normal()

    def crash_hook(kind, value, trace) -> None:
        """Record exception type and stack frames only; never raw exception values, keys, or user context."""
        log.error("Unhandled %s\n%s", kind.__name__, "".join(traceback.format_tb(trace)))
        controller.notice(
            "An unexpected operation failed. See diagnostics.log for its code location and retry."
        )

    sys.excepthook = crash_hook
    server.newConnection.connect(reveal)
    controller.start()
    if args.smoke_test:
        QTimer.singleShot(1000, controller.quit)
    result = app.exec_()
    server.close()
    lock.unlock()
    handler.close()
    log.removeHandler(handler)
    if temporary:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
