# English Lens 🔍

Herramienta de escritorio personal para Windows diseñada para **aprender a leer inglés de forma activa** sobre cualquier contenido en pantalla (juegos, PDFs, artículos, cómics, apps), sin caer en la trampa de los traductores automáticos completos.

## 🎯 Objetivo del proyecto
1. Presionar un atajo rápido (ej. `F11` o hotkey configurable).
2. **Desenfocar el fondo** de la pantalla para enfocar la atención en el texto capturado.
3. **Tocar cualquier palabra** directamente para ver su traducción *en ese contexto*.
4. Recibir **tips de lectura y "frases de manual"** (*chunks*, *phrasal verbs*, estructuras gramaticales y modismos) en español, sin spoilear la traducción completa del texto.
5. Mantener costo **$0** usando **OCR local nativo de Windows** + **Google Gemini API (tier gratuito)**.

## 📚 Documentación del proceso
Todo el diseño, la investigación pedagógica y el avance técnico se documentan en la carpeta `docs/`:

1. [01 - Fundamentos de aprendizaje de idiomas](docs/01-fundamentos-aprendizaje.md): Teoría de adquisición de segundas lenguas aplicada al diseño de la app.
2. [02 - Arquitectura y plan de desarrollo](docs/02-arquitectura-y-plan.md): Stack técnico, flujo de datos y fases de implementación.
3. [Bitácora de desarrollo](docs/BITACORA.md): Registro cronológico de decisiones, pruebas y avances.

## 🛠️ Stack elegido
- **Lenguaje:** Python 3.14
- **Interfaz / Overlay con desenfoque:** PySide6 (Qt6) — permite overlays fullscreen sin bordes, efectos de blur, hitboxes por palabra y tooltips fluidos.
- **OCR Local ($0):** Motor nativo de Windows 11 (`Windows.Media.Ocr`), que además devuelve las coordenadas exactas (*bounding boxes*) de cada palabra.
- **IA / Análisis lingüístico ($0):** Google Gemini API (tier gratuito via Google AI Studio, SDK `google-genai`).

## 🚀 Cómo ejecutarlo
1. Creá el entorno virtual e instalá dependencias:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```
2. Copiá `.env.example` a `.env` y pegá tu API key gratuita de [Google AI Studio](https://aistudio.google.com/apikey):
   ```env
   GEMINI_API_KEY=tu_api_key_gratis
   ```
3. Ejecutá `run.bat` (o `.\.venv\Scripts\python.exe src\main.py`).
4. Presioná **`Alt + F11`** en cualquier pantalla, arrastrá sobre el texto en inglés y tocá cada palabra para ver su traducción en contexto + tips de lectura.

## 🗺️ Roadmap
- [x] **Fase 0:** Investigación pedagógica, definición de UX y documentación inicial.
- [x] **Fase 1:** Atajo global (`Alt + F11`) + captura de pantalla + overlay fullscreen con fondo desenfocado.
- [x] **Fase 2:** Integración de OCR local de Windows (`Windows.Media.Ocr`) con detección de coordenadas por palabra.
- [x] **Fase 3:** Interacción palabra por palabra (clic → traducción contextual) + integración con Gemini API gratuita para tips y *chunks*.
- [ ] **Fase 4:** Pulido de UX, configuración de nivel de inglés (A2–C1) y registro opcional de palabras aprendidas.
