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
