"""Recuperación sobre `fragmentos`: BM25, vectores (bge-m3), híbrida (RRF) y reranker.

Modo por defecto: vectores. El reranker gana +0,03 de recall@5 pero en CPU tarda ~30 s por
consulta (S2, notas/s2-recuperacion.md); solo tiene sentido con GPU.

Los vectores y el reranker necesitan el extra `ml` (`uv sync --extra ml`) y descargar los modelos
de Hugging Face; BM25 funciona sin ellos.

Generar los vectores: uv run --extra ml python -m trafico_agent.index [data/trafico.db]
"""

import re
import sqlite3
import sys
import unicodedata
from functools import cache
from pathlib import Path

import numpy as np
import snowballstemmer
from rank_bm25 import BM25Okapi

MODELO_EMB = "BAAI/bge-m3"
MODELO_RERANK = "BAAI/bge-reranker-v2-m3"
CANDIDATOS = 30  # top-k de cada recuperador antes de fusionar / reordenar
RRF_K = 60
RERANK_MAX_TOKENS = 512
PESO_BM25 = 0.5  # en la híbrida ponderada; con 1 (RRF clásico) BM25 empeoraba a los vectores

# Palabras vacías frecuentes en preguntas y en el texto legal (tras quitar tildes).
_VACIAS = (
    "a al algo con como cual cuando de del desde donde el en entre es esta este esto ha hay la las "
    "le lo los me mi mas muy ni no o para pero por que se si sin sobre su sus te tengo un una uno "
    "unos unas y ya yo"
)
VACIAS = frozenset(_VACIAS.split())
_stem = snowballstemmer.stemmer("spanish")


def tokenizar(texto):
    """Minúsculas, sin tildes, sin palabras vacías y con raíz (snowball)."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return _stem.stemWords([w for w in re.findall(r"\w+", t) if w not in VACIAS])


def _texto_indexado(f):
    return "\n".join(x for x in (f["titulo"], f["contexto"], f["texto"]) if x)


class Indice:
    def __init__(self, db_path, emb_path=None):
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        self.frags = [dict(r) for r in db.execute("SELECT * FROM fragmentos ORDER BY id")]
        self.bm25 = BM25Okapi([tokenizar(_texto_indexado(f)) for f in self.frags])
        emb_path = Path(emb_path or Path(db_path).with_name("embeddings.npy"))
        self.emb = np.load(emb_path) if emb_path.exists() else None
        self._rerank_cache = {}  # (consulta, fragmento) -> puntuación: los modos rerank comparten pares
        if self.emb is not None and len(self.emb) != len(self.frags):
            raise ValueError(f"{emb_path} no corresponde a los fragmentos actuales: regenéralo")

    # Cada recuperador devuelve índices de self.frags ordenados de mejor a peor.
    def buscar_bm25(self, consulta, k=CANDIDATOS):
        return list(np.argsort(-self.bm25.get_scores(tokenizar(consulta)))[:k])

    def buscar_vectores(self, consulta, k=CANDIDATOS):
        q = _vector_consulta(consulta)
        return list(np.argsort(-(self.emb @ q))[:k])

    def buscar_hibrida(self, consulta, k=CANDIDATOS):
        return rrf([self.buscar_bm25(consulta), self.buscar_vectores(consulta)])[:k]

    def buscar_hibrida_ponderada(self, consulta, k=CANDIDATOS):
        """Como la híbrida, pero BM25 pesa la mitad que los vectores."""
        rankings = [self.buscar_bm25(consulta), self.buscar_vectores(consulta)]
        return rrf(rankings, pesos=[PESO_BM25, 1])[:k]

    def buscar_rerank(self, consulta, k=CANDIDATOS):
        """Reranker sobre los candidatos de la híbrida."""
        return self._reordenar(consulta, self.buscar_hibrida(consulta))[:k]

    def buscar_rerank_vectores(self, consulta, k=CANDIDATOS):
        """Reranker sobre los candidatos de los vectores (sin BM25)."""
        return self._reordenar(consulta, self.buscar_vectores(consulta))[:k]

    def _reordenar(self, consulta, cand):
        nuevos = [i for i in cand if (consulta, i) not in self._rerank_cache]
        if nuevos:
            pares = [(consulta, _texto_indexado(self.frags[i])) for i in nuevos]
            for i, s in zip(nuevos, _modelo_rerank().predict(pares), strict=True):
                self._rerank_cache[(consulta, i)] = float(s)
        return sorted(cand, key=lambda i: self._rerank_cache[(consulta, i)], reverse=True)

    def buscar(self, consulta, modo="vectores", k=5):
        return [self.frags[i] for i in getattr(self, f"buscar_{modo}")(consulta)[:k]]


def rrf(rankings, k=RRF_K, pesos=None):
    """Reciprocal Rank Fusion: suma peso/(k + posición) de cada ranking."""
    puntos = {}
    for ranking, peso in zip(rankings, pesos or [1] * len(rankings), strict=True):
        for pos, i in enumerate(ranking):
            puntos[i] = puntos.get(i, 0) + peso / (k + pos + 1)
    return sorted(puntos, key=puntos.get, reverse=True)


@cache
def _modelo_emb():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODELO_EMB)


@cache
def _modelo_rerank():
    from sentence_transformers import CrossEncoder

    # ponytail: trunca a 512 tokens (sin límite, los fragmentos largos hacen el CPU muy lento)
    return CrossEncoder(MODELO_RERANK, max_length=RERANK_MAX_TOKENS)


@cache
def _vector_consulta(consulta):
    return _modelo_emb().encode([consulta], normalize_embeddings=True)[0]


def generar_embeddings(db_path):
    """Vectores normalizados de todos los fragmentos -> data/embeddings.npy (mismo orden que `id`)."""
    idx = Indice(db_path, emb_path="/nonexistent")
    textos = [_texto_indexado(f) for f in idx.frags]
    emb = _modelo_emb().encode(
        textos, normalize_embeddings=True, batch_size=8, show_progress_bar=True
    )
    out = Path(db_path).with_name("embeddings.npy")
    np.save(out, emb.astype(np.float32))
    print(f"{len(textos)} vectores {emb.shape[1]}d -> {out}")


if __name__ == "__main__":
    generar_embeddings(sys.argv[1] if len(sys.argv) > 1 else "data/trafico.db")
