"""Punto de entrada de English Lens (System Tray + Atajo global Alt + F11)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from capture import capture_monitor_at
from hotkey import WindowsHotkeyManager
from overlay_ui import LensOverlay


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


class EnglishLensApp:
    """Controlador principal: bandeja del sistema, hotkey Alt+F11 y ciclo del overlay."""

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.overlay: LensOverlay | None = None

        self.tray = QSystemTrayIcon(_create_tray_icon(), app)
        self.tray.setToolTip("English Lens — Presioná F10 para capturar")

        menu = QMenu()
        capture_action = QAction("Capturar ahora (F10)", menu)
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
        self.hotkey.triggered.connect(self.trigger_capture)
        ok = self.hotkey.register()
        if ok:
            self.tray.showMessage(
                "English Lens activo",
                "Presioná F10 en cualquier pantalla para leer con desenfoque y tips.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
        else:
            print("[AVISO] No se pudo registrar F10 (puede estar en uso por otra app).")

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
        self.app.quit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    controller = EnglishLensApp(app)

    if "--capture-now" in sys.argv:
        QTimer.singleShot(250, controller.trigger_capture)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
