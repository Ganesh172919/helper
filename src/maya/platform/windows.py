"""Pointer-safe Windows integration isolated from portable application logic."""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys
import os

from maya.core.types import MayaError


# --- Read-only foreground metadata and capture exclusion; no input automation API exists here. ---
@dataclass(frozen=True)
class ActiveWindow:
    """A best-effort snapshot of an external foreground window in physical desktop pixels."""

    handle: int = 0
    title: str = ""
    rect: tuple[int, int, int, int] | None = None
    minimized: bool = False
    process_id: int = 0


class WindowsDesktop:
    """Desktop capture helpers; unsupported platforms return honest unavailable states."""

    def __init__(self):
        """Bind every pointer-bearing native function used by this implementation."""
        self.user = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None
        self.registered: list[tuple[int, int]] = []
        if self.user:
            self.user.GetForegroundWindow.restype = wintypes.HWND
            self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            self.user.IsWindow.argtypes = [wintypes.HWND]
            self.user.IsIconic.argtypes = [wintypes.HWND]
            self.user.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
            self.user.SetWindowDisplayAffinity.restype = wintypes.BOOL
            self.user.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            self.user.GetWindowDisplayAffinity.restype = wintypes.BOOL
            self.user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

    def active_window(self, own_handles: set[int]) -> ActiveWindow:
        """Read an external foreground window; never return the assistant's own content as context."""
        if not self.user:
            return ActiveWindow()
        handle = self.user.GetForegroundWindow()
        if not handle or int(handle) in own_handles:
            return ActiveWindow()
        title = ctypes.create_unicode_buffer(1024)
        self.user.GetWindowTextW(handle, title, len(title))
        rect, pid = wintypes.RECT(), wintypes.DWORD()
        ok = self.user.GetWindowRect(handle, ctypes.byref(rect))
        self.user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value == os.getpid():
            return ActiveWindow()
        bounds = (rect.left, rect.top, rect.right, rect.bottom) if ok else None
        return ActiveWindow(int(handle), title.value, bounds, bool(self.user.IsIconic(handle)), pid.value)

    def valid_window(self, window: ActiveWindow) -> bool:
        """Reject minimized/closed windows instead of silently capturing unrelated screen content."""
        return bool(
            self.user
            and window.handle
            and self.user.IsWindow(window.handle)
            and not self.user.IsIconic(window.handle)
            and window.rect
        )

    def exclude_capture(self, handle: int) -> bool:
        """Request best-effort capture exclusion; callers still hide own windows for their captures."""
        return bool(self.user and self.user.SetWindowDisplayAffinity(handle, 0x11))

    def capture_affinity(self, handle: int) -> int | None:
        """Read native affinity when available; a failed query must not claim verified exclusion."""
        if not self.user:
            return None
        value = wintypes.DWORD()
        if self.user.GetWindowDisplayAffinity(handle, ctypes.byref(value)):
            return value.value
        return None

    def cursor(self) -> tuple[int, int]:
        """Return native cursor coordinates, including negative multi-monitor positions."""
        point = wintypes.POINT()
        if self.user and self.user.GetCursorPos(ctypes.byref(point)):
            return point.x, point.y
        return 0, 0

    @staticmethod
    def parse_hotkey(value: str) -> tuple[int, int]:
        """Parse Alt/Ctrl/Shift plus one letter/digit/F-key; Windows-key shortcuts are intentionally absent."""
        parts = [part.strip().casefold() for part in value.split("+")]
        modifiers = {"alt": 1, "ctrl": 2, "control": 2, "shift": 4}
        if len(parts) < 2 or any(part not in modifiers for part in parts[:-1]):
            raise MayaError("Use a shortcut such as Alt+Shift+N or Ctrl+Alt+F8.", "hotkey")
        mask = 0x4000  # MOD_NOREPEAT avoids rapid toggling while the keys are held.
        for part in parts[:-1]:
            mask |= modifiers[part]
        key = parts[-1]
        if len(key) == 1 and key.isascii() and key.isalnum():
            return mask, ord(key.upper())
        if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
            return mask, 0x70 + int(key[1:]) - 1
        if key in {"up", "down"}:
            return mask, 0x26 if key == "up" else 0x28
        raise MayaError("The shortcut key must be a letter, digit, arrow, or F1–F24.", "hotkey")

    def register_hotkey(self, handle: int, identifier: int, value: str) -> None:
        """Register a global shortcut, raising an actionable error if another app owns it."""
        if not self.user:
            raise MayaError("Global shortcuts are currently supported on Windows only.", "hotkey")
        modifiers, key = self.parse_hotkey(value)
        if not self.user.RegisterHotKey(handle, identifier, modifiers, key):
            raise MayaError(f"Shortcut {value} is unavailable. Choose another in Settings.", "hotkey")
        self.registered.append((handle, identifier))

    def unregister_hotkeys(self) -> None:
        """Release only shortcuts registered by this application, including during settings changes."""
        if self.user:
            for handle, identifier in self.registered:
                self.user.UnregisterHotKey(handle, identifier)
        self.registered.clear()


def set_dpi_awareness() -> None:
    """Request per-monitor-v2 awareness before Qt imports/creates windows; older Windows falls back."""
    if sys.platform == "win32":
        user = ctypes.WinDLL("user32", use_last_error=True)
        try:
            user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except AttributeError:
            user.SetProcessDPIAware()
