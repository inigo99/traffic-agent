import sqlite3
from datetime import date
from pathlib import Path

from trafico_agent.ingest import boe

FIX = Path(__file__).parent / "fixtures" / "boe"


def fake_fetch(url, accept):
    nombre = "indice.json" if url.endswith("/indice") else url.rsplit("/", 1)[1] + ".xml"
    return (FIX / nombre).read_bytes()


def test_version_vigente_ignora_futuras():
    xml = (FIX / "a14.xml").read_bytes()
    assert boe.version_vigente(xml, date(2022, 1, 1))[0] == "20160131"
    assert boe.version_vigente(xml, date(2026, 1, 1))[0] == "20220321"


def test_build(tmp_path):
    db_path = tmp_path / "t.db"
    boe.build(db_path, fetch=fake_fetch, pausa=0)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    a14 = dict(
        db.execute("SELECT * FROM articulos WHERE norma='LSV' AND id_bloque='a14'").fetchone()
    )
    assert (a14["parte"], a14["tipo"], a14["articulo"]) == ("texto", "articulo", "14")
    assert a14["titulo"] == "Artículo 14. Bebidas alcohólicas y drogas."
    assert a14["contexto"] == (
        "TÍTULO II. Normas de comportamiento en la circulación"
        " > CAPÍTULO I. Normas de comportamiento en la circulación"
    )
    assert "menor de edad" in a14["texto"]  # versión vigente
    assert "Téngase en cuenta" not in a14["texto"] and "Se modifica" not in a14["texto"]
    assert a14["url"] == "https://www.boe.es/buscar/act.php?id=BOE-A-2015-11722#a14"

    assert (
        db.execute("SELECT COUNT(*) FROM articulos WHERE id_bloque IN ('tii','ci-2')").fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT fecha_actualizacion FROM versiones WHERE id_norma=?", (boe.NORMAS["LSV"],)
        ).fetchone()[0]
        == "20251204"
    )


def test_velocidades(tmp_path):
    db_path = tmp_path / "t.db"
    boe.build(db_path, fetch=fake_fetch, pausa=0)
    db = sqlite3.connect(db_path)
    assert db.execute("SELECT COUNT(*) FROM velocidades").fetchone()[0] == 60

    def tramo(limite, kmh):
        return db.execute(
            "SELECT gravedad, multa_eur, puntos FROM velocidades WHERE limite=? AND desde<=?"
            " AND (hasta IS NULL OR hasta>=?)",
            (limite, kmh, kmh),
        ).fetchall()

    assert tramo(50, 71) == [("grave", 300.0, 2)]  # la pregunta "71 vs 81 en vía de 50"
    assert tramo(50, 81) == [("grave", 400.0, 4)]
    assert tramo(120, 151) == [("grave", 300.0, 2)]
    assert tramo(120, 200) == [("muy_grave", 600.0, 6)]
    assert tramo(90, 105) == [("grave", 100.0, 0)]
