import sqlite3

from trafico_agent.index import Indice, rrf, tokenizar


def test_tokenizar_sin_tildes_ni_vacias_y_con_raiz():
    assert tokenizar("¿Es obligatorio el cinturón en vías urbanas?") == [
        "obligatori",
        "cinturon",
        "vias",
        "urban",
    ]


def test_rrf_premia_lo_que_aparece_en_ambos():
    assert rrf([[1, 2, 3], [3, 4, 1]])[:2] == [1, 3]


def test_rrf_con_pesos():
    assert rrf([[1, 2], [2, 1]], pesos=[0.5, 1]) == [2, 1]


def test_bm25(tmp_path):
    db = sqlite3.connect(tmp_path / "t.db")
    db.execute("CREATE TABLE fragmentos (id, norma, id_bloque, titulo, contexto, texto)")
    db.executemany(
        "INSERT INTO fragmentos VALUES (?,?,?,?,?,?)",
        [
            (
                "1",
                "CIR",
                "a117",
                "Artículo 117. Cinturones.",
                None,
                "Uso del cinturón de seguridad.",
            ),
            ("2", "CIR", "a20", "Artículo 20. Alcohol.", None, "Tasas de alcohol en sangre."),
            ("3", "CIR", "a48", "Artículo 48. Velocidad.", None, "Velocidades máximas en autovía."),
        ],
    )
    db.commit()
    idx = Indice(tmp_path / "t.db")
    assert idx.emb is None
    assert [
        f["id_bloque"] for f in idx.buscar("¿cuánto alcohol puedo llevar?", modo="bm25", k=1)
    ] == ["a20"]


def test_reordenar_cachea_pares(tmp_path, monkeypatch):
    from trafico_agent import index

    llamadas = []

    class Falso:
        def predict(self, pares):
            llamadas.append(len(pares))
            return [len(t) for _, t in pares]  # el texto más largo primero

    monkeypatch.setattr(index, "_modelo_rerank", lambda: Falso())
    db = sqlite3.connect(tmp_path / "t.db")
    db.execute("CREATE TABLE fragmentos (id, norma, id_bloque, titulo, contexto, texto)")
    db.executemany(
        "INSERT INTO fragmentos VALUES (?,?,?,?,?,?)",
        [("1", "CIR", "a", "T", None, "corto"), ("2", "CIR", "b", "T", None, "bastante más largo")],
    )
    db.commit()
    idx = Indice(tmp_path / "t.db")
    assert idx._reordenar("q", [0, 1]) == [1, 0]
    assert idx._reordenar("q", [1, 0]) == [1, 0]
    assert llamadas == [2]  # la segunda vez no vuelve a llamar al modelo
