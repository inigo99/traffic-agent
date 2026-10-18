# S3 — Agente "¿es multa?"

## Diseño (`src/trafico_agent/agent.py`, LangGraph)

```
analizar ─┬─ fuera de ámbito ─────────────► fuera
          ├─ faltan datos clave ──────────► aclarar
          └─ buscar ─► sancion ─► redactar
```

El LLM solo interviene en tres sitios: analizar la pregunta, elegir la fila ARCI entre candidatas y redactar. Todo lo demás es determinista:

- **Datos numéricos, vehículo y tema** (velocidad, alcohol, casco) salen de reglas sobre el texto. Con el LLM salían límites inventados, "moto" cuando nadie la nombraba y alcohol en una pregunta sobre el telepeaje.
- **Velocidad**: tramo del Anexo IV de la LSV. **Alcohol**: fila del art. 20 RGC según tasa y tipo de conductor. Ninguno de los dos pasa por el LLM.
- **Candidatas ARCI**: las 8 filas más parecidas por vectores (hechos denunciados, bge-m3) más las de los artículos recuperados, hasta 30. La salida JSON del LLM se limita a esos códigos (enum).
- **Importes y puntos** los pone el código desde SQL; las frases del LLM con cifras se borran.
- Si el texto del LLM no cita, se responde igualmente con la sanción y su artículo del BOE; sin sanción ni cita, no se responde.

## Evaluación (`eval/run_agent.py --tipo situacion`, 60 situaciones, Ollama en local)

| Modelo | Comportamiento | Sanción exacta | Código ARCI | Gold entre candidatas | Cita | s/pregunta |
|---|---|---|---|---|---|---|
| **qwen2.5:7b** | 58/60 (97 %) | 43/56 (77 %) | 28/54 | 43/54 | 41/56 (73 %) | 6,1 |
| **qwen2.5:3b** | 56/60 (93 %) | 37/56 (66 %) | 16/54 | 36/54 | 39/56 (70 %) | 3,4 |
| qwen2.5:1.5b | 54/60 (90 %) | 35/56 (62 %) | 14/54 | 43/54 | 27/56 (48 %) | 3,2 |
| Claude Haiku | pendiente (sin clave de API) | | | | | |

"Sanción exacta" compara gravedad, importe, pronto pago y puntos. "Código" es más estricto: la ARCI tiene filas casi idénticas con códigos distintos y la misma cuantía.

### Cómo se llegó ahí (qwen2.5:7b, sanción exacta)

| Cambio | Sanción | Candidatas |
|---|---|---|
| Primera evaluación completa | 41/56 | 30/54 |
| Bug: el tope de 12 candidatas dejaba fuera **todas** las filas de los artículos | 42/56 | 41/54 |
| Tema y vehículo por reglas; `\bpositivo` (casaba con "dis**positivo**"); tope de longitud en el JSON (qwen se embuclaba) | 43/56 | 43/54 |

Para los modelos pequeños, lo que más pesó: limitar la elección a los códigos candidatos (enum) y no tirar la sanción cuando el texto no cita. qwen2.5:1.5b pasó de 5/56 a 35/56 y el 3b de 28/56 a 37/56, sin cambios en el 7b.

`eval/run_candidatos.py` mide la cobertura de candidatas sin LLM: 8 por vectores + artículos de top 5 → 47/54 con ~25 filas; ampliar a 12 + top 10 solo da 48/54 con ~40.

## Decisión

- **Modelo de la demo: qwen2.5:3b.** Cita casi como el 7b (70 % frente a 73 %) con la mitad de tamaño; el 1.5b cita mucho peor.
- Fallos que quedan, sobre todo de elección del LLM: móvil en la mano (S02), ráfagas para avisar de un control (S35), bici sin chaleco (S40), cambio de sentido en curva (S52). En el 3b además entran menos candidatas (36/54): su reformulación de la consulta recupera peor.

## Pendiente

- Evaluar Claude Haiku cuando haya clave de API.
- Factuales y trampas con el agente (`--tipo factual`, `--tipo trampa`).
- 3b: probar a buscar con la pregunta original en vez de la reformulada.
