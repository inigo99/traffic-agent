# S1 · Día 1 — Prueba de extracción de la guía ARCI

PDF: guía ARCI vigente desde 01-07-2025 (edición del 12-11-2025), 282 páginas.

## Decisión

**pdfplumber** (`page.extract_tables()` con la configuración por defecto).

| Herramienta | Resultado | Tiempo (3 págs.) |
|---|---|---|
| pdfplumber | 12 columnas limpias en las 282 páginas; 774 filas | 0,6 s |
| camelot (lattice) | Mismo resultado celda a celda | 4,0 s, más dependencias (ghostscript/opencv) |
| markitdown | Texto plano; mezcla las columnas. No sirve para la tabla | — |

La tabla tiene líneas dibujadas, así que no hace falta el modo *stream* ni ajustes finos.

## Estructura de cada fila

`NORMA | ART | APT | OPC | PTOS | CALIF | TEXTO HECHO | MULTA | RESPONS | COMENTARIO | MATERIA | ABREVIADO`

- Las celdas NORMA, ART y APT tienen **dos líneas**: precepto del reglamento (p. ej. `CIR 020.1`) y precepto de la LSV que lo tipifica (`LSV 014.1`).
- MULTA tiene dos líneas: importe y pronto pago (`500.0\n250.0`).
- CALIF: gravedad más, si es grave o muy grave, el apartado de la LSV (`Muy grave\n077.c\n-)` → art. 77.c).
- Código único de fila: norma + artículo + apartado + opción (`CIR 020 1 5E`).
- Cabeceras de página repetidas (`NORMA…`) → se descartan. No hay filas partidas entre páginas.

## Normas que aparecen

| NORMA | Filas | ¿En corpus v1? |
|---|---|---|
| CIR (RGC) | 526 | Sí |
| LSV | 26 | Sí |
| VEH (Reglamento de Vehículos) | 100 | No (v2) |
| EPC | 60 | No |
| CRC | 35 | No |
| CON (Reglamento de Conductores) | 22 | No (v2) |
| SOA (seguro obligatorio) | 5 | No |

**552 filas** (CIR + LSV) entran en v1. **Decisión: se cargan solo esas 552**; el resto no entra en SQLite.

## Problemas encontrados

1. **El texto del hecho está recortado en el propio PDF**: la celda tiene alto fijo y el texto que no cabe no existe (comprobado en la imagen de la página 3). No se puede recuperar. Impacto bajo: la cita se apoya en el artículo del BOE, no en este texto.
2. **Multas especiales (46 filas)**: `SIN REDUC.` (sin pronto pago), con o sin importe (`3000.0 SIN REDUC.` ×29, `80.0 SIN REDUC.` ×8, solo `SIN REDUC.` ×5…). Se modela como `importe_eur` (nullable) + `pronto_pago_eur` (nullable) + `sin_reduccion` (bool).
3. **Velocidad (10 filas)**: PTOS = `0, 2, 4, 6` e importe genérico (100 €) o variable. La ARCI **no** trae los tramos km/h → importe y puntos reales salen del **Anexo IV de la LSV** (BOE). Decisión: tabla aparte `velocidades` construida desde el BOE el día 3.
4. Opción `5Ñ` (2 filas): válida; el regex de OPC debe admitir Ñ.
5. Filas `ARTÍCULO 0XX` fuera de la tabla: son títulos de sección y se ignoran.

## Día 2 — resultado

- `src/trafico_agent/ingest/arci.py` → `data/trafico.db`, tabla `sanciones`, **552 filas** (331 graves, 162 leves, 59 muy graves). Unos 30 s para las 282 páginas.
- **Corrección de lectura**: la 2.ª línea de CALIF (`076.h`, `077.c`, `076.z` + `3)`) es el **artículo de la LSV que califica** la infracción (art. 76 graves, 77 muy graves), no una letra del precepto LSV de la columna ART. Se guarda como `tipificacion` (`'76.h'`, `'77.c'`, `'76.z.3'`); NULL en leves.
- Velocidad: la ARCI sí trae importe y puntos por **opción** (5D…5J: 600/500/400/300 €, 6/4/2 puntos), pero el tramo km/h de cada opción no aparece ("CIRCULAR A ... KM/H"). El cruce opción ↔ tramo sale del Anexo IV de la LSV (día 3).
- Tests (`tests/test_arci.py`, 9 en verde): 552 filas y solo CIR/LSV; filas críticas alcohol `CIR 020 1 5E`, móvil `LSV 076 - 5A` (6 puntos), cinturón `CIR 117 1 5E`, ZBE `LSV 076 - 5F` (sin reducción), una leve; pronto pago = mitad; sin reducción → sin pronto pago.
- **Muestra de 50 filas** (semilla 1): 0 diferencias frente a una segunda extracción independiente con camelot en 8 campos, y 4 filas revisadas sobre la imagen del PDF (págs. 45 y 147). Revisión a mano de Íñigo sobre `arci-muestra-50.csv`: **50/50 correctas (100 %)**. Criterio de S1 (> 95 %) cumplido.
