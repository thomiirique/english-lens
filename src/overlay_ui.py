"""Overlay fullscreen con fondo desenfocado, selección nítida, palabras clicables y panel de tips."""

from __future__ import annotations

from typing import Optional

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ai_tutor import TutorAnalysis, analyze_text_with_gemini
from capture import ScreenCapture
from ocr_windows import OcrResult, OcrWord, run_windows_ocr


def _pil_to_qpixmap(img: Image.Image, dpr: float) -> QPixmap:
    rgb = img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg.copy())
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


class OcrWorker(QThread):
    """Ejecuta el OCR local de Windows sin congelar la interfaz."""

    finished_ocr = Signal(object)
    failed_ocr = Signal(str)

    def __init__(self, crop_image: Image.Image) -> None:
        super().__init__()
        self._crop_image = crop_image

    def run(self) -> None:
        try:
            result = run_windows_ocr(self._crop_image)
            self.finished_ocr.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed_ocr.emit(str(exc))


class TutorWorker(QThread):
    """Consulta la API gratuita de Gemini en segundo plano."""

    finished_analysis = Signal(object)

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def run(self) -> None:
        analysis = analyze_text_with_gemini(self._text)
        self.finished_analysis.emit(analysis)


class WordTooltipCard(QFrame):
    """Tarjetita flotante que aparece al tocar cualquier palabra del recorte."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("wordTooltip")
        self.setStyleSheet(
            """
            QFrame#wordTooltip {
                background-color: rgba(15, 23, 42, 245);
                border: 1px solid rgba(56, 189, 248, 0.75);
                border-radius: 10px;
            }
            QLabel {
                color: #f8fafc;
                background: transparent;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(4)

        self.title_label = QLabel()
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #38bdf8;")

        self.translation_label = QLabel()
        self.translation_label.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        self.translation_label.setWordWrap(True)

        self.meta_label = QLabel()
        self.meta_label.setFont(QFont("Segoe UI", 9))
        self.meta_label.setStyleSheet("color: #94a3b8;")
        self.meta_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.translation_label)
        layout.addWidget(self.meta_label)
        self.setMaximumWidth(320)
        self.hide()

    def show_word(self, word_text: str, translation: str, meta: str, anchor_rect: QRectF) -> None:
        self.title_label.setText(word_text)
        self.translation_label.setText(translation)
        self.meta_label.setText(meta)
        self.meta_label.setVisible(bool(meta))
        self.adjustSize()

        parent = self.parentWidget()
        pw = parent.width() if parent else 1920
        ph = parent.height() if parent else 1080

        x = int(anchor_rect.center().x() - self.width() / 2)
        y = int(anchor_rect.top() - self.height() - 10)
        if y < 16:
            y = int(anchor_rect.bottom() + 10)
        x = max(12, min(x, pw - self.width() - 12))
        y = max(12, min(y, ph - self.height() - 12))

        self.move(x, y)
        self.show()
        self.raise_()


class TipsPanel(QFrame):
    """Panel flotante con Frases de manual (Chunks) y Tips de lectura."""

    close_requested = Signal()
    recapture_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("tipsPanel")
        self.setStyleSheet(
            """
            QFrame#tipsPanel {
                background-color: rgba(15, 23, 42, 238);
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 14px;
            }
            QLabel {
                color: #e2e8f0;
                background: transparent;
            }
            QPushButton {
                background-color: rgba(51, 65, 85, 0.85);
                color: #f8fafc;
                border: 1px solid rgba(148, 163, 184, 0.3);
                border-radius: 7px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(56, 189, 248, 0.28);
                border-color: #38bdf8;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(8)

        header = QHBoxLayout()
        self.header_title = QLabel("🔍 English Lens — Lectura activa")
        self.header_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.header_title.setStyleSheet("color: #38bdf8;")

        self.recapture_btn = QPushButton("Nuevo recorte")
        self.recapture_btn.clicked.connect(self.recapture_requested.emit)

        self.close_btn = QPushButton("Cerrar (Esc)")
        self.close_btn.clicked.connect(self.close_requested.emit)

        header.addWidget(self.header_title)
        header.addStretch()
        header.addWidget(self.recapture_btn)
        header.addWidget(self.close_btn)
        outer.addLayout(header)

        self.status_label = QLabel("Analizando texto...")
        self.status_label.setFont(QFont("Segoe UI", 10))
        self.status_label.setStyleSheet("color: #94a3b8;")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMaximumHeight(240)
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 2, 0, 2)
        self.content_layout.setSpacing(8)
        self.scroll.setWidget(self.content_widget)
        outer.addWidget(self.scroll)

        self.setFixedWidth(560)
        self.hide()

    def _clear_content(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def set_loading(self, message: str) -> None:
        self._clear_content()
        self.status_label.setText(message)
        self.status_label.show()
        self.scroll.hide()
        self.adjustSize()

    def show_analysis(self, analysis: TutorAnalysis, word_count: int, ocr_lang: str) -> None:
        self._clear_content()

        has_data = bool(analysis.words or analysis.chunks or analysis.reading_tips)
        if analysis.status_message and not has_data:
            self.status_label.setText(analysis.status_message)
            self.status_label.setStyleSheet("color: #fbbf24;")
            self.status_label.show()
        else:
            self.status_label.setText(
                f"Tocá cualquier palabra del recorte para ver su traducción en contexto "
                f"({word_count} palabras · OCR: {ocr_lang})"
            )
            self.status_label.setStyleSheet("color: #94a3b8;")
            self.status_label.show()

        has_blocks = False

        if analysis.chunks:
            has_blocks = True
            sec_title = QLabel("🧩 Frases de manual / Chunks")
            sec_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            sec_title.setStyleSheet("color: #a78bfa;")
            self.content_layout.addWidget(sec_title)

            for chunk in analysis.chunks:
                lbl = QLabel(
                    f"<b style='color:#f8fafc;'>“{chunk.phrase}”</b> → "
                    f"<span style='color:#38bdf8;'>{chunk.meaning}</span><br>"
                    f"<span style='color:#cbd5e1;'>{chunk.tip}</span>"
                )
                lbl.setWordWrap(True)
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setFont(QFont("Segoe UI", 9.5))
                self.content_layout.addWidget(lbl)

        if analysis.reading_tips:
            has_blocks = True
            tips_title = QLabel("💡 Tips para leer la estructura")
            tips_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            tips_title.setStyleSheet("color: #34d399;")
            self.content_layout.addWidget(tips_title)

            for tip in analysis.reading_tips:
                lbl = QLabel(f"• {tip}")
                lbl.setWordWrap(True)
                lbl.setFont(QFont("Segoe UI", 9.5))
                self.content_layout.addWidget(lbl)

        self.scroll.setVisible(has_blocks)
        self.adjustSize()


class LensOverlay(QWidget):
    """Ventana fullscreen con desenfoque, selección nítida e interacción palabra por palabra."""

    closed = Signal()

    def __init__(self, capture: ScreenCapture) -> None:
        super().__init__()
        self._capture = capture
        self._state = "selecting"  # "selecting" | "reading"
        self._drag_start: Optional[QPoint] = None
        self._selection_rect = QRect()

        self._ocr_result: Optional[OcrResult] = None
        self._analysis: Optional[TutorAnalysis] = None
        self._word_rects: list[tuple[OcrWord, QRectF]] = []
        self._hovered_index: int = -1
        self._selected_index: int = -1

        self._ocr_worker: Optional[OcrWorker] = None
        self._tutor_worker: Optional[TutorWorker] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Posicionar exactamente en el monitor capturado respetando DPI
        screen = self.screen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        self._dpr = dpr

        logical_x = int(capture.left / dpr)
        logical_y = int(capture.top / dpr)
        logical_w = int(capture.width / dpr)
        logical_h = int(capture.height / dpr)
        self.setGeometry(logical_x, logical_y, logical_w, logical_h)

        self._blurred_pixmap = _pil_to_qpixmap(capture.blurred, dpr)
        self._original_pixmap = _pil_to_qpixmap(capture.original, dpr)

        # Banner superior discreto
        self._hud = QLabel("Arrastrá sobre el texto en inglés · Esc para cancelar", self)
        self._hud.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self._hud.setStyleSheet(
            """
            background-color: rgba(15, 23, 42, 225);
            color: #f8fafc;
            border: 1px solid rgba(56, 189, 248, 0.5);
            border-radius: 16px;
            padding: 7px 16px;
            """
        )
        self._hud.adjustSize()
        self._hud.move((logical_w - self._hud.width()) // 2, 18)

        self._tooltip = WordTooltipCard(self)
        self._tips_panel = TipsPanel(self)
        self._tips_panel.close_requested.connect(self.close)
        self._tips_panel.recapture_requested.connect(self._reset_to_selection)

    def _reset_to_selection(self) -> None:
        self._state = "selecting"
        self._drag_start = None
        self._selection_rect = QRect()
        self._ocr_result = None
        self._analysis = None
        self._word_rects = []
        self._hovered_index = -1
        self._selected_index = -1
        self._tooltip.hide()
        self._tips_panel.hide()
        self._hud.setText("Arrastrá sobre el texto en inglés · Esc para cancelar")
        self._hud.adjustSize()
        self._hud.move((self.width() - self._hud.width()) // 2, 18)
        self._hud.show()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def _position_tips_panel(self) -> None:
        self._tips_panel.adjustSize()
        pw, ph = self.width(), self.height()
        panel_w = self._tips_panel.width()
        panel_h = self._tips_panel.height()

        x = int(self._selection_rect.center().x() - panel_w / 2)
        y = self._selection_rect.bottom() + 16
        if y + panel_h > ph - 16:
            y = self._selection_rect.top() - panel_h - 16
        if y < 16:
            y = ph - panel_h - 16

        x = max(16, min(x, pw - panel_w - 16))
        y = max(16, min(y, ph - panel_h - 16))
        self._tips_panel.move(x, y)
        self._tips_panel.show()
        self._tips_panel.raise_()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position().toPoint()
        if self._state == "selecting":
            self._drag_start = pos
            self._selection_rect = QRect(pos, pos)
            self.update()
            return

        if self._state == "reading":
            idx = self._hit_test_word(pos)
            if idx != -1:
                self._selected_index = idx
                self._show_word_popup(idx)
                self.update()
            else:
                self._selected_index = -1
                self._tooltip.hide()
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        if self._state == "selecting" and self._drag_start is not None:
            self._selection_rect = QRect(self._drag_start, pos).normalized()
            self.update()
            return

        if self._state == "reading":
            idx = self._hit_test_word(pos)
            if idx != self._hovered_index:
                self._hovered_index = idx
                self.setCursor(
                    Qt.CursorShape.PointingHandCursor if idx != -1 else Qt.CursorShape.ArrowCursor
                )
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state != "selecting" or self._drag_start is None:
            return

        self._selection_rect = QRect(self._drag_start, event.position().toPoint()).normalized()
        self._drag_start = None

        if self._selection_rect.width() < 20 or self._selection_rect.height() < 12:
            self._selection_rect = QRect()
            self.update()
            return

        self._enter_reading_mode()

    def _enter_reading_mode(self) -> None:
        self._state = "reading"
        self._hud.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # Recortar en píxeles físicos para máxima nitidez en el OCR
        dpr = self._dpr
        x1 = max(0, int(self._selection_rect.left() * dpr))
        y1 = max(0, int(self._selection_rect.top() * dpr))
        x2 = min(self._capture.original.width, int(self._selection_rect.right() * dpr))
        y2 = min(self._capture.original.height, int(self._selection_rect.bottom() * dpr))
        crop = self._capture.original.crop((x1, y1, x2, y2))

        self._tips_panel.set_loading("Leyendo texto con OCR local de Windows...")
        self._position_tips_panel()
        self.update()

        self._ocr_worker = OcrWorker(crop)
        self._ocr_worker.finished_ocr.connect(self._on_ocr_done)
        self._ocr_worker.failed_ocr.connect(self._on_ocr_error)
        self._ocr_worker.start()

    def _on_ocr_done(self, result: OcrResult) -> None:
        self._ocr_result = result
        dpr = self._dpr
        ox = self._selection_rect.left()
        oy = self._selection_rect.top()

        self._word_rects = [
            (
                w,
                QRectF(
                    ox + (w.x / dpr) - 2,
                    oy + (w.y / dpr) - 2,
                    (w.width / dpr) + 4,
                    (w.height / dpr) + 4,
                ),
            )
            for w in result.words
        ]
        self.update()

        if not result.full_text:
            self._tips_panel.set_loading("No se detectó texto en esa zona. Probá con otro recorte.")
            self._position_tips_panel()
            return

        self._tips_panel.set_loading(
            f"OCR listo ({len(result.words)} palabras). Buscando chunks y tips con Gemini..."
        )
        self._position_tips_panel()

        self._tutor_worker = TutorWorker(result.full_text)
        self._tutor_worker.finished_analysis.connect(self._on_analysis_done)
        self._tutor_worker.start()

    def _on_ocr_error(self, message: str) -> None:
        self._tips_panel.set_loading(f"Error en OCR local: {message}")
        self._position_tips_panel()

    def _on_analysis_done(self, analysis: TutorAnalysis) -> None:
        self._analysis = analysis
        word_count = len(self._ocr_result.words) if self._ocr_result else 0
        ocr_lang = self._ocr_result.language_tag if self._ocr_result else "?"
        self._tips_panel.show_analysis(analysis, word_count, ocr_lang)
        self._position_tips_panel()

        # Si el usuario ya había hecho clic en una palabra mientras cargaba, actualizamos el tooltip
        if self._selected_index != -1:
            self._show_word_popup(self._selected_index)

    def _hit_test_word(self, pos: QPoint) -> int:
        for i, (_, rect) in enumerate(self._word_rects):
            if rect.contains(pos):
                return i
        return -1

    def _show_word_popup(self, index: int) -> None:
        word, rect = self._word_rects[index]
        if self._analysis is None:
            self._tooltip.show_word(word.text, "Cargando traducción...", "", rect)
            return

        entry = self._analysis.lookup_word(word.text)
        chunks = self._analysis.find_chunks_for_word(word.text)

        if entry is not None:
            title = f"{entry.word}  ({entry.lemma})" if entry.lemma.lower() != entry.word.lower() else entry.word
            meta_parts = [entry.pos] if entry.pos else []
            if entry.note:
                meta_parts.append(entry.note)
            if chunks:
                chunk_txt = " · ".join(f"Parte de “{c.phrase}” = {c.meaning}" for c in chunks)
                meta_parts.append(chunk_txt)
            self._tooltip.show_word(title, entry.translation, " — ".join(meta_parts), rect)
        else:
            fallback = (
                "Sin traducción cargada (configurá GEMINI_API_KEY en .env)"
                if self._analysis.status_message
                else "Palabra detectada (sin nota adicional)"
            )
            self._tooltip.show_word(word.text, fallback, "", rect)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Fondo: nítido (con velo leve) mientras seleccionás; desenfocado recién al soltar el mouse
        if self._state == "selecting":
            painter.drawPixmap(0, 0, self._original_pixmap)
            painter.fillRect(self.rect(), QColor(15, 23, 42, 65))
        else:
            painter.drawPixmap(0, 0, self._blurred_pixmap)

        # 2. Región seleccionada nítida (sin velo ni desenfoque)
        if not self._selection_rect.isNull():
            painter.save()
            painter.setClipRect(self._selection_rect)
            painter.drawPixmap(0, 0, self._original_pixmap)
            painter.restore()

            border_pen = QPen(QColor("#38bdf8"), 2)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self._selection_rect, 4, 4)

        # 3. Cajas interactivas por palabra detectada
        if self._state == "reading" and self._word_rects:
            for i, (_, rect) in enumerate(self._word_rects):
                if i == self._selected_index:
                    painter.setPen(QPen(QColor("#38bdf8"), 1.6))
                    painter.setBrush(QColor(56, 189, 248, 65))
                    painter.drawRoundedRect(rect, 3, 3)
                elif i == self._hovered_index:
                    painter.setPen(QPen(QColor(56, 189, 248, 210), 1.2))
                    painter.setBrush(QColor(56, 189, 248, 38))
                    painter.drawRoundedRect(rect, 3, 3)
                else:
                    painter.setPen(QPen(QColor(56, 189, 248, 55), 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(rect, 3, 3)

        painter.end()
