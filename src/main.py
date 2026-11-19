"""Punto de entrada de English Lens (System Tray + Atajos globales + Instancia única)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from capture import capture_monitor_at
from hotkey import WindowsHotkeyManager
from overlay_ui import LensOverlay

_PID_FILE = Path(tempfile.gettempdir()) / "english_lens.pid"


def _ensure_single_instance() -> None:
    """Si ya había una instancia previa de English Lens corriendo, la reemplaza limpiamente."""
    current_pid = os.getpid()
    if _PID_FILE.exists():
        try:
            old_pid = int(_PID_FILE.read_text(encoding="utf-8").strip())
            if old_pid > 0 and old_pid != current_pid:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.run(
                    ["taskkill", "/PID", str(old_pid), "/F"],
                    capture_output=True,
                    creationflags=creationflags,
                    timeout=3,
                )
        except Exception:  # noqa: BLE001
            pass

    try:
        _PID_FILE.write_text(str(current_pid), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _create_tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#0f172a"))
    painter.setPen(QColor("#38bdf8"))
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor("#38bdf8"))
    font = painter.font()
    font.setPointSize(24)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), 0x0084, "En")  # AlignCenter
    painter.end()
    return QIcon(pixmap)


class EnglishLensApp(QObject):
    """Controlador principal (QObject para encolar señales del hook al hilo GUI)."""

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.overlay: LensOverlay | None = None

        self.tray = QSystemTrayIcon(_create_tray_icon(), app)
        self.tray.setToolTip("English Lens — Ctrl+Shift+Espacio · Alt+Shift+E · F8")

        menu = QMenu()
        capture_action = QAction("Capturar ahora (Ctrl+Shift+Espacio / F8)", menu)
        capture_action.triggered.connect(self.trigger_capture)
        quit_action = QAction("Salir", menu)
        quit_action.triggered.connect(self.quit)

        menu.addAction(capture_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self.hotkey = WindowsHotkeyManager(app)
        self.hotkey.triggered.connect(self.trigger_capture, Qt.ConnectionType.QueuedConnection)
        active = self.hotkey.register()
        if active:
            self.tray.showMessage(
                "English Lens activo",
                "Atajos: Ctrl + Shift + Espacio · Alt + Shift + E · F8",
                QSystemTrayIcon.MessageIcon.Information,
                2800,
            )
        else:
            print("[AVISO] No se pudo instalar el hook de teclado global.")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.trigger_capture()

    def trigger_capture(self) -> None:
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None
            return

        pos = QCursor.pos()
        screen = self.app.screenAt(pos) or self.app.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        capture = capture_monitor_at(int(pos.x() * dpr), int(pos.y() * dpr))

        self.overlay = LensOverlay(capture)
        self.overlay.closed.connect(self._on_overlay_closed)
        self.overlay.show()
        self.overlay.activateWindow()
        self.overlay.raise_()

    def _on_overlay_closed(self) -> None:
        self.overlay = None

    def quit(self) -> None:
        self.hotkey.unregister()
        self.tray.hide()
        try:
            if _PID_FILE.exists():
                _PID_FILE.unlink()
        except Exception:  # noqa: BLE001
            pass
        self.app.quit()


def main() -> int:
    _ensure_single_instance()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    controller = EnglishLensApp(app)

    if "--capture-now" in sys.argv:
        QTimer.singleShot(250, controller.trigger_capture)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
