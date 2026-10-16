# S2 — Recuperación y conjunto de test

## Conjunto de test (`eval/questions.yaml`)

150 casos: 60 factuales, 60 situaciones (44 normales, 5 de ARCI desfasada, 3 que piden aclaración, más las 8 de S1) y 30 trampas (ordenanza, posible delito, premisa falsa, fuera de ámbito y competencia). 135 tienen citas y entran en la métrica de recuperación.

- Una cita puede ser una **lista de artículos equivalentes** (p. ej. CIR 117 o LSV 47 para el cinturón): el grupo se cumple si aparece cualquiera.
- `tests/test_questions.py` comprueba el esquema, el reparto 60/60/30, que las claves de cada factual están en el texto citado y que cada sanción coincide con su fila ARCI.

**Revisión manual de 30 casos (16-10-2026): 28/30 correctos.** Corregidos los dos fallos:

| Caso | Problema | Corrección |
|---|---|---|
| F34 | "¿Con cuántos puntos empieza un conductor?" ignoraba a los noveles (8) | La respuesta debe dar 12 y 8 |
| S34 | "Flecha verde a la derecha y giré a la izquierda" se confunde con saltarse el rojo (4 puntos), y la ARCI 143 1-B 5B da 0 | Sustituida por pitar sin motivo en un atasco (CIR 110 2 5A) |

## Recuperación (`src/trafico_agent/index.py`, `eval/run_retrieval.py`)

655 fragmentos. Vectores con `BAAI/bge-m3` (en CPU, ~5 min) y reranker `BAAI/bge-reranker-v2-m3` sobre los 30 candidatos de la híbrida. Sin base de datos vectorial: 655 × 1024 en un `.npy` y un producto de matrices.

| Config | recall@5 | hit@5 | MRR | Tiempo (135 consultas, CPU) |
|---|---|---|---|---|
| BM25 | 0,568 | 0,570 | 0,431 | 0,1 s |
| **Vectores (bge-m3)** | **0,765** | **0,778** | **0,614** | 38 s (incluye cargar el modelo) |
| Híbrida (RRF, pesos 1:1) | 0,732 | 0,741 | 0,563 | 0,2 s |
| Híbrida ponderada (BM25 × 0,5) | 0,762 | 0,770 | 0,591 | 0,2 s |
| Híbrida + reranker (512 tokens) | 0,794 | 0,800 | 0,642 | 4 358 s (~32 s por consulta) |
| Vectores + reranker (512 tokens) | 0,791 | 0,800 | 0,649 | 1 519 s (~11 s por consulta, reaprovechando pares ya puntuados) |

(Medición del 16-10-2026 con las dos correcciones de la revisión.)

Lectura:

- Con 18 preguntas BM25 parecía el mejor; con 135 preguntas parafraseadas se invierte. El test pequeño no servía para decidir.
- La fusión RRF con pesos iguales **empeora** a los vectores: BM25 mete ruido. Bajando su peso a la mitad se recupera casi todo (0,762), pero sigue sin superar a los vectores solos.
- El reranker es el mejor (+0,026–0,029 de recall@5 sobre vectores, da igual sobre qué candidatos actúe), pero en CPU tarda **decenas de segundos por consulta** (~32 s en frío): inviable para la demo en HF Spaces (CPU) y para el agente.

## Decisión

- **Recuperación por defecto: vectores (bge-m3), top 5.** `Indice.buscar(..., modo="vectores")`.
- El reranker se queda como opción (`modo="rerank"`) y fuera de la evaluación por defecto (`eval/run_retrieval.py --rerank` para medirlo). Se reconsidera si se ejecuta con GPU (CUDA) o con un reranker más pequeño.
- Criterio de S2 ("recall@5 medido para las 4 configuraciones"): ✅.
