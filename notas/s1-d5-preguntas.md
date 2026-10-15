# S1 · Día 5 — Primeras 20 preguntas y cierre de la semana

## `eval/questions.yaml`

20 casos: 8 factuales (F01–F08), 8 situaciones "¿es multa?" (S01–S08, una de ellas debe pedir aclaración) y 4 trampas (T01 ordenanza, T02 posible delito, T03 premisa falsa, T04 Navarra).

El esquema está documentado en la cabecera del YAML. `tests/test_questions.py` comprueba:

- estructura de cada caso (tipo coherente con el id, comportamiento válido, campos obligatorios por tipo);
- que toda respuesta esperada lleva al menos una cita (salvo rechazo o aclaración);
- **que el gold cuadra con los datos**: cada `id_bloque` citado existe en `articulos` y cada sanción coincide exactamente con la fila ARCI (gravedad, importe, pronto pago, puntos). S06 (velocidad sin código ARCI) se ha comprobado contra `velocidades`.

Hallazgos al construirlo:

- El significado de la luz roja ya no está en el art. 143 del RGC sino en su **Anexo I, apdo. 4** (RD 465/2025). S04 cita ambos.
- El **Anexo II de la LSV** (tabla de puntos) no se estaba ingiriendo: las celdas tienen texto directo sin `<p>`. Corregido en `boe.py` (día 5) y reingerido.
- T04 (Navarra) lleva `revisar: true`: hay que confirmar qué autoridad tramita y si hay especialidades forales antes de usarlo como métrica.

## Criterios de "hecho" de S1

| Criterio | Resultado |
|---|---|
| Artículos con metadatos | ✅ LSV y RGC completos (texto, aprobatoria y anexos) con url, fecha de versión y contexto |
| ARCI > 95 % correcta en muestra de 50 | ✅ 50/50 (revisión manual) |
| 100 % de preceptos ARCI cruzados | ✅ 552/552 artículos; 541/552 apartados, 11 excepciones explicadas |
| 20 preguntas con gold | ✅ 20, validadas contra los datos |

## Pendiente para S2

- Completar el test hasta 150 (añadir las 11 filas ARCI desactualizadas como casos de aviso).
- Índice BM25 + embeddings + reranker sobre `fragmentos` (655).
- CI en GitHub Actions (los tests del BOE ya no necesitan red; los de ARCI y del gold necesitan `data/`).
