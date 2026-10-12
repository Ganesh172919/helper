"""Apply the reference's native capture exclusion to every Maya top-level surface."""

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QApplication, QWidget


class CaptureGuard(QObject):
    """Protect new dialogs/popups and recreated handles, with honest native verification state.

    This filter only sees this application's widgets. It never changes another process, blocks
    a recorder or promises invisibility with every screen-sharing API.
    """

    def __init__(self, desktop, parent=None):
        super().__init__(parent)
        self.desktop = desktop
        self.installed = False
        self.busy = False

    def start(self) -> None:
        """Watch future surfaces and handle windows that are already visible."""
        if not self.installed:
            QApplication.instance().installEventFilter(self)
            self.installed = True
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible():
                self.protect(widget)

    def stop(self) -> None:
        """Detach before application shutdown; no global callbacks outlive the controller."""
        if self.installed:
            QApplication.instance().removeEventFilter(self)
            self.installed = False

    def protect(self, widget: QWidget) -> None:
        """Set an own top-level handle and separately record API acceptance and read-back."""
        if self.busy or not widget.isWindow():
            return
        self.busy = True
        try:
            handle = int(widget.winId())
            accepted = self.desktop.exclude_capture(handle)
            affinity = self.desktop.capture_affinity(handle) if accepted else None
            widget.setProperty("maya_capture_requested", accepted)
            widget.setProperty("maya_capture_affinity", affinity if affinity is not None else -1)
            widget.setProperty("maya_capture_verified", accepted and affinity == 0x11)
        except RuntimeError:
            # A short-lived popup may be destroyed as Qt dispatches a deferred native event.
            return
        finally:
            self.busy = False

    def eventFilter(self, watched, event) -> bool:
        """Reapply at Show and native-handle replacement without consuming any user input."""
        if isinstance(watched, QWidget) and watched.isWindow():
            if event.type() == QEvent.Show or (event.type() == QEvent.WinIdChange and watched.isVisible()):
                self.protect(watched)
        return False

    def report(self) -> str:
        """Describe visible own surfaces without treating API acceptance as recorder compatibility."""
        rows = []
        for widget in QApplication.topLevelWidgets():
            if not widget.isVisible():
                continue
            if widget.property("maya_capture_verified"):
                state = "Windows exclusion confirmed"
            elif widget.property("maya_capture_requested") and widget.property("maya_capture_affinity") == 1:
                state = "monitor-only fallback; capture exclusion not confirmed"
            elif widget.property("maya_capture_requested") and widget.property("maya_capture_affinity") == -1:
                state = "request accepted; read-back unavailable"
            elif widget.property("maya_capture_requested"):
                state = "capture exclusion not confirmed"
            else:
                state = "exclusion unavailable"
            rows.append(f"{widget.windowTitle() or 'Maya popup'}: {state}")
        return "\n".join(sorted(rows)) or "No Maya surface is currently visible."
