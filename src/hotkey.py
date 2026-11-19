"""Registro de atajos globales nativos en Windows (F9 y Ctrl+Alt+E) integrados con Qt."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QWidget

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

VK_F9 = 0x78
VK_E = 0x45

HOTKEY_F9_ID = 0xE119
HOTKEY_CTRL_ALT_E_ID = 0xE11E


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

    def __init__(self, hotkey_ids: set[int], callback) -> None:
        super().__init__()
        self._hotkey_ids = hotkey_ids
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message == WM_HOTKEY and msg.wParam in self._hotkey_ids:
                self._callback()
                return True, 0
        return False, 0


class WindowsHotkeyManager(QObject):
    """Registra F9 (principal) y Ctrl+Alt+E (respaldo) usando un HWND oculto de Qt."""

    triggered = Signal()

    def __init__(self, app) -> None:
        super().__init__()
        self._app = app
        self._registered_ids: set[int] = set()
        self._hwnd_widget = QWidget()
        self._hwnd = int(self._hwnd_widget.winId())
        self._filter = GlobalHotkeyFilter(self._registered_ids, self.triggered.emit)

    def register(self) -> list[str]:
        """Registra los atajos y devuelve la lista legible de los que quedaron activos."""
        user32 = ctypes.windll.user32
        active_labels: list[str] = []

        candidates = [
            (HOTKEY_F9_ID, MOD_NOREPEAT, VK_F9, "F9"),
            (HOTKEY_CTRL_ALT_E_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_E, "Ctrl + Alt + E"),
        ]

        for hk_id, mods, vk, label in candidates:
            if user32.RegisterHotKey(self._hwnd, hk_id, mods, vk):
                self._registered_ids.add(hk_id)
                active_labels.append(label)

        if self._registered_ids:
            self._app.installNativeEventFilter(self._filter)

        return active_labels

    def unregister(self) -> None:
        if self._registered_ids:
            self._app.removeNativeEventFilter(self._filter)
            user32 = ctypes.windll.user32
            for hk_id in list(self._registered_ids):
                user32.UnregisterHotKey(self._hwnd, hk_id)
            self._registered_ids.clear()
