"""¿Está la fila ARCI correcta entre los candidatos? Sin LLM (solo vectores), ~1 min.

Uso: uv run python eval/run_candidatos.py

Mide, sobre las situaciones con código gold (sin velocidad ni alcohol, que no usan candidatos):
  vec@N        el código está entre los N hechos ARCI más parecidos a la pregunta
  art@K        está entre las filas de los artículos de los K fragmentos recuperados
  vecN+artK    unión de ambos (y tamaño medio de la lista que vería el LLM)
"""

from pathlib import Path

import yaml

from trafico_agent import tools

RAIZ = Path(__file__).parents[1]


def main():
    preguntas = yaml.safe_load((RAIZ / "eval/questions.yaml").read_text(encoding="utf-8"))
    casos = [
        q
        for q in preguntas
        if q["tipo"] == "situacion"
        and (q.get("sancion") or {}).get("codigo")
        and not q["sancion"]["codigo"].startswith("CIR 020")
    ]
    vec, art = {}, {}
    for q in casos:
        vec[q["id"]] = [s["codigo"] for s in tools.sanciones_parecidas(q["pregunta"], 50)]
        for k in (5, 10):
            bloques = [
                (f["norma"], f["id_bloque"]) for f in tools.buscar_normativa(q["pregunta"], k=k)
            ]
            art[q["id"], k] = {s["codigo"] for s in tools.sanciones_de_articulos(bloques)}

    def tasa(fn):
        aciertos = [q["sancion"]["codigo"] in fn(q["id"]) for q in casos]
        return f"{sum(aciertos)}/{len(casos)}"

    print(f"{len(casos)} situaciones con código ARCI")
    for n in (8, 12, 20, 30, 50):
        print(f"vec@{n}: {tasa(lambda i, n=n: set(vec[i][:n]))}")
    for k in (5, 10):
        tam = sum(len(art[i, k]) for i in vec) / len(vec)
        print(f"art@{k}: {tasa(lambda i, k=k: art[i, k])}  (media {tam:.0f} filas)")
    for n, k in ((8, 5), (12, 5), (12, 10), (20, 10)):
        tam = sum(len(set(vec[i][:n]) | art[i, k]) for i in vec) / len(vec)
        print(
            f"vec{n}+art{k}: {tasa(lambda i, n=n, k=k: set(vec[i][:n]) | art[i, k])}  (media {tam:.0f} filas)"
        )
    fallos = [
        q["id"]
        for q in casos
        if q["sancion"]["codigo"] not in set(vec[q["id"]][:20]) | art[q["id"], 10]
    ]
    print("fuera de vec20+art10:", " ".join(fallos))


if __name__ == "__main__":
    main()
