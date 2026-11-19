"""Tutor lingüístico basado en Google Gemini API (tier gratuito via google-genai).

Aplica los principios documentados en docs/01-fundamentos-aprendizaje.md:
- NO traduce el texto completo.
- Devuelve un mapa de traducciones contextuales palabra por palabra (en 1 sola llamada).
- Detecta chunks / phrasal verbs / frases de manual como bloques completos.
- Da 1 a 3 tips ultracortos de lectura y gramática.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class WordTranslation(BaseModel):
    word: str = Field(description="Palabra exacta tal como aparece en el texto en inglés.")
    lemma: str = Field(description="Forma base o infinitivo si difiere (ej. 'went' -> 'go'), si no, igual a word.")
    translation: str = Field(description="Traducción breve al español EXACTAMENTE para este contexto (1 a 4 palabras).")
    pos: str = Field(description="Categoría gramatical corta en español (ej. 'verbo', 'sustantivo', 'phrasal verb', 'conector').")
    note: str = Field(default="", description="Micro-nota opcional de máx. 10 palabras si hay matiz o falso amigo.")


class LexicalChunk(BaseModel):
    phrase: str = Field(description="Expresión, phrasal verb, colocación o frase de manual en inglés.")
    meaning: str = Field(description="Significado natural en español.")
    tip: str = Field(description="Explicación de 1 línea de por qué se lee como bloque y cómo recordarla.")


class TutorAnalysis(BaseModel):
    words: list[WordTranslation] = Field(
        default_factory=list,
        description="Traducción contextual de cada palabra distinta del texto para permitir clic palabra por palabra.",
    )
    chunks: list[LexicalChunk] = Field(
        default_factory=list,
        description="Frases de manual, phrasal verbs, modismos o colocaciones encontradas en el texto (0 a 4).",
    )
    reading_tips: list[str] = Field(
        default_factory=list,
        description="Máximo 3 tips muy breves en español sobre gramática o estructura para leer la frase sin traducirla entera.",
    )
    status_message: str = Field(default="", description="Mensaje interno de estado o error.")

    def lookup_word(self, raw_word: str) -> Optional[WordTranslation]:
        """Busca la traducción contextual normalizando signos de puntuación."""
        target = _normalize_token(raw_word)
        if not target:
            return None
        for entry in self.words:
            if _normalize_token(entry.word) == target:
                return entry
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


SYSTEM_PROMPT = """Sos un tutor experto en enseñanza de inglés para hispanohablantes (enfoque comunicativo, Enfoque Léxico de chunks e Input Comprensible i+1).

El usuario capturó un fragmento de texto en inglés de su pantalla y quiere LEERLO Y ENTENDERLO POR SÍ MISMO, NO recibir una traducción completa.

REGLAS ESTRICTAS:
1. NUNCA traduzcas el texto completo ni las oraciones enteras.
2. En `words`: incluí cada palabra relevante del texto (evitá repetir duplicados exactos) con su traducción breve AL ESPAÑOL en ESE contexto exacto (no definiciones largas de diccionario).
3. En `chunks`: detectá "frases de manual", phrasal verbs, colocaciones, conectores compuestos o modismos (ej: "end up", "as a matter of fact", "take for granted", "had I known"). Explicá en 1 línea cómo leerlos como un solo bloque.
4. En `reading_tips`: dá entre 1 y 3 tips MUY cortos (máximo 18 palabras cada uno) en español claro y directo señalando estructuras gramaticales clave (tiempos verbales, voz pasiva, omisiones, conectores, orden de adjetivos).
5. Si el texto tiene errores menores de OCR, inferí la palabra inglesa correcta por contexto.
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
            status_message=(
                "Modo OCR local activo (sin API Key). "
                "Creá tu archivo .env con GEMINI_API_KEY (gratis en aistudio.google.com/apikey) "
                "para activar las traducciones por palabra y tips de lectura."
            )
        )

    if not text.strip():
        return TutorAnalysis(status_message="No se detectó texto en el recorte seleccionado.")

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
                    response_schema=TutorAnalysis,
                    temperature=0.2,
                ),
            )
            if response.parsed is not None:
                return response.parsed
            if response.text:
                return TutorAnalysis.model_validate_json(response.text)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{model_name}: {exc}"
            continue

    return TutorAnalysis(
        status_message=f"No se pudo conectar con Gemini API ({last_error[:160]})."
    )
