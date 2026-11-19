# Bitácora de Desarrollo — English Lens

Registro paso a paso de decisiones, experimentos, problemas encontrados y soluciones durante la construcción del proyecto.

---

## 2026-11-19 — Inicio del proyecto (Fase 0)

### Qué definimos hoy
- **Objetivo personal:** Crear una herramienta de escritorio para Windows que permita activar una captura rápida, desenfocar el fondo, tocar cualquier palabra para ver su traducción contextual y mostrar tips de lectura ("frases de manual" / estructuras) sin traducir todo el texto.
- **Restricción clave:** Costo **$0** — OCR 100% local + API gratuita de Google (Gemini via Google AI Studio).
- **Entorno detectado en la PC:**
  - Windows 11 (Build 26100)
  - Python 3.14 (`py.exe`)
  - Git instalado

### Decisiones técnicas clave
1. **OCR nativo de Windows (`Windows.Media.Ocr`):** Elegido porque ya viene en Windows 11, es rápido, no pesa nada y devuelve el `BoundingRect` exacto de cada palabra (indispensable para hacer clic palabra por palabra sobre la captura).
2. **1 sola llamada a Gemini por captura:** En vez de llamar a la API en cada clic, pedimos en una sola llamada de texto (JSON estructurado) el mapa de palabras en contexto + *chunks* + tips de gramática. Resultado: clic instantáneo (0 ms) y mínimo consumo de cuota gratuita.
3. **Base pedagógica documentada:** Aplicamos Input Comprensible ($i+1$), Enfoque Léxico (*chunks*), Hipótesis de la Atención (*Noticing*) y traducción contextual.
4. **Repositorio público en GitHub:** Inicializado desde el día 0 (`thomiirique/english-lens`) con `.gitignore` para proteger `.env` y el entorno virtual.

### Próximo paso
- Confirmar el atajo de teclado preferido y la API key gratuita de Google AI Studio.
- Arrancar **Fase 1**: entorno virtual + prueba de OCR local de Windows + overlay fullscreen con fondo desenfocado.

---

## 2026-11-19 — MVP Completo (Fases 1, 2 y 3)

### Qué construimos
- **`src/hotkey.py`:** Registro nativo en Windows (`RegisterHotKey`) para **`Alt + F11`** integrado al event loop de Qt (`QAbstractNativeEventFilter`), sin hooks invasivos ni dependencias externas.
- **`src/capture.py`:** Captura del monitor activo con `mss` + desenfoque rápido (*downscale → GaussianBlur → upscale* + oscurecimiento sutil) para destacar el recorte nítido.
- **`src/ocr_windows.py`:** Wrapper del motor nativo `Windows.Media.Ocr` via PowerShell/WinRT. Devuelve texto y `BoundingRect` por palabra, con escalado 2x automático para fuentes chicas.
  - *Hallazgo en pruebas:* Esta PC tenía instalados los paquetes de OCR `es-ES` y `es-MX` (sin `en-US`). El wrapper prioriza `en-*` si está instalado y hace fallback automático al primer idioma latino disponible (`es-ES`), que igualmente reconoce texto en inglés con alta precisión.
- **`src/ai_tutor.py`:** Cliente `google-genai` con salida estructurada Pydantic (`TutorAnalysis`) que devuelve en **1 sola llamada**: mapa de palabras en contexto (`words`), frases de manual (`chunks`) y 1–3 tips de estructura (`reading_tips`). Incluye modo degradado si todavía no se configuró `GEMINI_API_KEY`.
- **`src/overlay_ui.py`:** Overlay fullscreen sin bordes respetando DPI (`devicePixelRatio`), recorte nítido sobre fondo desenfocado, hitboxes interactivas sobre cada palabra, tooltip flotante contextual y panel de tips.
- **`src/main.py` y `run.bat`:** Ejecución discreta en la bandeja del sistema (*system tray*).

### Ajuste rápido (Atajo global → `F10`)
- Cambiamos el atajo global de `Alt + F11` a **`F10`** (una sola tecla) y asociamos `RegisterHotKey` a un `HWND` oculto propio de Qt (`QWidget.winId()`), verificado con prueba sintética de `WM_HOTKEY`.

### Ajustes de UX y API (Prueba real con Gemini)
- **Desenfoque al soltar el mouse:** Mientras arrastrás el recuadro la pantalla ahora se ve nítida (con un velo sutil) para seleccionar con precisión; recién al soltar el mouse se desenfoca todo el fondo dejando en foco solo el recorte.
- **Modelos Gemini gratuitos actualizados:** `gemini-2.5-flash` y `gemini-2.0-flash` devolvían `404` para cuentas nuevas. Actualizamos a `gemini-3.5-flash-lite` (principal, ultra rápido) con fallback a `gemini-3.8-flash` y `gemini-3.1-flash-lite`.
- **Carga de `.env` robusta:** Se carga explícitamente desde la raíz del proyecto con `override=True`.

### Mejoras tras la primera prueba real en pantalla
- **Atajos globales `F9` + `Ctrl + Alt + E`:** `F10` en Windows suele ser interceptado como tecla de menú del sistema (`WM_SYSKEYDOWN`). Reemplazado por **`F9`** (tecla única sin conflicto) + **`Ctrl + Alt + E`** como respaldo simultáneo.
- **Diccionario local liviano (`src/common_words.py`, ~20 KB):** Cubre ~400+ palabras base más frecuentes (+ plurales y conjugaciones regulares `-s/-es/-ed/-ing`) en **0 ms y 0 tokens**. Así Gemini no gasta cuota traduciendo palabras básicas como `they`, `can`, `at`, `of`.
- **Énfasis fuerte en gramática:** Nuevo bloque principal **"📐 Cómo leer la gramática"** (`GrammarPoint`: patrón exacto + regla + cómo decodificarlo en español), arriba de los *chunks*.
- **Fix del tooltip falso de API Key:** Separamos el esquema JSON de Gemini (`GeminiTutorPayload`) del campo interno `error_message` para que nunca vuelva a mostrar `"configurá GEMINI_API_KEY"` cuando la API respondió bien.

### Investigación pedagógica ampliada y estimación de cuota
- **Consumo medido:** ~970 tokens por captura (1 request/captura), totalmente viable en el tier gratuito diario de Google AI Studio.
- **Documento `docs/03-investigacion-aprendizaje-e-ideas.md`:** Investigamos *Involvement Load Hypothesis*, *Desirable Difficulties / Retrieval Practice*, *Phonological Loop (TTS bimodal)*, *Conciencia Morfológica / Falsos Amigos* y *Sentence Mining*, definiendo 6 features concretas para las próximas iteraciones.
