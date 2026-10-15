# S1 · Día 3 — Ingesta del BOE

`src/trafico_agent/ingest/boe.py` → `data/trafico.db` (tablas `articulos`, `versiones`, `velocidades`). Solo stdlib (`urllib`, `xml.etree`). Unas 500 peticiones, ~2 min por norma.

Se ejecuta en local: el entorno de Claude no llega a www.boe.es. Los tests usan `tests/fixtures/boe/` (sin red).

## Resultado (ejecución del 15-10-2026)

| Norma | Parte | Artículos | Disposiciones | Anexos |
|---|---|---|---|---|
| LSV (`BOE-A-2015-11722`) | texto | 117 | 26 | 9 |
| LSV | aprobatoria (RDL 6/2015) | 1 | 4 | — |
| CIR (`BOE-A-2003-23514`) | texto | 181 | 8 | — |
| CIR | aprobatoria (RD 1428/2003) | 1 | 6 | — |
| CIR | ANEXO I (6 apartados numerados) / II (36 artículos propios) / III / IV | 36 | — | 4 + 6 |

- Versión consolidada de ambas: **26-06-2026**.
- `velocidades`: 60 tramos del Anexo IV de la LSV (12 límites × 5 tramos).
- Todos los artículos del texto tienen contexto (TÍTULO > CAPÍTULO > Sección > Subsección).

## Decisiones

- **Versión vigente** = la de `fecha_vigencia` más reciente ≤ hoy. Las notas editoriales (`<blockquote>`: "Téngase en cuenta…", "Se modifica…") se eliminan del texto.
- **`parte`**: `aprobatoria` hasta el primer TÍTULO; luego `texto`; y `ANEXO X` desde cada anexo. Necesario porque el RGC tiene articulado propio en el Anexo II (art. 1–35 de pruebas deportivas) y ambas normas repiten nombres de disposiciones.
- **Contexto** por pila de encabezados (un encabezado sustituye a los de su nivel o inferior). El RD 465/2025 reestructuró el Título IV del RGC y dejó encabezados sin padre o vacíos; los vacíos se ignoran.
- **Clave única** = `(id_norma, id_bloque)`. `articulo` no es único (ver abajo).

## Incidencias para el día 4

1. **CIR art. 151–158 aparecen dos veces dentro del texto**: los de 2003 (señales: "Señales de prioridad"…, bloques `a151`…`a158`) y los de un nuevo **TÍTULO VI "Normas de circulación específicas en zonas urbanas"** (bloques `a1-4`…`a1-11`, vigentes desde 2026). Es así en el índice del BOE. El cruce con la ARCI debe decidir a cuál apunta cada fila (por texto del hecho) o dejarlo como excepción documentada.
2. **La ARCI es del 12-11-2025** y el RGC tiene artículos modificados después (p. ej. art. 18, 31, 48, 118–125 con fecha 26-06-2026). Puede haber filas ARCI que citen redacciones anteriores. Revisarlo al cruzar.
3. El encabezado de CIR art. 150 está bajo "TÍTULO V. Señales en los vehículos > Subsección 2.ª" por cómo quedó la reestructuración de 2025 en el BOE; es fiel a la fuente.
