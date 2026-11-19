"""Overlay fullscreen con desenfoque, Visual Noticing progresivo por frase y tips antes de traducir."""

from __future__ import annotations

from typing import Optional

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ai_tutor import (
    GrammarPoint,
    LexicalChunk,
    TutorAnalysis,
    WordTranslation,
    analyze_text_with_gemini,
    check_user_comprehension,
    compute_sentence_groups,
    match_pattern_indices,
)
from capture import ScreenCapture
from common_words import lookup_common_word
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


class ComprehensionWorker(QThread):
    """Evalúa la comprensión escrita del usuario (Retrieval Practice) en segundo plano."""

    finished_feedback = Signal(str)

    def __init__(self, original_text: str, user_summary: str) -> None:
        super().__init__()
        self._original_text = original_text
        self._user_summary = user_summary

    def run(self) -> None:
        feedback = check_user_comprehension(self._original_text, self._user_summary)
        self.finished_feedback.emit(feedback)


class WordTooltipCard(QFrame):
    """Tarjetita flotante con soporte de Modo Desafío (tip interpretativo → revelar español)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("wordTooltip")
        self.setStyleSheet(
            """
            QFrame#wordTooltip {
                background-color: rgba(15, 23, 42, 246);
                border: 1px solid rgba(56, 189, 248, 0.8);
                border-radius: 11px;
            }
            QLabel {
                color: #f8fafc;
                background: transparent;
            }
            QPushButton#revealBtn {
                background-color: rgba(56, 189, 248, 0.18);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.6);
                border-radius: 7px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#revealBtn:hover {
                background-color: rgba(56, 189, 248, 0.35);
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(5)

        self.title_label = QLabel()
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #38bdf8;")

        self.main_label = QLabel()
        self.main_label.setFont(QFont("Segoe UI", 10.5, QFont.Weight.DemiBold))
        self.main_label.setWordWrap(True)

        self.meta_label = QLabel()
        self.meta_label.setFont(QFont("Segoe UI", 9))
        self.meta_label.setStyleSheet("color: #94a3b8;")
        self.meta_label.setWordWrap(True)

        self.reveal_btn = QPushButton("Revelar traducción (Espacio)")
        self.reveal_btn.setObjectName("revealBtn")
        self.reveal_btn.clicked.connect(self.reveal_answer)
        self.reveal_btn.hide()

        layout.addWidget(self.title_label)
        layout.addWidget(self.main_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.reveal_btn)
        self.setMaximumWidth(350)
        self.hide()

        self._anchor_rect = QRectF()
        self._pending_reveal_title = ""
        self._pending_reveal_text = ""
        self._pending_reveal_meta = ""
        self._is_hidden_answer = False

    def show_instant(self, title: str, text: str, meta: str, anchor_rect: QRectF) -> None:
        self._is_hidden_answer = False
        self._anchor_rect = anchor_rect
        self.reveal_btn.hide()
        self.title_label.setText(title)
        self.main_label.setText(text)
        self.main_label.setStyleSheet("color: #f8fafc;")
        self.meta_label.setText(meta)
        self.meta_label.setVisible(bool(meta))
        self._place_near(anchor_rect)

    def show_challenge(
        self,
        title: str,
        clue: str,
        reveal_title: str,
        reveal_text: str,
        reveal_meta: str,
        anchor_rect: QRectF,
    ) -> None:
        """Muestra primero un tip interpretativo para deducir la palabra antes de traducirla."""
        self._is_hidden_answer = True
        self._anchor_rect = anchor_rect
        self._pending_reveal_title = reveal_title
        self._pending_reveal_text = reveal_text
        self._pending_reveal_meta = reveal_meta

        self.title_label.setText(f"🧠 {title}")
        self.main_label.setText(f"Tip: {clue}")
        self.main_label.setStyleSheet("color: #fde68a;")
        self.meta_label.setText("Intentá interpretarla antes de revelar")
        self.meta_label.show()
        self.reveal_btn.show()
        self._place_near(anchor_rect)

    def is_awaiting_reveal(self) -> bool:
        return self.isVisible() and self._is_hidden_answer

    def reveal_answer(self) -> None:
        if not self._is_hidden_answer:
            return
        self.show_instant(
            self._pending_reveal_title,
            self._pending_reveal_text,
            self._pending_reveal_meta,
            self._anchor_rect,
        )

    def _place_near(self, anchor_rect: QRectF) -> None:
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


class InteractiveInsightCard(QFrame):
    """Tarjeta de estructura argumentativa/gramatical o chunk con soporte hover/pin."""

    hovered_changed = Signal(object, str, bool)  # indices: list[int], kind: str, entering: bool
    pin_toggled = Signal(object, object, str)    # card: self, indices: list[int], kind: str

    def __init__(
        self,
        html_text: str,
        word_indices: list[int],
        kind: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.word_indices = word_indices
        self.word_index_set = set(word_indices)
        self.kind = kind  # "grammar" | "chunk"
        self._pinned = False

        self.setCursor(
            Qt.CursorShape.PointingHandCursor if word_indices else Qt.CursorShape.ArrowCursor
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(2)

        self._label = QLabel(html_text)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setFont(QFont("Segoe UI", 9.5))
        self._label.setStyleSheet("background: transparent;")
        layout.addWidget(self._label)
        self._apply_style(hovered=False)

    def set_pinned(self, pinned: bool) -> None:
        self._pinned = pinned
        self._apply_style(hovered=False)

    def _apply_style(self, hovered: bool) -> None:
        accent = "52, 211, 153" if self.kind == "grammar" else "167, 139, 250"
        if self._pinned:
            self.setStyleSheet(
                f"InteractiveInsightCard {{ background-color: rgba({accent}, 0.18); "
                f"border: 1px solid rgba({accent}, 0.85); border-radius: 8px; }}"
            )
        elif hovered and self.word_indices:
            self.setStyleSheet(
                f"InteractiveInsightCard {{ background-color: rgba({accent}, 0.11); "
                f"border: 1px solid rgba({accent}, 0.5); border-radius: 8px; }}"
            )
        else:
            self.setStyleSheet(
                "InteractiveInsightCard { background-color: rgba(30, 41, 59, 0.58); "
                "border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; }"
            )

    def enterEvent(self, event) -> None:
        self._apply_style(hovered=True)
        if self.word_indices:
            self.hovered_changed.emit(self.word_indices, self.kind, True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._apply_style(hovered=False)
        if self.word_indices:
            self.hovered_changed.emit(self.word_indices, self.kind, False)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.word_indices:
            self.pin_toggled.emit(self, self.word_indices, self.kind)
        super().mousePressEvent(event)


class TipsPanel(QFrame):
    """Panel progresivo: barra compacta por defecto; despliega la estructura de la frase al posarte sobre ella."""

    close_requested = Signal()
    recapture_requested = Signal()
    challenge_mode_changed = Signal(bool)
    show_all_changed = Signal(bool)
    highlight_hover_changed = Signal(object, str, bool)
    highlight_pinned = Signal(object, str)
    comprehension_submitted = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._grammar_items: list[tuple[GrammarPoint, list[int]]] = []
        self._chunk_items: list[tuple[LexicalChunk, list[int]]] = []
        self._sentence_groups: list[set[int]] = []
        self._cards: list[InteractiveInsightCard] = []
        self._pinned_card: Optional[InteractiveInsightCard] = None
        self._active_word_filter: int = -1

        self._challenge_mode = True
        self._show_all = False
        self._has_analysis = False
        self._drag_offset: Optional[QPoint] = None
        self._manually_moved = False

        self.setObjectName("tipsPanel")
        self.setStyleSheet(
            """
            QFrame#tipsPanel {
                background-color: rgba(15, 23, 42, 240);
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
                padding: 4px 9px;
                font-size: 11.5px;
            }
            QPushButton:hover {
                background-color: rgba(56, 189, 248, 0.28);
                border-color: #38bdf8;
            }
            QLineEdit {
                background-color: rgba(30, 41, 59, 0.95);
                color: #f8fafc;
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 7px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(7)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.header_title = QLabel("🔍 English Lens")
        self.header_title.setFont(QFont("Segoe UI", 10.5, QFont.Weight.Bold))
        self.header_title.setStyleSheet("color: #38bdf8;")

        self.challenge_btn = QPushButton("🧠 Desafío: ON")
        self.challenge_btn.setToolTip(
            "Cuando está activo, al tocar una palabra te tira un tip primero antes de mostrar el español"
        )
        self.challenge_btn.clicked.connect(self._toggle_challenge_mode)
        self._update_challenge_btn_style()

        self.show_all_btn = QPushButton("📋 Ver todo")
        self.show_all_btn.setToolTip("Expandir todas las estructuras gramaticales y chunks a la vez")
        self.show_all_btn.clicked.connect(self._toggle_show_all)
        self.show_all_btn.hide()

        self.recapture_btn = QPushButton("Nuevo recorte")
        self.recapture_btn.clicked.connect(self.recapture_requested.emit)

        self.close_btn = QPushButton("Cerrar (Esc)")
        self.close_btn.clicked.connect(self.close_requested.emit)

        header.addWidget(self.header_title)
        header.addStretch()
        header.addWidget(self.challenge_btn)
        header.addWidget(self.show_all_btn)
        header.addWidget(self.recapture_btn)
        header.addWidget(self.close_btn)
        outer.addLayout(header)

        self.status_label = QLabel("Analizando texto...")
        self.status_label.setFont(QFont("Segoe UI", 9.5))
        self.status_label.setStyleSheet("color: #94a3b8;")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMaximumHeight(280)
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 2, 0, 2)
        self.content_layout.setSpacing(6)
        self.scroll.setWidget(self.content_widget)
        self.scroll.hide()
        outer.addWidget(self.scroll)

        # Sección de Retrieval Practice ("¿Entendí bien?")
        self.check_toggle_btn = QPushButton("✍️ ¿Entendí bien? Comprobar mi lectura en 1 frase")
        self.check_toggle_btn.clicked.connect(self._toggle_check_box)
        self.check_toggle_btn.hide()
        outer.addWidget(self.check_toggle_btn)

        self.check_container = QWidget()
        self.check_container.setStyleSheet("background: transparent;")
        check_layout = QVBoxLayout(self.check_container)
        check_layout.setContentsMargins(0, 2, 0, 0)
        check_layout.setSpacing(6)

        row = QHBoxLayout()
        self.summary_input = QLineEdit()
        self.summary_input.setPlaceholderText("Escribí en español qué entendiste del fragmento y apretá Enter...")
        self.summary_input.returnPressed.connect(self._submit_summary)

        self.verify_btn = QPushButton("Verificar")
        self.verify_btn.clicked.connect(self._submit_summary)
        row.addWidget(self.summary_input)
        row.addWidget(self.verify_btn)
        check_layout.addLayout(row)

        self.feedback_label = QLabel()
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setFont(QFont("Segoe UI", 9.5))
        self.feedback_label.setStyleSheet(
            "background-color: rgba(30, 41, 59, 0.85); color: #e2e8f0; "
            "border-left: 3px solid #34d399; border-radius: 6px; padding: 7px 10px;"
        )
        self.feedback_label.hide()
        check_layout.addWidget(self.feedback_label)
        self.check_container.hide()
        outer.addWidget(self.check_container)

        self.setFixedWidth(640)
        self.hide()

    def is_challenge_mode(self) -> bool:
        return self._challenge_mode

    def is_show_all(self) -> bool:
        return self._show_all

    def is_typing_summary(self) -> bool:
        return self.summary_input.hasFocus()

    def was_manually_moved(self) -> bool:
        return self._manually_moved

    def reset_manual_move(self) -> None:
        self._manually_moved = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            parent = self.parentWidget()
            new_pos = self.pos() + (event.position().toPoint() - self._drag_offset)
            if parent is not None:
                nx = max(8, min(new_pos.x(), parent.width() - self.width() - 8))
                ny = max(8, min(new_pos.y(), parent.height() - self.height() - 8))
                new_pos = QPoint(nx, ny)
            self.move(new_pos)
            self._manually_moved = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def _toggle_challenge_mode(self) -> None:
        self._challenge_mode = not self._challenge_mode
        self._update_challenge_btn_style()
        self.challenge_mode_changed.emit(self._challenge_mode)

    def _toggle_show_all(self) -> None:
        self._show_all = not self._show_all
        self._update_show_all_btn_style()
        self._render_cards_for_context(self._active_word_filter)
        self.show_all_changed.emit(self._show_all)

    def _update_challenge_btn_style(self) -> None:
        if self._challenge_mode:
            self.challenge_btn.setText("🧠 Desafío: ON")
            self.challenge_btn.setStyleSheet(
                "background-color: rgba(52, 211, 153, 0.2); color: #34d399; "
                "border: 1px solid rgba(52, 211, 153, 0.65); border-radius: 7px; padding: 4px 9px; font-size: 11.5px;"
            )
        else:
            self.challenge_btn.setText("🧠 Desafío: OFF")
            self.challenge_btn.setStyleSheet("")

    def _update_show_all_btn_style(self) -> None:
        if self._show_all:
            self.show_all_btn.setText("📋 Ocultar lista")
            self.show_all_btn.setStyleSheet(
                "background-color: rgba(56, 189, 248, 0.22); color: #38bdf8; "
                "border: 1px solid rgba(56, 189, 248, 0.65); border-radius: 7px; padding: 4px 9px; font-size: 11.5px;"
            )
        else:
            self.show_all_btn.setText("📋 Ver todo")
            self.show_all_btn.setStyleSheet("")

    def _toggle_check_box(self) -> None:
        visible = not self.check_container.isVisible()
        self.check_container.setVisible(visible)
        if visible:
            self.summary_input.setFocus()
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None and hasattr(parent, "_position_tips_panel"):
            parent._position_tips_panel()

    def _submit_summary(self) -> None:
        text = self.summary_input.text().strip()
        if not text:
            return
        self.verify_btn.setEnabled(False)
        self.feedback_label.setText("Evaluando tu lectura...")
        self.feedback_label.show()
        self.adjustSize()
        self.comprehension_submitted.emit(text)

    def show_comprehension_feedback(self, feedback: str) -> None:
        self.verify_btn.setEnabled(True)
        self.feedback_label.setText(feedback)
        self.feedback_label.show()
        self.adjustSize()

    def _clear_cards(self) -> None:
        self._cards.clear()
        self._pinned_card = None
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def set_loading(self, message: str) -> None:
        self._has_analysis = False
        self._grammar_items.clear()
        self._chunk_items.clear()
        self._sentence_groups.clear()
        self._active_word_filter = -1
        self._show_all = False
        self._update_show_all_btn_style()
        self._clear_cards()
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #94a3b8;")
        self.status_label.show()
        self.show_all_btn.hide()
        self.scroll.hide()
        self.check_toggle_btn.hide()
        self.check_container.hide()
        self.feedback_label.hide()
        self.summary_input.clear()
        self.adjustSize()

    def _on_card_pin_toggled(self, card: InteractiveInsightCard, indices: list[int], kind: str) -> None:
        if self._pinned_card is card:
            card.set_pinned(False)
            self._pinned_card = None
            self.highlight_pinned.emit([], kind)
            return

        if self._pinned_card is not None:
            self._pinned_card.set_pinned(False)

        self._pinned_card = card
        card.set_pinned(True)
        self.highlight_pinned.emit(indices, kind)

    def load_analysis(
        self,
        analysis: TutorAnalysis,
        ocr_tokens: list[str],
        ocr_lang: str,
    ) -> list[tuple[set[int], str]]:
        """Guarda las estructuras detectadas sin mostrar todo de golpe."""
        self._has_analysis = True
        self._grammar_items.clear()
        self._chunk_items.clear()
        self._sentence_groups = compute_sentence_groups(ocr_tokens)
        self._active_word_filter = -1
        all_spans: list[tuple[set[int], str]] = []

        for gp in analysis.grammar_points:
            indices = match_pattern_indices(ocr_tokens, gp.pattern)
            self._grammar_items.append((gp, indices))
            if indices:
                all_spans.append((set(indices), "grammar"))

        for chunk in analysis.chunks:
            indices = match_pattern_indices(ocr_tokens, chunk.phrase)
            self._chunk_items.append((chunk, indices))
            if indices:
                all_spans.append((set(indices), "chunk"))

        if analysis.error_message:
            self.status_label.setText(analysis.error_message)
            self.status_label.setStyleSheet("color: #fbbf24;")
            self.show_all_btn.hide()
            self.check_toggle_btn.hide()
        else:
            g_count = len(self._grammar_items)
            c_count = len(self._chunk_items)
            self.status_label.setText(
                f"Posate sobre una frase subrayada para ver su estructura ({g_count} reglas · {c_count} chunks) · "
                f"Tocá una palabra para ver su tip ({ocr_lang})"
            )
            self.status_label.setStyleSheet("color: #94a3b8;")
            self.show_all_btn.setVisible(bool(g_count or c_count))
            self.check_toggle_btn.show()

        self._render_cards_for_context(-1)
        return all_spans

    def update_for_hovered_word(self, word_index: int) -> tuple[set[int], str]:
        """Actualiza el panel según la frase bajo el cursor y devuelve los índices a iluminar arriba."""
        if not self._has_analysis:
            return set(), ""
        if word_index == self._active_word_filter:
            return self._matching_highlight_for_word(word_index)

        self._active_word_filter = word_index
        if not self._show_all:
            self._render_cards_for_context(word_index)
        return self._matching_highlight_for_word(word_index)

    def _sentence_for_word(self, word_index: int) -> set[int]:
        for group in self._sentence_groups:
            if word_index in group:
                return group
        return set()

    def _select_items_for_word(
        self,
        word_index: int,
    ) -> tuple[list[tuple[GrammarPoint, list[int]]], list[tuple[LexicalChunk, list[int]]]]:
        if self._show_all:
            return self._grammar_items, self._chunk_items
        if word_index < 0:
            return [], []

        sentence_set = self._sentence_for_word(word_index)

        # Prioridad 1: estructuras/chunks que contienen exactamente la palabra bajo el mouse
        direct_g = [(gp, idx) for gp, idx in self._grammar_items if word_index in idx]
        direct_c = [(ch, idx) for ch, idx in self._chunk_items if word_index in idx]

        # Si tocó la misma oración de una estructura/chunk aunque no la palabra exacta, mostrar los de esa frase
        if not direct_g and sentence_set:
            direct_g = [
                (gp, idx) for gp, idx in self._grammar_items if any(i in sentence_set for i in idx)
            ]
        if not direct_c and sentence_set:
            direct_c = [
                (ch, idx) for ch, idx in self._chunk_items if any(i in sentence_set for i in idx)
            ]
        return direct_g, direct_c

    def _matching_highlight_for_word(self, word_index: int) -> tuple[set[int], str]:
        if word_index < 0:
            return set(), ""
        matched_g, matched_c = self._select_items_for_word(word_index)

        # Si el cursor está justo encima de un chunk, priorizamos el violeta del chunk; si no, verde de gramática
        for _, idx in matched_c:
            if word_index in idx:
                return set(idx), "chunk"
        for _, idx in matched_g:
            if word_index in idx:
                return set(idx), "grammar"

        combined_g: set[int] = set()
        for _, idx in matched_g:
            combined_g.update(idx)
        if combined_g:
            return combined_g, "grammar"

        combined_c: set[int] = set()
        for _, idx in matched_c:
            combined_c.update(idx)
        if combined_c:
            return combined_c, "chunk"
        return set(), ""

    def _render_cards_for_context(self, word_index: int) -> None:
        self._clear_cards()
        g_items, c_items = self._select_items_for_word(word_index)

        has_blocks = False
        if g_items:
            has_blocks = True
            gram_title = QLabel("📐 Estructura argumentativa y gramática")
            gram_title.setFont(QFont("Segoe UI", 9.5, QFont.Weight.Bold))
            gram_title.setStyleSheet("color: #34d399;")
            self.content_layout.addWidget(gram_title)

            for gp, indices in g_items:
                html = (
                    f"<b style='color:#f8fafc;'>“{gp.pattern}”</b> "
                    f"<span style='color:#34d399;'>[{gp.concept}]</span><br>"
                    f"<span style='color:#e2e8f0;'>{gp.how_to_read}</span>"
                )
                card = InteractiveInsightCard(html, indices, "grammar", self.content_widget)
                card.hovered_changed.connect(self.highlight_hover_changed.emit)
                card.pin_toggled.connect(self._on_card_pin_toggled)
                self._cards.append(card)
                self.content_layout.addWidget(card)

        if c_items:
            has_blocks = True
            sec_title = QLabel("🧩 Frases de manual / Chunks")
            sec_title.setFont(QFont("Segoe UI", 9.5, QFont.Weight.Bold))
            sec_title.setStyleSheet("color: #a78bfa;")
            self.content_layout.addWidget(sec_title)

            for chunk, indices in c_items:
                html = (
                    f"<b style='color:#f8fafc;'>“{chunk.phrase}”</b> → "
                    f"<span style='color:#38bdf8;'>{chunk.meaning}</span><br>"
                    f"<span style='color:#cbd5e1;'>{chunk.tip}</span>"
                )
                card = InteractiveInsightCard(html, indices, "chunk", self.content_widget)
                card.hovered_changed.connect(self.highlight_hover_changed.emit)
                card.pin_toggled.connect(self._on_card_pin_toggled)
                self._cards.append(card)
                self.content_layout.addWidget(card)

        self.scroll.setVisible(has_blocks)
        self.adjustSize()


class LensOverlay(QWidget):
    """Ventana fullscreen con desenfoque al soltar, Visual Noticing progresivo y tips por palabra."""

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

        # Visual Noticing: subrayado sobre la captura + foco progresivo al posarse en la frase
        self._grammar_indices: set[int] = set()
        self._chunk_indices: set[int] = set()
        self._phrase_hover_highlight: tuple[set[int], str] = (set(), "")
        self._card_hover_highlight: tuple[set[int], str] = (set(), "")
        self._pinned_highlight: tuple[set[int], str] = (set(), "")

        self._ocr_worker: Optional[OcrWorker] = None
        self._tutor_worker: Optional[TutorWorker] = None
        self._comp_worker: Optional[ComprehensionWorker] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

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
        self._tips_panel.highlight_hover_changed.connect(self._on_card_highlight_hover)
        self._tips_panel.highlight_pinned.connect(self._on_highlight_pinned)
        self._tips_panel.comprehension_submitted.connect(self._on_comprehension_submitted)
        self._tips_panel.challenge_mode_changed.connect(self._on_challenge_mode_changed)
        self._tips_panel.show_all_changed.connect(self._on_show_all_changed)

    def _on_card_highlight_hover(self, indices: list[int], kind: str, entering: bool) -> None:
        self._card_hover_highlight = (set(indices), kind) if entering else (set(), "")
        self.update()

    def _on_highlight_pinned(self, indices: list[int], kind: str) -> None:
        self._pinned_highlight = (set(indices), kind) if indices else (set(), "")
        self.update()

    def _on_show_all_changed(self, _show_all: bool) -> None:
        self._position_tips_panel()

    def _on_challenge_mode_changed(self, _enabled: bool) -> None:
        if self._selected_index != -1 and self._tooltip.isVisible():
            self._show_word_popup(self._selected_index)

    def _on_comprehension_submitted(self, user_summary: str) -> None:
        if not self._ocr_result:
            return
        self._comp_worker = ComprehensionWorker(self._ocr_result.full_text, user_summary)
        self._comp_worker.finished_feedback.connect(self._on_comprehension_done)
        self._comp_worker.start()

    def _on_comprehension_done(self, feedback: str) -> None:
        self._tips_panel.show_comprehension_feedback(feedback)
        self._position_tips_panel()

    def _reset_to_selection(self) -> None:
        self._state = "selecting"
        self._drag_start = None
        self._selection_rect = QRect()
        self._ocr_result = None
        self._analysis = None
        self._word_rects = []
        self._hovered_index = -1
        self._selected_index = -1
        self._grammar_indices.clear()
        self._chunk_indices.clear()
        self._phrase_hover_highlight = (set(), "")
        self._card_hover_highlight = (set(), "")
        self._pinned_highlight = (set(), "")
        self._tooltip.hide()
        self._tips_panel.hide()
        self._tips_panel.reset_manual_move()
        self._hud.setText("Arrastrá sobre el texto en inglés · Esc para cancelar")
        self._hud.adjustSize()
        self._hud.move((self.width() - self._hud.width()) // 2, 18)
        self._hud.show()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def _position_tips_panel(self) -> None:
        """Ubica el panel donde haya más espacio (arriba, abajo, derecha o izquierda) sin tapar el recorte."""
        if self._tips_panel.was_manually_moved() and self._tips_panel.isVisible():
            self._tips_panel.adjustSize()
            return

        pw, ph = self.width(), self.height()
        sel = self._selection_rect
        margin = 16
        gap = 14

        space_above = max(0, sel.top() - gap - margin)
        space_below = max(0, (ph - margin) - (sel.bottom() + gap))
        space_left = max(0, sel.left() - gap - margin)
        space_right = max(0, (pw - margin) - (sel.right() + gap))

        candidates = [
            ("below", pw - 2 * margin, space_below),
            ("above", pw - 2 * margin, space_above),
            ("right", space_right, ph - 2 * margin),
            ("left", space_left, ph - 2 * margin),
        ]

        def score(item: tuple[str, int, int]) -> tuple[int, int, int, int]:
            side, avail_w, avail_h = item
            fits_expanded = int(avail_w >= 380 and avail_h >= 240)
            fits_compact = int(avail_w >= 360 and avail_h >= 150)
            wide_bonus = int(side in ("above", "below") and avail_h >= 240 and avail_w >= 520)
            usable_area = min(avail_w, 660) * min(avail_h, 460)
            return (fits_expanded, fits_compact, wide_bonus, usable_area)

        best_side, best_w, best_h = max(candidates, key=score)

        target_w = max(340, min(640, best_w))
        self._tips_panel.setFixedWidth(target_w)

        chrome_h = 145 if self._tips_panel.check_container.isVisible() else 108
        max_scroll_h = max(80, min(320, best_h - chrome_h))
        self._tips_panel.scroll.setMaximumHeight(max_scroll_h)
        self._tips_panel.adjustSize()
        if self._tips_panel.height() > best_h:
            overflow = self._tips_panel.height() - best_h
            self._tips_panel.scroll.setMaximumHeight(max(64, max_scroll_h - overflow - 4))
            self._tips_panel.adjustSize()

        panel_w = self._tips_panel.width()
        panel_h = self._tips_panel.height()

        if best_side == "below":
            x = int(sel.center().x() - panel_w / 2)
            y = sel.bottom() + gap
        elif best_side == "above":
            x = int(sel.center().x() - panel_w / 2)
            y = sel.top() - gap - panel_h
        elif best_side == "right":
            x = sel.right() + gap
            y = int(sel.center().y() - panel_h / 2)
        else:
            x = sel.left() - gap - panel_w
            y = int(sel.center().y() - panel_h / 2)

        x = max(margin, min(x, pw - panel_w - margin))
        y = max(margin, min(y, ph - panel_h - margin))

        self._tips_panel.move(x, y)
        self._tips_panel.show()
        self._tips_panel.raise_()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if (
            event.key() == Qt.Key.Key_Space
            and not self._tips_panel.is_typing_summary()
            and self._tooltip.is_awaiting_reveal()
        ):
            self._tooltip.reveal_answer()
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
                # Si el mouse salió hacia el panel mismo, mantenemos lo mostrado para poder interactuar
                if idx != -1 or not self._tips_panel.geometry().contains(pos):
                    prev_scroll = self._tips_panel.scroll.isVisible()
                    prev_h = self._tips_panel.height()
                    hi_indices, hi_kind = self._tips_panel.update_for_hovered_word(idx)
                    self._phrase_hover_highlight = (hi_indices, hi_kind)
                    if (
                        prev_scroll != self._tips_panel.scroll.isVisible()
                        or abs(prev_h - self._tips_panel.height()) > 6
                    ):
                        self._position_tips_panel()
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
            f"OCR listo ({len(result.words)} palabras). Analizando estructura argumentativa y tips..."
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
        ocr_tokens = [w.text for w, _ in self._word_rects]
        ocr_lang = self._ocr_result.language_tag if self._ocr_result else "?"
        spans = self._tips_panel.load_analysis(analysis, ocr_tokens, ocr_lang)

        self._grammar_indices.clear()
        self._chunk_indices.clear()
        for indices, kind in spans:
            if kind == "grammar":
                self._grammar_indices.update(indices)
            elif kind == "chunk":
                self._chunk_indices.update(indices)

        self._position_tips_panel()
        self.update()

        if self._selected_index != -1:
            self._show_word_popup(self._selected_index)

    def _hit_test_word(self, pos: QPoint) -> int:
        for i, (_, rect) in enumerate(self._word_rects):
            if rect.contains(pos):
                return i
        return -1

    def _build_entry_details(self, entry: WordTranslation, chunks) -> tuple[str, str]:
        title = (
            f"{entry.word}  ({entry.lemma})"
            if entry.lemma.lower() != entry.word.lower().strip(".,;:!?\"'()")
            else entry.word
        )
        meta_parts = [entry.pos] if entry.pos else []
        if entry.note:
            meta_parts.append(entry.note)
        if chunks:
            chunk_txt = " · ".join(f"Parte de “{c.phrase}” = {c.meaning}" for c in chunks)
            meta_parts.append(chunk_txt)
        return title, " — ".join(meta_parts)

    def _show_word_popup(self, index: int) -> None:
        word, rect = self._word_rects[index]
        challenge_on = self._tips_panel.is_challenge_mode()

        if self._analysis is None:
            local = lookup_common_word(word.text)
            if local is not None:
                base, tr, pos, tip, is_trivial = local
                title = (
                    f"{word.text}  ({base})"
                    if base != word.text.lower().strip(".,;:!?\"'()")
                    else word.text
                )
                if challenge_on and not is_trivial and tip:
                    self._tooltip.show_challenge(
                        word.text, tip, title, tr, f"{pos} · diccionario local", rect
                    )
                else:
                    self._tooltip.show_instant(title, tr, f"{pos} · diccionario local", rect)
            else:
                self._tooltip.show_instant(word.text, "Analizando contexto...", "", rect)
            return

        entry, is_trivial = self._analysis.lookup_word(word.text)
        chunks = self._analysis.find_chunks_for_word(word.text)

        if entry is not None:
            title, meta = self._build_entry_details(entry, chunks)
            if challenge_on and not is_trivial:
                tip = entry.clue.strip() or (
                    f"({entry.pos}) Mirá su posición en la frase y las palabras vecinas para deducirla."
                )
                self._tooltip.show_challenge(
                    word.text,
                    tip,
                    title,
                    entry.translation,
                    meta,
                    rect,
                )
            else:
                self._tooltip.show_instant(title, entry.translation, meta, rect)
        elif chunks:
            chunk_txt = " / ".join(f"“{c.phrase}” → {c.meaning}" for c in chunks)
            if challenge_on:
                tip = chunks[0].tip or "Forma parte de una frase hecha: leé las palabras vecinas como bloque."
                self._tooltip.show_challenge(
                    word.text,
                    tip,
                    word.text,
                    chunk_txt,
                    "parte de una frase de manual",
                    rect,
                )
            else:
                self._tooltip.show_instant(word.text, chunk_txt, "parte de una frase de manual", rect)
        elif self._analysis.error_message:
            self._tooltip.show_instant(word.text, "Sin conexión con Gemini", self._analysis.error_message, rect)
        else:
            self._tooltip.show_instant(
                word.text,
                "Término o cognado transparente — fijate en su parecido al español y rol en la oración.",
                "",
                rect,
            )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Fondo: nítido (con velo leve) mientras seleccionás; desenfocado al soltar el mouse
        if self._state == "selecting":
            painter.drawPixmap(0, 0, self._original_pixmap)
            painter.fillRect(self.rect(), QColor(15, 23, 42, 65))
        else:
            painter.drawPixmap(0, 0, self._blurred_pixmap)

        # 2. Región seleccionada nítida
        if not self._selection_rect.isNull():
            painter.save()
            painter.setClipRect(self._selection_rect)
            painter.drawPixmap(0, 0, self._original_pixmap)
            painter.restore()

            painter.setPen(QPen(QColor("#38bdf8"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self._selection_rect, 4, 4)

        # 3. Cajas interactivas + Visual Noticing progresivo sobre la captura
        if self._state == "reading" and self._word_rects:
            if self._card_hover_highlight[0]:
                active_indices, active_kind = self._card_hover_highlight
            elif self._phrase_hover_highlight[0]:
                active_indices, active_kind = self._phrase_hover_highlight
            else:
                active_indices, active_kind = self._pinned_highlight

            active_color = QColor("#34d399") if active_kind == "grammar" else QColor("#a78bfa")

            for i, (_, rect) in enumerate(self._word_rects):
                is_active_notice = i in active_indices

                if is_active_notice:
                    fill = QColor(active_color)
                    fill.setAlpha(55)
                    painter.setPen(QPen(active_color, 1.5))
                    painter.setBrush(fill)
                    painter.drawRoundedRect(rect, 3, 3)
                    painter.setPen(QPen(active_color, 2.6))
                    painter.drawLine(
                        int(rect.left() + 1),
                        int(rect.bottom() + 1),
                        int(rect.right() - 1),
                        int(rect.bottom() + 1),
                    )
                elif i == self._selected_index:
                    painter.setPen(QPen(QColor("#38bdf8"), 1.6))
                    painter.setBrush(QColor(56, 189, 248, 65))
                    painter.drawRoundedRect(rect, 3, 3)
                elif i == self._hovered_index:
                    painter.setPen(QPen(QColor(56, 189, 248, 210), 1.2))
                    painter.setBrush(QColor(56, 189, 248, 38))
                    painter.drawRoundedRect(rect, 3, 3)
                else:
                    painter.setPen(QPen(QColor(56, 189, 248, 35), 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(rect, 3, 3)

                if not is_active_notice:
                    if i in self._grammar_indices:
                        painter.setPen(QPen(QColor(52, 211, 153, 185), 1.8))
                        painter.drawLine(
                            int(rect.left() + 1),
                            int(rect.bottom()),
                            int(rect.right() - 1),
                            int(rect.bottom()),
                        )
                    elif i in self._chunk_indices:
                        painter.setPen(QPen(QColor(167, 139, 250, 185), 1.8))
                        painter.drawLine(
                            int(rect.left() + 1),
                            int(rect.bottom()),
                            int(rect.right() - 1),
                            int(rect.bottom()),
                        )

        painter.end()
