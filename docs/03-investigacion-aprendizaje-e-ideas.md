# 03 — Investigación profunda sobre aprendizaje de idiomas e ideas para English Lens

Este documento amplía `01-fundamentos-aprendizaje.md` con evidencia de **Adquisición de Segundas Lenguas (SLA)** y **Psicología Cognitiva**, traducida directamente en funcionalidades concretas para futuras versiones de **English Lens**.

---

## 1. Hallazgos científicos clave (más allá de leer y traducir)

### A. Hipótesis de la Carga de Participación (*Involvement Load Hypothesis* — Laufer & Hulstijn, 2001)
- **Qué dice la ciencia:** La retención de una palabra nueva depende de tres factores:
  1. **Need** (necesidad real de entenderla en ese momento).
  2. **Search** (esfuerzo activo por averiguar su significado).
  3. **Evaluation** (comparar significados y verificar si encaja en la oración).
- **Por qué importa:** Si una app te da un glosario automático en pantalla sin que hagas nada, elimina el *Search* y la *Evaluation* → entendés en el instante, pero **a los 10 minutos te olvidaste la palabra**.
- **Qué tiene de bueno English Lens hoy:** El simple hecho de tener que elegir y hacer clic en la palabra genera *Need + Search*. Podemos potenciar la *Evaluation* sin romper la fluidez.

---

### B. Dificultades Deseables y Práctica de Recuperación (*Desirable Difficulties & Retrieval Practice* — Robert Bjork)
- **Qué dice la ciencia:** Releer pasivamente genera una **"ilusión de fluidez"**: sentís que entendés porque tenés el texto enfrente, pero el rastro en memoria es muy débil. En cambio, introducir pequeñas fricciones (*desirable difficulties*) —como intentar recordar antes de mirar la respuesta, o completar huecos (*cloze*)— fortalece muchísimo las conexiones neuronales.
- **Repetición espaciada (SRS):** Volver a encontrarte una palabra o estructura gramatical justo cuando estás por olvidarla (1 día → 3 días → 7 días → 21 días) multiplica la retención a largo plazo.

---

### C. Bucle Fonológico y Lectura Bimodal (*Phonological Loop & TTS* — Alan Baddeley)
- **Qué dice la ciencia:** En la memoria de trabajo existe un "bucle fonológico" que retiene sonidos unos segundos para procesarlos. En inglés, **la ortografía no coincide con la pronunciación** (ej. *though, through, tough, thorough, niche*).
- **El cuello de botella:** Si leés una palabra difícil y no sabés cómo suena (o la pronunciás mal en tu cabeza), la memoria de trabajo no puede sostenerla bien y cuesta el doble recordarla.
- **Lectura bimodal (texto + audio):** Ver la palabra mientras escuchás su pronunciación exacta crea una **doble traza en memoria (visual + auditiva)** y libera carga cognitiva para entender la gramática.

---

### D. Conciencia Morfológica y Puente de Cognados / Falsos Amigos
- **Qué dice la ciencia:** Reconocer **morfemas** (prefijos, raíces, sufijos) permite decodificar familias enteras de palabras (ej. saber `evade` + sufijos te destraba `evasion`, `evasive`, `unevadable`).
- **Ventaja del español:** Compartimos miles de raíces latinas/griegas con el inglés (*cognados* como *orchestrate*, *industrial*, *sufficient*), pero también existen **falsos amigos** (*actually ≠ actualmente*, *eventually ≠ eventualmente*, *comprehensive ≠ comprensivo*, *assist ≠ asistir*) que rompen la comprensión si no te avisan.

---

### E. *Sentence Mining* y *Narrow Reading*
- **Qué dice la ciencia:** Memorizar palabras sueltas en listas no funciona bien porque perdés la preposición con la que van, el tiempo verbal y el registro. El ***Sentence Mining*** guarda la palabra **dentro de la oración real** donde la encontraste (exactamente lo que vos ya capturás con English Lens).
- ***Narrow Reading* (Krashen):** Leer varios textos sobre un **mismo tema** hace que las mismas estructuras y vocabulario se repitan de forma natural, acelerando la adquisición sin estudio artificial.

---

## 2. Ideas concretas para integrar en English Lens

Ordenadas de **mayor impacto pedagógico / menor fricción** a funcionalidades más avanzadas:

### 💡 Idea 1 — Resaltado interactivo de gramática sobre el texto (Visual *Noticing*)
- **Base científica:** *Noticing Hypothesis* + carga cognitiva visual.
- **Cómo funcionaría:** Cuando pasás el mouse por arriba de un punto gramatical en el panel (ej. `"If AI were to evade... it would be sufficient"`), **se subrayan o iluminan esas palabras exactas arriba en la imagen capturada** (por ejemplo, sujeto en un color, verbo/estructura en otro).
- **Por qué suma:** En vez de ir y venir con la vista entre el texto y la explicación, ves la "radiografía" de la oración directo encima del texto real.

### 💡 Idea 2 — Audio instantáneo de palabra u oración (TTS local $0)
- **Base científica:** Bucle fonológico + Lectura bimodal (doble traza visual y auditiva).
- **Cómo funcionaría:**
  - Un botón **🔊** en el tooltip de la palabra (o clic derecho sobre cualquier palabra) para escuchar cómo se pronuncia.
  - Un botón **"Escuchar frase"** en el panel para oír el ritmo real del inglés.
  - Usando el motor de voz nativo de Windows (`System.Speech` / WinRT TTS) o `edge-tts`: **0 tokens de API**.

### 💡 Idea 3 — Alertas de "Falsos Amigos" + Descomposición Morfológica
- **Base científica:** Transferencia L1→L2 y Conciencia Morfológica.
- **Cómo funcionaría:**
  - Si aparece un falso amigo (ej. *actually*, *eventually*, *library*, *realize*, *pretend*), el tooltip lo marca en color ámbar: *"⚠️ Falso amigo: significa 'en realidad', NO 'actualmente'"*.
  - En palabras largas/derivadas (ej. *unavoidable*, *orchestrate*), mostrar el despiece: `un- (no) + avoid (evitar) + -able` o familia de palabras.

### 💡 Idea 4 — Modo "Micro-desafío" antes de ver la respuesta (*Desirable Difficulty*)
- **Base científica:** *Involvement Load Hypothesis* (*Evaluation*) + *Retrieval Practice*.
- **Cómo funcionaría (modo opcional toggleable):**
  - Al tocar una palabra nueva, podés ver primero **una pista contextual o su categoría** (*"verbo · sinónimo: dodge / escape"*) y recién con un clic (o barra espaciadora) revelar la traducción en español.
  - Botón opcional **"¿Lo entendí?"**: escribís en 1 frase corta qué quiso decir el párrafo y Gemini te corrige solo si te comiste algún matiz gramatical (*"Bien la idea general, ojo que 'were to' lo hace hipotético, no pasado real"*).

### 💡 Idea 5 — *Sentence Mining* con 1 clic + Repaso Espaciado (SRS / Anki)
- **Base científica:** *Sentence Mining* + *Spaced Repetition* + *Cloze Testing*.
- **Cómo funcionaría:**
  - En el tooltip de cualquier palabra o *chunk*, un botón **⭐ Guardar**: guarda en un archivo local (`data/vocab_journal.json` o SQLite) la palabra, su traducción en contexto, la **oración completa donde la viste** y la nota gramatical.
  - **Mini-repaso de 2 minutos:** Desde el ícono del tray, abrir un modo repaso rápido que te muestra tus propias oraciones capturadas con la palabra oculta (*Cloze*):
    > *"If AI were to `______` international monitoring..."* → tenés que recordar `evade` antes de destaparlo.
  - **Exportar a Anki:** Un botón para exportar tus palabras guardadas a `.csv` listo para importar en Anki.

### 💡 Idea 6 — Vocabulario personal ("Ya me la sé") y Calibración de Nivel ($i+1$)
- **Base científica:** Personalización continua del umbral $i+1$.
- **Cómo funcionaría:**
  - Botón **"✓ Ya me la sé"** en el tooltip: agrega esa palabra a tu diccionario local personal para no volver a gastar tokens ni mostrarte ruido en futuras capturas.
  - Selector de nivel (`A2` / `B1` / `B2` / `C1`) en el menú del tray para ajustar qué estructuras gramaticales explica Gemini y qué palabras omite.

---

## 3. Matriz de priorización sugerida (Fase 4 en adelante)

| Prioridad | Feature | Complejidad técnica | Impacto en aprendizaje | Costo API extra |
| :---: | :--- | :---: | :---: | :---: |
| **1** | **Audio TTS (pronunciar palabra / oración)** | Baja | Muy alto (bucle fonológico) | **$0** (local) |
| **2** | **Resaltado sincronizado de gramática y chunks en la captura** | Media | Muy alto (*noticing* visual) | **$0** |
| **3** | **Alertas de Falsos Amigos + Morfología en el prompt/tooltip** | Muy baja | Alto | **$0** (mismo prompt) |
| **4** | **⭐ Guardar frase (*Sentence Mining*) + Export Anki / Mini-repaso Cloze** | Media | Altísimo (retención largo plazo) | **$0** (local) |
| **5** | **Botón "✓ Ya me la sé" + Selector de nivel (A2–C1)** | Baja | Alto (ajusta $i+1$) | **Ahorra tokens** |
| **6** | **Modo Desafío ("¿Lo entendí?" + pista antes de traducir)** | Media | Alto (*retrieval practice*) | Mínimo / opcional |
