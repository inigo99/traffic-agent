# S1 · Día 4 — Cruce ARCI ↔ BOE y troceado

`src/trafico_agent/ingest/postproceso.py` → tablas `sancion_articulo` y `fragmentos`. Sin red; se ejecuta después de `arci` y `boe`.

## Cruce (552 filas ARCI)

Cada fila se busca en `articulos` (parte `texto`, tipo `articulo`) por norma + número, y su precepto LSV equivalente.

| Estado | Filas | Qué significa |
|---|---|---|
| ok | 484 | Artículo encontrado y su apartado (y letra) existe en el texto vigente |
| sin_apartado | 38 | La ARCI cita el artículo sin apartado |
| apartado_implicito | 19 | La ARCI cita el apdo. 1 de un artículo que hoy no está numerado (p. ej. CIR 2, CIR 20) |
| apartado_no_encontrado | 7 | El apartado no existe en la versión vigente |
| letra_no_encontrada | 4 | El apartado existe pero no la letra |

- **Artículo encontrado: 552/552 (100 %)**, sin ambigüedades. Ninguna fila ARCI cita los CIR 151–158 duplicados, así que esa incidencia no afecta al cruce (sí a la búsqueda: la clave es `id_bloque`).
- **Precepto LSV equivalente encontrado: 552/552.**
- **Apartado verificado: 541/552 (98 %).** Criterio de S1 cumplido con lista de excepciones.

### Excepciones explicadas (11)

| Filas | Causa |
|---|---|
| CIR 012 4 5A; CIR 121 4 5B, 121 4 5C, 121 5 5B; CIR 122 6 5A, 122 7 5A; CIR 125 3 5A | **ARCI desactualizada**: los art. 12, 121, 122 y 125 del RGC tienen redacción vigente desde el **01-10-2026** (posterior a la ARCI del 12-11-2025) y ya no tienen esos apartados. Afecta a peatones, patines y remolques de ciclomotor |
| CIR 094 1-L 5U, 094 1-M 5V | El art. 94.1 vigente llega hasta la letra j); la ARCI cita l) y m) |
| LSV 071 3-A 5A, 071 3-A 5B | El art. 71.3 LSV no tiene letras; la ARCI cita "3-A" |

**Qué hará el agente con ellas**: puede dar importe y puntos (vienen de la ARCI), pero debe avisar de que el precepto citado por la DGT no coincide con el texto vigente del BOE. Se añaden como casos al conjunto de test.

## Troceado (`fragmentos`)

- Artículo/anexo/disposición **entero si ≤ 3 000 caracteres** (≈ 90 % de los artículos; mediana 1 116).
- Si es más largo: **un fragmento por apartado numerado**; si un apartado (o un texto sin apartados, como los anexos) sigue siendo largo, se agrupan párrafos hasta 3 000. El título del artículo se repite en cada fragmento.
- Resultado: **634 fragmentos**, media 934 caracteres, 239 con apartado. 6 superan los 3 000 por poco (máx. 3 049, por el título repetido).
- Id del fragmento: `id_norma#id_bloque#n`, con la `url` del artículo para la cita.
