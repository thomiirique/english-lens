"""Atajos globales en Windows mediante hook de teclado de bajo nivel (WH_KEYBOARD_LL).

Ventajas frente a RegisterHotKey:
- No falla con ERROR_HOTKEY_ALREADY_REGISTERED (1409) si otra app usa la tecla.
- Funciona sin importar qué ventana tenga el foco (navegador, PDF, juego, IDE).
- Soporta múltiples combinaciones cómodas sin chocar con AltGr (€) en teclados latinos:
  * Ctrl + Shift + Espacio (universal, sin necesidad de tecla Fn)
  * Alt + Shift + E (mano izquierda, sin conflicto con AltGr)
  * F8 (tecla única sin conflictos del sistema)
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_MENU = 0x12  # Alt
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


_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class WindowsHotkeyManager(QObject):
    """Escucha atajos globales desde un hilo dedicado con GetMessageW + WH_KEYBOARD_LL."""

    triggered = Signal()

    def __init__(self, app=None) -> None:
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

        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hook_handle = None
        self._hook_cb = None
        self._ready_event = threading.Event()
        self._register_ok = False
        self._pressed_triggers: set[str] = set()

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
            if n_code == 0 and l_param:
                info = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                vk = int(info.vkCode)

                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    combo = self._match_combo(vk)
                    if combo is not None:
                        if combo not in self._pressed_triggers:
                            self._pressed_triggers.add(combo)
                            self.triggered.emit()
                        return 1  # Consumir tecla para no abrir menú/espacio en la app de fondo
                elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                    if vk == VK_SPACE:
                        self._pressed_triggers.discard("ctrl+shift+space")
                    elif vk == VK_E:
                        self._pressed_triggers.discard("alt+shift+e")
                    elif vk == VK_F8:
                        self._pressed_triggers.discard("f8")

            return self._user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

        self._hook_cb = _HOOKPROC(low_level_handler)
        self._hook_handle = self._user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_cb, None, 0)
        self._register_ok = bool(self._hook_handle)
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
        """Inicia el hook global y devuelve los atajos activos."""
        if self._thread is not None and self._thread.is_alive():
            return ["Ctrl + Shift + Espacio", "Alt + Shift + E", "F8"]

        self._ready_event.clear()
        self._thread = threading.Thread(target=self._run_hook_loop, name="EnglishLensHotkey", daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=2.0)

        if self._register_ok:
            return ["Ctrl + Shift + Espacio", "Alt + Shift + E", "F8"]
        return []

    def unregister(self) -> None:
        if self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
            self._thread_id = 0
