"""Tutor lingüístico basado en Google Gemini API (tier gratuito) + diccionario local liviano.

Aplica los principios documentados en docs/01-fundamentos-aprendizaje.md y
docs/03-investigacion-aprendizaje-e-ideas.md:
- NO traduce el texto completo.
- Las palabras básicas/frecuentes se resuelven en 0 ms desde src/common_words.py (0 tokens).
- Gemini se enfoca en:
  1) Entender la GRAMÁTICA y cómo leer la estructura de las oraciones (Visual Noticing).
  2) Detectar frases de manual / chunks / phrasal verbs.
  3) Traducir palabras difíciles + dar una micro-pista previa (Involvement Load).
  4) Verificar la comprensión escrita del usuario (Retrieval Practice).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from common_words import lookup_common_word

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class WordTranslation(BaseModel):
    word: str = Field(description="Palabra exacta del texto en inglés.")
    lemma: str = Field(description="Forma base o infinitivo si difiere (ej. 'went' -> 'go').")
    translation: str = Field(description="Traducción breve al español EXACTAMENTE para este contexto (1 a 4 palabras).")
    pos: str = Field(description="Categoría gramatical corta en español (ej. 'verbo', 'sustantivo', 'adjetivo').")
    clue: str = Field(
        default="",
        description=(
            "Micro-pista breve (máx. 12 palabras) SIN decir la traducción literal en español, "
            "para ayudar a deducirla antes de revelarla (ej. raíz/cognado, familia de palabras o sinónimo simple en inglés)."
        ),
    )
    note: str = Field(default="", description="Micro-nota opcional de máx. 10 palabras si hay matiz o falso amigo.")


class GrammarPoint(BaseModel):
    pattern: str = Field(
        description=(
            "Fragmento EXACTO extraído del texto original (podés usar '...' entre dos partes si no son contiguas, "
            "ej. 'If AI were to evade... it would be sufficient')."
        )
    )
    concept: str = Field(
        description="Función argumentativa + regla gramatical (ej. 'Hipótesis / 2do condicional (were to)', 'Concesión / Contraste', 'Aclaración causal')."
    )
    how_to_read: str = Field(
        description="Explicación breve en español de qué rol argumentativo cumple esa frase y cómo decodificar su gramática (1 a 2 líneas)."
    )


class LexicalChunk(BaseModel):
    phrase: str = Field(description="Expresión, phrasal verb, colocación o frase de manual exacta del texto.")
    meaning: str = Field(description="Significado natural en español.")
    tip: str = Field(description="Explicación de 1 línea de por qué se lee como bloque.")


class GeminiTutorPayload(BaseModel):
    """Esquema estricto que devuelve Gemini (sin campos internos de error)."""

    grammar_points: list[GrammarPoint] = Field(
        default_factory=list,
        description="Entre 2 y 4 explicaciones claras de la gramática y estructura del texto (PRIORIDAD PRINCIPAL).",
    )
    chunks: list[LexicalChunk] = Field(
        default_factory=list,
        description="Frases de manual, phrasal verbs, colocaciones o modismos (0 a 4).",
    )
    words: list[WordTranslation] = Field(
        default_factory=list,
        description="SOLO palabras de nivel intermedio/avanzado, técnicas o con significado especial en este contexto.",
    )


class TutorAnalysis(BaseModel):
    """Modelo completo consumido por la interfaz."""

    grammar_points: list[GrammarPoint] = Field(default_factory=list)
    chunks: list[LexicalChunk] = Field(default_factory=list)
    words: list[WordTranslation] = Field(default_factory=list)
    error_message: str = Field(default="")

    def lookup_word(self, raw_word: str) -> tuple[Optional[WordTranslation], bool]:
        """Devuelve (WordTranslation, is_trivial).

        Prioriza la traducción contextual de Gemini (con pista interpretativa) y cae al
        diccionario local liviano si corresponde.
        """
        target = normalize_token(raw_word)
        if not target:
            return None, False

        for entry in self.words:
            if normalize_token(entry.word) == target:
                return entry, False

        local = lookup_common_word(raw_word)
        if local is not None:
            base, translation, pos, tip, is_trivial = local
            return (
                WordTranslation(
                    word=raw_word,
                    lemma=base,
                    translation=translation,
                    pos=f"{pos} · local",
                    clue=tip,
                    note="",
                ),
                is_trivial,
            )

        return None, False

    def find_chunks_for_word(self, raw_word: str) -> list[LexicalChunk]:
        """Devuelve chunks/frases de manual que contengan esta palabra."""
        target = normalize_token(raw_word)
        if not target:
            return []
        matches = []
        for chunk in self.chunks:
            tokens = [normalize_token(t) for t in chunk.phrase.split()]
            if target in tokens:
                matches.append(chunk)
        return matches


def normalize_token(token: str) -> str:
    return re.sub(r"^[^a-zA-Z0-9']+|[^a-zA-Z0-9']+$", "", token).lower()


def match_pattern_indices(ocr_words: list[str], pattern: str) -> list[int]:
    """Encuentra los índices de las palabras del OCR que coinciden con `pattern`.

    Soporta fragmentos separados por '...' o '…' (ej. 'If AI were to evade... it would be sufficient').
    """
    if not ocr_words or not pattern:
        return []

    norm_ocr = [normalize_token(w) for w in ocr_words]
    segments = [seg.strip() for seg in re.split(r"\.\.\.|…", pattern) if seg.strip()]

    matched: list[int] = []
    search_from = 0

    for seg in segments:
        seg_tokens = [normalize_token(t) for t in seg.split()]
        seg_tokens = [t for t in seg_tokens if t]
        if not seg_tokens:
            continue

        found_start = -1
        span_len = len(seg_tokens)
        limit = len(norm_ocr) - span_len + 1
        for i in range(search_from, max(search_from, limit)):
            if norm_ocr[i : i + span_len] == seg_tokens:
                found_start = i
                break

        # Fallback: buscar desde el principio si el LLM reordenó segmentos
        if found_start == -1 and search_from > 0:
            for i in range(0, max(0, limit)):
                if norm_ocr[i : i + span_len] == seg_tokens:
                    found_start = i
                    break

        if found_start != -1:
            matched.extend(range(found_start, found_start + span_len))
            search_from = found_start + span_len

    return matched


def compute_sentence_groups(ocr_words: list[str]) -> list[set[int]]:
    """Agrupa índices de palabras OCR por oración para activar tips al posarse sobre la frase."""
    if not ocr_words:
        return []
    groups: list[set[int]] = []
    current: set[int] = set()
    for i, w in enumerate(ocr_words):
        current.add(i)
        stripped = w.strip()
        if stripped and stripped[-1] in ".!?":
            groups.append(current)
            current = set()
    if current:
        groups.append(current)
    return groups


SYSTEM_PROMPT = """Sos un profesor experto en lectura comprensiva de inglés para hispanohablantes (Enfoque Léxico + Noticing Hypothesis + Involvement Load).

El usuario capturó un fragmento en inglés y quiere ENTENDER LA ESTRUCTURA ARGUMENTATIVA Y GRAMATICAL por sí mismo, SIN que le traduzcas el párrafo entero.

PRIORIDADES Y REGLAS ESTRICTAS:
1. NUNCA traduzcas el texto completo ni las oraciones enteras.
2. PRIORIDAD #1 — `grammar_points` (2 a 4 puntos, uno por cada frase/cláusula relevante):
   Explicá qué rol argumentativo cumple esa frase (tesis, hipótesis, contraste, concesión, evidencia, consecuencia, aclaración) y cómo leer su gramática:
   - Tiempos verbales, condicionales, modales, voz pasiva, inversiones.
   - Orden de palabras distinto al español (ej: cadenas de adjetivos/sustantivos).
   - Conectores y cláusulas subordinadas.
   IMPORTANTE: En `pattern` copiá las palabras EXACTAS tal como aparecen en el texto (podés usar `...` si unís dos partes de la misma oración) para que aparezca JUSTO cuando el usuario se pose sobre esa frase.
3. PRIORIDAD #2 — `chunks` (0 a 4 bloques):
   Detectá "frases de manual", colocaciones fijas, phrasal verbs o modismos con sus palabras EXACTAS del texto.
4. PRIORIDAD #3 — `words` (vocabulario no elemental):
   Omití solo artículos/pronombres/preposiciones ultra básicos (`the, a, it, they, is, of, in, to, and`).
   Para TODA palabra con contenido (sustantivos, verbos, adjetivos, adverbios, conectores) incluí:
   - `translation`: traducción breve al español en este contexto.
   - `clue`: SIEMPRE completá un tip interpretativo útil (máx. 14 palabras) SIN decir la traducción literal en español (ej. raíz/cognado, rol en el argumento, prefijo/sufijo, sinónimo simple o pista de contexto) para que el usuario intente deducirla antes de revelar.
"""


COMPREHENSION_SYSTEM_PROMPT = """Sos un tutor breve y alentador de inglés.
El estudiante leyó un texto en inglés e intentó explicar en español qué entendió.
Evaluá su comprensión en MÁXIMO 2 líneas cortas (sin traducir todo el texto):
- Línea 1 (`✓`): qué entendió bien de la idea central.
- Línea 2 (`💡`): si algún detalle gramatical (tiempo verbal, condicional, negación, sujeto) le cambió el sentido, marcáselo de forma clara y amable; si lo captó perfecto, felicitá y destacá un matiz clave del texto.
"""


DEFAULT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
]


def _get_api_key_and_models() -> tuple[str, list[str]]:
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    preferred_model = os.getenv("GEMINI_MODEL", "").strip()
    models = ([preferred_model] if preferred_model else []) + [
        m for m in DEFAULT_MODELS if m != preferred_model
    ]
    return api_key, models


def analyze_text_with_gemini(text: str, user_level: str = "B1") -> TutorAnalysis:
    """Envía el texto extraído por OCR a la API gratuita de Google Gemini."""
    api_key, models_to_try = _get_api_key_and_models()

    if not api_key or api_key == "pega_tu_api_key_aca":
        return TutorAnalysis(
            error_message=(
                "Modo offline (sin API Key). Configurá GEMINI_API_KEY en .env "
                "(gratis en aistudio.google.com/apikey) para activar el análisis gramatical con Gemini."
            )
        )

    if not text.strip():
        return TutorAnalysis(error_message="No se detectó texto en el recorte seleccionado.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = (
        f"Nivel aproximado del estudiante: {user_level}.\n"
        f"Texto capturado en inglés:\n\"\"\"\n{text}\n\"\"\""
    )

    last_error = ""
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=GeminiTutorPayload,
                    temperature=0.2,
                ),
            )
            payload: Optional[GeminiTutorPayload] = None
            if response.parsed is not None:
                payload = response.parsed
            elif response.text:
                payload = GeminiTutorPayload.model_validate_json(response.text)

            if payload is not None:
                return TutorAnalysis(
                    grammar_points=payload.grammar_points,
                    chunks=payload.chunks,
                    words=payload.words,
                    error_message="",
                )
        except Exception as exc:  # noqa: BLE001
            last_error = f"{model_name}: {exc}"
            continue

    return TutorAnalysis(
        error_message=f"No se pudo conectar con Gemini API ({last_error[:160]})."
    )


def check_user_comprehension(original_text: str, user_summary: str) -> str:
    """Evalúa brevemente qué entendió el usuario para reforzar Retrieval Practice."""
    if not user_summary.strip():
        return "Escribí primero en 1 frase qué entendiste del texto."

    api_key, models_to_try = _get_api_key_and_models()
    if not api_key or api_key == "pega_tu_api_key_aca":
        return "Configurá GEMINI_API_KEY en .env para validar tu resumen."

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = (
        f"Texto original en inglés:\n\"\"\"\n{original_text}\n\"\"\"\n\n"
        f"Lo que entendió el estudiante (en español):\n\"\"\"\n{user_summary}\n\"\"\""
    )

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=COMPREHENSION_SYSTEM_PROMPT,
                    temperature=0.25,
                    max_output_tokens=180,
                ),
            )
            if response.text:
                return response.text.strip()
        except Exception:  # noqa: BLE001
            continue

    return "No se pudo verificar en este momento (error de conexión con Gemini)."
