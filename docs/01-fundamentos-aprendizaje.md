# 01 — Fundamentos de aprendizaje de idiomas aplicados al diseño

Antes de escribir código, investigamos qué dice la ciencia de la **Adquisición de Segundas Lenguas (SLA)** sobre cómo el cerebro aprende realmente a leer otro idioma, para traducir cada principio directamente a una decisión de diseño del software.

---

## 1. Input Comprensible e Hipótesis $i+1$ (Stephen Krashen)
- **Qué dice la teoría:** Adquirimos un idioma cuando entendemos mensajes que están apenas un escalón por encima de nuestro nivel actual ($i+1$). El punto dulce en lectura (*Extensive Reading*) es entender entre el **95% y 98%** del texto por cuenta propia y destrabar solo ese 2%–5% desconocido.
- **Por qué fallan los traductores clásicos:** Si traducís el párrafo entero, bajás la exigencia a $0$ (leés en español). El cerebro no hace ningún esfuerzo de decodificación y no consolida vocabulario ni estructura.
- **Cómo lo aplicamos en la app:**
  - **Prohibida la traducción completa por defecto.**
  - El usuario **elige activamente qué palabra tocar** cuando se traba, manteniendo el cerebro trabajando en inglés el 95% del tiempo.

---

## 2. Enfoque Léxico y "Chunks" (Michael Lewis)
- **Qué dice la teoría:** Los nativos no arman frases pegando palabras sueltas con reglas gramaticales; almacenan y recuperan **bloques prefabricados (*lexical chunks*)**: colocaciones, *phrasal verbs*, conectores y modismos ("frases de manual").
  - Ejemplos: *"as a matter of fact"*, *"end up doing"*, *"make sense of"*, *"had I known"*, *"take it for granted"*.
- **El problema al traducir palabra por palabra:** Si tocás *"take"*, *"for"* y *"granted"* por separado, no vas a entender que juntas significan *"dar por sentado"*.
- **Cómo lo aplicamos en la app:**
  - Además del clic por palabra, el panel de **Tips de lectura** detecta automáticamente *chunks*, *phrasal verbs* y expresiones idiomáticas de la captura y las explica como **una sola unidad de significado**.
  - Al tocar una palabra que forma parte de un *chunk*, la app idealmente resalta el bloque completo.

---

## 3. Hipótesis de la Atención / *Noticing Hypothesis* (Richard Schmidt)
- **Qué dice la teoría:** Leer pasivamente no alcanza para incorporar estructuras gramaticales complejas; el cerebro necesita un momento breve de **atención consciente (*noticing*)** sobre la diferencia entre cómo se arma una idea en inglés y cómo la esperarías en español.
- **Cómo lo aplicamos en la app:**
  - **Desenfoque del fondo (Blur):** Reduce estímulos visuales distractores y crea un micro-entorno de foco para *notar* la estructura.
  - **Tips gramaticales ultracortos (1–2 líneas):** Señalan exactamente el "truco" de lectura de la frase (ej. *"Ojo: 'would' acá no es condicional, marca hábito en el pasado = 'solía'"*, o *"Voz pasiva: el sujeto recibe la acción"*).

---

## 4. Polisemia y Traducción Contextual
- **Qué dice la teoría:** En inglés, las palabras más frecuentes tienen decenas de significados según el contexto (*run*, *get*, *set*, *turn*, *point*, *figure*). Un diccionario estático te muestra 15 acepciones y te corta la lectura.
- **Cómo lo aplicamos en la app:**
  - Cuando el usuario toca una palabra, no se busca aislada: el modelo recibe la **oración completa** (extraída por OCR) y devuelve el significado **exacto en ese contexto** + su forma base (*lemma*, ej. *went → go*) si está conjugada.

---

## 5. Resumen: De la teoría a la UX

| Principio pedagógico | Decisión de producto en English Lens |
| :--- | :--- |
| **Input comprensible ($i+1$)** | No traducir todo; traducción *on-demand* al tocar cada palabra. |
| **Enfoque léxico (*Chunks*)** | Detectar y resaltar *phrasal verbs*, colocaciones y "frases de manual" como bloques. |
| **Noticing Hypothesis** | Fondo desenfocado + 1 a 3 tips breves de cómo leer la estructura de la frase. |
| **Aprendizaje en contexto** | Traducción adaptada a la oración exacta, no definición genérica de diccionario. |
| **Baja fricción cognitiva** | Hotkey instantáneo (`F11` o similar) y cierre inmediato con `Esc`. |
