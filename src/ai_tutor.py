"""Tutor lingüístico basado en Google Gemini API (tier gratuito) + diccionario local liviano.

Aplica los principios documentados en docs/01-fundamentos-aprendizaje.md:
- NO traduce el texto completo.
- Las palabras básicas/frecuentes se resuelven en 0 ms desde src/common_words.py (0 tokens).
- Gemini se enfoca en:
  1) Entender la GRAMÁTICA y cómo leer la estructura de las oraciones.
  2) Detectar frases de manual / chunks / phrasal verbs.
  3) Traducir SOLO palabras difíciles, técnicas o con sentido especial en contexto.
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
    note: str = Field(default="", description="Micro-nota opcional de máx. 10 palabras si hay matiz o falso amigo.")


class GrammarPoint(BaseModel):
    pattern: str = Field(description="Fragmento o estructura exacta del texto (ej. 'If AI were to evade', 'much more powerful greenhouse gases').")
    concept: str = Field(description="Nombre claro de la regla gramatical (ej. '2do condicional formal (were to)', 'Voz pasiva con modal', 'Cadena de modificadores').")
    how_to_read: str = Field(description="Explicación práctica en español de CÓMO leer y decodificar esa estructura sin traducir todo el párrafo (1 a 2 líneas).")


class LexicalChunk(BaseModel):
    phrase: str = Field(description="Expresión, phrasal verb, colocación o frase de manual en inglés.")
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
        description="SOLO palabras de nivel intermedio/avanzado, técnicas o con significado especial en este contexto. Omitir palabras básicas (the, they, is, can, and, of, for, etc.).",
    )


class TutorAnalysis(BaseModel):
    """Modelo completo consumido por la interfaz."""

    grammar_points: list[GrammarPoint] = Field(default_factory=list)
    chunks: list[LexicalChunk] = Field(default_factory=list)
    words: list[WordTranslation] = Field(default_factory=list)
    error_message: str = Field(default="")

    def lookup_word(self, raw_word: str) -> Optional[WordTranslation]:
        """Busca primero en la traducción contextual de Gemini y luego en el diccionario local."""
        target = _normalize_token(raw_word)
        if not target:
            return None

        # 1. Prioridad: traducción contextual de Gemini (palabras difíciles o polisémicas)
        for entry in self.words:
            if _normalize_token(entry.word) == target:
                return entry

        # 2. Fallback instantáneo: diccionario local de palabras frecuentes (0 ms, 0 tokens)
        local = lookup_common_word(raw_word)
        if local is not None:
            base, translation, pos = local
            return WordTranslation(
                word=raw_word,
                lemma=base,
                translation=translation,
                pos=f"{pos} · local",
                note="",
            )

        return None

    def find_chunks_for_word(self, raw_word: str) -> list[LexicalChunk]:
        """Devuelve chunks/frases de manual que contengan esta palabra."""
        target = _normalize_token(raw_word)
        if not target:
            return []
        matches = []
        for chunk in self.chunks:
            tokens = [_normalize_token(t) for t in chunk.phrase.split()]
            if target in tokens:
                matches.append(chunk)
        return matches


def _normalize_token(token: str) -> str:
    return re.sub(r"^[^a-zA-Z0-9']+|[^a-zA-Z0-9']+$", "", token).lower()


SYSTEM_PROMPT = """Sos un profesor experto en enseñanza de lectura en inglés para hispanohablantes (Enfoque Léxico + Noticing Hypothesis + Input Comprensible i+1).

El usuario capturó un fragmento en inglés y quiere ENTENDER CÓMO FUNCIONA LA GRAMÁTICA para poder leerlo solo. NO quiere que le traduzcas el párrafo entero.

PRIORIDADES Y REGLAS ESTRICTAS:
1. NUNCA traduzcas el texto completo ni las oraciones enteras.
2. PRIORIDAD #1 — `grammar_points` (2 a 4 puntos):
   Explicá de forma clara, didáctica y práctica las estructuras gramaticales que hacen que la frase cueste leer:
   - Tiempos verbales, condicionales, modales (would/could/were to/had I...), voz pasiva ("can be produced").
   - Orden de palabras en inglés distinto al español (ej: cadenas de adjetivos/sustantivos que se leen de atrás para adelante, como "powerful greenhouse gases").
   - Conectores, aclaraciones y cláusulas subordinadas ("that is", "to the point that", "there is no ... left").
   Usá español claro y directo: decile al usuario *cómo decodificar* esa estructura al leerla.
3. PRIORIDAD #2 — `chunks` (0 a 4 bloques):
   Detectá "frases de manual", colocaciones fijas, phrasal verbs o modismos que se leen como una sola unidad.
4. PRIORIDAD #3 — `words` (SOLO vocabulario no básico):
   Ya tenemos un diccionario local offline para palabras comunes (pronombres, artículos, preposiciones, verbos básicos como be/have/can/do/make/produce/exist/year/point).
   NO gastes espacio en esas palabras básicas. Incluí en `words` ÚNICAMENTE palabras intermedias/avanzadas, técnicas, poco frecuentes o usadas con un sentido especial en este contexto (ej: evade, orchestrate, megatons, sufficient, niche, persist, atmosphere, greenhouse, scales, chemicals).
"""


DEFAULT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
]


def analyze_text_with_gemini(text: str, user_level: str = "B1") -> TutorAnalysis:
    """Envía el texto extraído por OCR a la API gratuita de Google Gemini."""
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

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

    preferred_model = os.getenv("GEMINI_MODEL", "").strip()
    models_to_try = ([preferred_model] if preferred_model else []) + [
        m for m in DEFAULT_MODELS if m != preferred_model
    ]

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
