import sqlite3
from pathlib import Path

import pytest

from trafico_agent.ingest.arci import build

PDF = Path(__file__).parents[1] / "data" / "arci.pdf"
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="falta data/arci.pdf")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "t.db"
    build(PDF, path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def fila(db, codigo):
    return dict(db.execute("SELECT * FROM sanciones WHERE codigo = ?", (codigo,)).fetchone())


def test_solo_corpus_v1(db):
    assert db.execute("SELECT COUNT(*) FROM sanciones").fetchone()[0] == 552
    assert {r[0] for r in db.execute("SELECT DISTINCT norma FROM sanciones")} == {"CIR", "LSV"}


@pytest.mark.parametrize(
    "codigo, gravedad, importe, pronto, puntos, lsv",
    [
        ("CIR 020 1 5E", "muy_grave", 500, 250, 4, (14, "1", "77.c")),  # alcohol 0,25 mg/l
        ("LSV 076 - 5A", "grave", 200, 100, 6, (76, None, "76.g")),  # móvil en la mano
        ("CIR 117 1 5E", "grave", 200, 100, 4, (47, None, "76.h")),  # cinturón
        ("LSV 076 - 5F", "grave", 200, None, 0, (18, None, "76.z.3")),  # ZBE, sin reducción
        ("CIR 002 1 5D", "leve", 100, 50, 0, (10, "1", None)),
    ],
)
def test_filas_criticas(db, codigo, gravedad, importe, pronto, puntos, lsv):
    f = fila(db, codigo)
    assert (f["gravedad"], f["importe_eur"], f["pronto_pago_eur"], f["puntos"]) == (
        gravedad,
        importe,
        pronto,
        puntos,
    )
    assert (f["lsv_articulo"], f["lsv_apartado"], f["tipificacion"]) == lsv


def test_velocidad_puntos_por_tramo(db):
    assert fila(db, "CIR 048 1 5M")["puntos"] is None


def test_pronto_pago_es_la_mitad(db):
    malas = db.execute(
        "SELECT codigo FROM sanciones WHERE pronto_pago_eur IS NOT NULL"
        " AND pronto_pago_eur * 2 != importe_eur"
    ).fetchall()
    assert malas == []


def test_sin_reduccion_no_tiene_pronto_pago(db):
    n = db.execute(
        "SELECT COUNT(*) FROM sanciones WHERE sin_reduccion = 1 AND pronto_pago_eur IS NOT NULL"
    ).fetchone()[0]
    assert n == 0
