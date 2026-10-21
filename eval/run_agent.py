"""Evalúa el agente completo sobre eval/questions.yaml.

Uso: [TRAFICO_ELECCION=vector] uv run python eval/run_agent.py [--tipo situacion|factual|trampa|todos] [--modelo qwen2.5:7b] [--n 10]

Métricas por pregunta:
  comportamiento  el agente hace lo esperado (responder / aclarar / rechazar / avisar)
  sancion         gravedad, importe, pronto pago y puntos idénticos al gold (situaciones)
  codigo          mismo código ARCI que el gold (no cuenta en velocidad, que va por tramo)
  candidato       el código del gold estaba entre las opciones que se dieron al LLM
  cita            alguna de las citas del gold está entre las fuentes de la respuesta
  claves          todas las claves aparecen en la respuesta (factuales y trampas)
"""

import argparse
import json
import time
from pathlib import Path

import yaml

from trafico_agent.agent import ELECCION, construir
from trafico_agent.llm import cola, ollama

RAIZ = Path(__file__).parents[1]
CAMPOS = ("gravedad", "importe_eur", "pronto_pago_eur", "puntos")


def _ok_comportamiento(esperado, obtenido):
    # "corregir" (premisa falsa) se hace respondiendo con la cita correcta
    return obtenido == esperado or (esperado == "corregir" and obtenido in ("responder", "avisar"))


def evaluar(q, r, segundos):
    fila = {
        "id": q["id"],
        "comportamiento": r.get("comportamiento"),
        "segundos": round(segundos, 1),
    }
    fila["ok_comportamiento"] = _ok_comportamiento(q["comportamiento"], r.get("comportamiento"))
    fuentes = {(f["norma"], f["id_bloque"]) for f in r.get("fuentes", [])}
    if q.get("citas") and q["comportamiento"] != "rechazar":
        grupos = [g if isinstance(g, list) else [g] for g in q["citas"]]
        fila["ok_cita"] = any((c["norma"], c["id_bloque"]) in fuentes for g in grupos for c in g)
    if (gold := q.get("sancion")) is not None:
        s = r.get("sancion") or {}
        fila["obtenido"] = {k: s.get(k) for k in ("codigo", *CAMPOS)}
        fila["ok_sancion"] = all(s.get(k) == gold[k] for k in CAMPOS)
        if gold["codigo"] and s.get("fuente") != "Anexo IV de la LSV":  # velocidad: por tramo
            fila["ok_codigo"] = s.get("codigo") == gold["codigo"]
            fila["ok_candidato"] = gold["codigo"] in (r.get("candidatos") or [])
    if q.get("claves"):
        texto = r.get("respuesta", "").lower()
        fila["ok_claves"] = all(c.lower() in texto for c in q["claves"])
    return fila


def resumen(filas):
    out = {"n": len(filas)}
    for k in (
        "ok_comportamiento",
        "ok_sancion",
        "ok_codigo",
        "ok_candidato",
        "ok_cita",
        "ok_claves",
    ):
        vals = [f[k] for f in filas if k in f]
        if vals:
            out[k.removeprefix("ok_")] = f"{sum(vals)}/{len(vals)} ({sum(vals) / len(vals):.0%})"
    out["segundos_media"] = round(sum(f["segundos"] for f in filas) / len(filas), 1)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tipo", default="situacion")
    p.add_argument("--modelo", default=None)
    p.add_argument("--n", type=int, default=None, help="solo las n primeras (prueba rápida)")
    args = p.parse_args()
    preguntas = yaml.safe_load((RAIZ / "eval" / "questions.yaml").read_text(encoding="utf-8"))
    preguntas = [q for q in preguntas if args.tipo == "todos" or q["tipo"] == args.tipo][: args.n]
    # --modelo cola:haiku -> respuestas a mano desde eval/cola/haiku.json (ver llm.cola)
    if args.modelo and args.modelo.startswith("cola:"):
        llm = cola(args.modelo.split(":", 1)[1])
    else:
        llm = ollama(args.modelo)
    grafo = construir(llm)
    filas = []
    for i, q in enumerate(preguntas, 1):
        t0 = time.perf_counter()
        try:
            r = grafo.invoke({"pregunta": q["pregunta"]})
        except Exception as e:  # noqa: BLE001 — un fallo del modelo cuenta como fallo, no corta la evaluación
            r = {"error": repr(e)}
        fila = evaluar(q, r, time.perf_counter() - t0)
        fila["respuesta"] = r.get("respuesta") or r.get("error")
        filas.append(fila)
        marcas = " ".join(
            f"{k[3:]}={'✓' if v else '✗'}" for k, v in fila.items() if k.startswith("ok_")
        )
        print(f"[{i}/{len(preguntas)}] {q['id']} {fila['segundos']}s {marcas}", flush=True)
    res = resumen(filas)
    print("\n" + json.dumps(res, ensure_ascii=False, indent=1))
    nombre = llm.nombre.replace(":", "_").replace("/", "_")
    out = RAIZ / "eval" / "results" / f"agente_{args.tipo}_{nombre}_{ELECCION}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps({"resumen": res, "preguntas": filas}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"Detalle -> {out.relative_to(RAIZ)}")
    if hasattr(llm, "pendientes"):
        print(f"Llamadas pendientes de respuesta: {llm.pendientes()}")


if __name__ == "__main__":
    main()
