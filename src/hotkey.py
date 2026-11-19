"""Atajos globales en Windows: hook WH_KEYBOARD_LL + RegisterHotKey con evento thread-safe.

Arquitectura ultra estable:
- El callback de WH_KEYBOARD_LL solo hace `_trigger_event.set()` (<1 microsegundo), sin tocar
  objetos de Qt desde el hilo del hook.
- Un QTimer liviano en el hilo principal de Qt lee `_trigger_event` cada 40 ms y emite `triggered`.
- Además intenta registrar los atajos por `RegisterHotKey` como respaldo (con debounce de 400 ms).
- Atajos activos:
  * Ctrl + Shift + Espacio
  * Alt + Shift + E
  * F8
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_MENU = 0x12
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1

VK_SPACE = 0x20
VK_E = 0x45
VK_F8 = 0x77


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class _HotKeyNativeFilter(QAbstractNativeEventFilter):
    def __init__(self, ids: set[int], callback) -> None:
        super().__init__()
        self._ids = ids
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message == WM_HOTKEY and msg.wParam in self._ids:
                self._callback()
                return True, 0
        return False, 0


class WindowsHotkeyManager(QObject):
    """Combina WH_KEYBOARD_LL + RegisterHotKey y despacha siempre en el hilo principal de Qt."""

    triggered = Signal()

    def __init__(self, app) -> None:
        super().__init__()
        self._app = app
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self._user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            _HOOKPROC,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        self._user32.SetWindowsHookExW.restype = wintypes.HANDLE
        self._user32.CallNextHookEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self._user32.CallNextHookEx.restype = ctypes.c_ssize_t
        self._user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        self._trigger_event = threading.Event()
        self._last_fire_ts = 0.0

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(40)
        self._poll_timer.timeout.connect(self._check_trigger_event)

        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hook_handle = None
        self._hook_cb = None
        self._ready_event = threading.Event()
        self._hook_ok = False
        self._pressed_triggers: set[str] = set()

        self._hwnd_widget = QWidget()
        self._hwnd = int(self._hwnd_widget.winId())
        self._registered_ids: set[int] = set()
        self._native_filter = _HotKeyNativeFilter(self._registered_ids, self._emit_debounced)

    def _emit_debounced(self) -> None:
        now = time.monotonic()
        if now - self._last_fire_ts >= 0.4:
            self._last_fire_ts = now
            self.triggered.emit()

    def _check_trigger_event(self) -> None:
        if self._trigger_event.is_set():
            self._trigger_event.clear()
            self._emit_debounced()

    def _is_down(self, *vks: int) -> bool:
        return any(bool(self._user32.GetAsyncKeyState(vk) & 0x8000) for vk in vks)

    def _match_combo(self, vk: int) -> str | None:
        ctrl = self._is_down(VK_CONTROL, VK_LCONTROL, VK_RCONTROL)
        alt = self._is_down(VK_MENU, VK_LMENU, VK_RMENU)
        shift = self._is_down(VK_SHIFT, VK_LSHIFT, VK_RSHIFT)

        if vk == VK_SPACE and ctrl and shift and not alt:
            return "ctrl+shift+space"
        if vk == VK_E and alt and shift and not ctrl:
            return "alt+shift+e"
        if vk == VK_F8 and not ctrl and not alt and not shift:
            return "f8"
        return None

    def _run_hook_loop(self) -> None:
        self._thread_id = self._kernel32.GetCurrentThreadId()

        def low_level_handler(n_code: int, w_param: int, l_param: int) -> int:
            try:
                if n_code == 0 and l_param:
                    info = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                    vk = int(info.vkCode)

                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        combo = self._match_combo(vk)
                        if combo is not None:
                            if combo not in self._pressed_triggers:
                                self._pressed_triggers.add(combo)
                                self._trigger_event.set()
                            return 1
                    elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                        if vk == VK_SPACE:
                            self._pressed_triggers.discard("ctrl+shift+space")
                        elif vk == VK_E:
                            self._pressed_triggers.discard("alt+shift+e")
                        elif vk == VK_F8:
                            self._pressed_triggers.discard("f8")
            except Exception:  # noqa: BLE001
                pass

            return self._user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

        self._hook_cb = _HOOKPROC(low_level_handler)
        self._hook_handle = self._user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_cb, None, 0)
        self._hook_ok = bool(self._hook_handle)
        self._ready_event.set()

        if not self._hook_handle:
            return

        msg = wintypes.MSG()
        while self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_handle:
            self._user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None

    def register(self) -> list[str]:
        """Activa el hook WH_KEYBOARD_LL y además registra RegisterHotKey como respaldo."""
        if self._thread is None or not self._thread.is_alive():
            self._ready_event.clear()
            self._thread = threading.Thread(
                target=self._run_hook_loop,
                name="EnglishLensHotkey",
                daemon=True,
            )
            self._thread.start()
            self._ready_event.wait(timeout=2.0)

        self._poll_timer.start()

        # Respaldo RegisterHotKey (útil si alguna app bloquea hooks)
        candidates = [
            (0xE201, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_SPACE),
            (0xE202, MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, VK_E),
            (0xE203, MOD_NOREPEAT, VK_F8),
        ]
        for hk_id, mods, vk in candidates:
            if self._user32.RegisterHotKey(self._hwnd, hk_id, mods, vk):
                self._registered_ids.add(hk_id)

        if self._registered_ids:
            self._app.installNativeEventFilter(self._native_filter)

        if self._hook_ok or self._registered_ids:
            return ["Ctrl + Shift + Espacio", "Alt + Shift + E", "F8"]
        return []

    def unregister(self) -> None:
        self._poll_timer.stop()
        if self._registered_ids:
            self._app.removeNativeEventFilter(self._native_filter)
            for hk_id in list(self._registered_ids):
                self._user32.UnregisterHotKey(self._hwnd, hk_id)
            self._registered_ids.clear()
        if self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
            self._thread_id = 0
