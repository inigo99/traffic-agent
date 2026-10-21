"""¿Ha cambiado alguna norma del corpus en el BOE? Compara el índice de la API de legislación
consolidada con `data/versiones.json` (versionado) y lista los bloques modificados.

    python -m trafico_agent.watch            # informe; sale con 3 si hay cambios
    python -m trafico_agent.watch --guardar  # tras reindexar: guarda fechas y anota el CHANGELOG

Solo usa la biblioteca estándar: la tarea semanal de GitHub Actions no instala nada.
"""

import json
import sys
from datetime import date
from pathlib import Path

from trafico_agent.ingest.boe import API, NORMAS, get

RAIZ = Path(__file__).parents[2]
VERSIONES = RAIZ / "data" / "versiones.json"
CHANGELOG = RAIZ / "CHANGELOG.md"
HAY_CAMBIOS = 3  # no 1: un error (BOE caído) también sale con 1 y no debe abrir issue


def indice(id_norma, fetch=get):
    """{id_bloque: fecha_actualizacion} de la versión consolidada actual."""
    datos = json.loads(fetch(API.format(id=id_norma) + "/indice", "application/json"))
    return {b["id"]: b["fecha_actualizacion"] for b in datos["data"][0]["bloque"]}


def cambios(conocidas, actuales):
    """Por norma: bloques nuevos o con fecha posterior a la conocida (y los que desaparecen)."""
    out = {}
    for norma, bloques in actuales.items():
        antes = conocidas.get(norma, {})
        dif = sorted(b for b, f in bloques.items() if f > antes.get(b, ""))
        dif += sorted(f"{b} (eliminado)" for b in antes.keys() - bloques.keys())
        if dif:
            out[norma] = dif
    return out


def informe(dif, actuales):
    lineas = [
        f"- **{n}** ({NORMAS[n]}, última actualización {max(actuales[n].values())}): "
        + ", ".join(b)
        for n, b in dif.items()
    ]
    return "Bloques modificados en el BOE desde la última indexación:\n\n" + "\n".join(lineas)


def main(argv=None, fetch=get):
    argv = sys.argv[1:] if argv is None else argv
    conocidas = json.loads(VERSIONES.read_text(encoding="utf-8")) if VERSIONES.exists() else {}
    actuales = {n: indice(i, fetch) for n, i in NORMAS.items()}
    dif = cambios(conocidas, actuales)
    if "--guardar" in argv:
        VERSIONES.write_text(json.dumps(actuales, indent=1, sort_keys=True), encoding="utf-8")
        if dif and conocidas:
            previo = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "# Cambios\n"
            entrada = f"\n## {date.today().isoformat()}: reindexado\n\n{informe(dif, actuales)}\n"
            CHANGELOG.write_text(previo + entrada, encoding="utf-8")
        print(f"Guardado {VERSIONES.name}")
        return 0
    if not conocidas:  # primera vez: todo es "nuevo"; basta la fecha para saber si reindexar
        for n, bloques in actuales.items():
            print(f"{n}: última actualización {max(bloques.values())} (sin versiones guardadas)")
        return HAY_CAMBIOS
    print(informe(dif, actuales) if dif else "Sin cambios en el BOE.")
    return HAY_CAMBIOS if dif else 0


if __name__ == "__main__":
    sys.exit(main())
