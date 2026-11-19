"""Registro de atajo global nativo en Windows (Alt + F11) integrado con Qt."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000
VK_F11 = 0x7A
HOTKEY_ID = 0xE11F


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class GlobalHotkeyFilter(QAbstractNativeEventFilter):
    """Escucha eventos nativos WM_HOTKEY de Windows dentro del loop de Qt."""

    def __init__(self, hotkey_id: int, callback) -> None:
        super().__init__()
        self._hotkey_id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                self._callback()
                return True, 0
        return False, 0


class WindowsHotkeyManager(QObject):
    """Registra y libera el atajo global Alt + F11 en Windows."""

    triggered = Signal()

    def __init__(self, app) -> None:
        super().__init__()
        self._app = app
        self._registered = False
        self._filter = GlobalHotkeyFilter(HOTKEY_ID, self.triggered.emit)

    def register(self) -> bool:
        user32 = ctypes.windll.user32
        ok = bool(user32.RegisterHotKey(None, HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_F11))
        if ok:
            self._registered = True
            self._app.installNativeEventFilter(self._filter)
        return ok

    def unregister(self) -> None:
        if self._registered:
            self._app.removeNativeEventFilter(self._filter)
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False
