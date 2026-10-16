"""Recall@5 y MRR de cada configuración de recuperación sobre las preguntas con citas.

Uso: uv run [--extra ml] python eval/run_retrieval.py [data/trafico.db] [--rerank]
Las configuraciones con vectores se saltan si no existe data/embeddings.npy.
"""

import json
import sys
import time
from pathlib import Path

import yaml

from trafico_agent.index import CANDIDATOS, Indice

RAIZ = Path(__file__).parents[1]
MODOS = ["bm25", "vectores", "hibrida", "hibrida_ponderada"]
MODOS_RERANK = ["rerank", "rerank_vectores"]  # lentos en CPU: solo con --rerank


def bloques_ordenados(idx, modo, consulta):
    """Artículos (norma, id_bloque) únicos, en el orden en que salen sus fragmentos."""
    vistos = []
    for i in getattr(idx, f"buscar_{modo}")(consulta, k=CANDIDATOS):
        b = (idx.frags[i]["norma"], idx.frags[i]["id_bloque"])
        if b not in vistos:
            vistos.append(b)
    return vistos


def evaluar(idx, preguntas, modo):
    filas = []
    for q in preguntas:
        # Cada grupo de citas se cumple si aparece cualquiera de sus artículos equivalentes.
        gold = [
            {(c["norma"], c["id_bloque"]) for c in (g if isinstance(g, list) else [g])}
            for g in q["citas"]
        ]
        ranking = bloques_ordenados(idx, modo, q["pregunta"])
        top5 = set(ranking[:5])
        cualquiera = set().union(*gold)
        primero = next((r for r, b in enumerate(ranking, 1) if b in cualquiera), None)
        filas.append(
            {
                "id": q["id"],
                "recall@5": sum(bool(g & top5) for g in gold) / len(gold),
                "hit@5": int(bool(cualquiera & top5)),
                "rr": 1 / primero if primero else 0.0,
                "top5": [b for _, b in ranking[:5]],
            }
        )
    media = lambda k: round(sum(f[k] for f in filas) / len(filas), 3)
    return {"recall@5": media("recall@5"), "hit@5": media("hit@5"), "mrr": media("rr")}, filas


def main(db_path, rerank=False):
    preguntas = yaml.safe_load((RAIZ / "eval" / "questions.yaml").read_text(encoding="utf-8"))
    preguntas = [q for q in preguntas if q.get("citas")]
    idx = Indice(db_path)
    modos = (MODOS + (MODOS_RERANK if rerank else [])) if idx.emb is not None else ["bm25"]
    resultados = {}
    print(
        f"{len(preguntas)} preguntas con citas\n\n| Config | recall@5 | hit@5 | MRR | s |\n|---|---|---|---|---|"
    )
    for modo in modos:
        t0 = time.perf_counter()
        resumen, filas = evaluar(idx, preguntas, modo)
        resumen["segundos"] = round(time.perf_counter() - t0, 1)
        resultados[modo] = {"resumen": resumen, "preguntas": filas}
        print(
            f"| {modo} | {resumen['recall@5']} | {resumen['hit@5']} | {resumen['mrr']} "
            f"| {resumen['segundos']} |",
            flush=True,
        )
    out = RAIZ / "eval" / "results" / "retrieval.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nDetalle por pregunta -> {out.relative_to(RAIZ)}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--rerank"]
    main(args[0] if args else RAIZ / "data" / "trafico.db", rerank="--rerank" in sys.argv)
