"""El conjunto de evaluación es el contrato: estructura válida y gold coherente con los datos."""

import sqlite3
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).parents[1]
PREGUNTAS = yaml.safe_load((RAIZ / "eval" / "questions.yaml").read_text(encoding="utf-8"))
DB = RAIZ / "data" / "trafico.db"

TIPOS = {"F": "factual", "S": "situacion", "T": "trampa"}
COMPORTAMIENTOS = {"responder", "aclarar", "rechazar", "corregir", "avisar"}
MOTIVOS = {"ordenanza", "penal", "premisa_falsa", "competencia"}
CAMPOS_SANCION = {"codigo", "gravedad", "importe_eur", "pronto_pago_eur", "puntos"}


@pytest.mark.parametrize("q", PREGUNTAS, ids=[q["id"] for q in PREGUNTAS])
def test_esquema(q):
    assert TIPOS[q["id"][0]] == q["tipo"]
    assert q["pregunta"].strip()
    assert q["comportamiento"] in COMPORTAMIENTOS
    for c in q.get("citas", []):
        assert set(c) == {"norma", "id_bloque", "apartado"} and c["norma"] in {"CIR", "LSV"}
    if q["tipo"] == "situacion" and q["comportamiento"] == "responder":
        assert set(q["sancion"]) == CAMPOS_SANCION
    if q["comportamiento"] == "aclarar":
        assert q["falta"]
    if q["tipo"] == "trampa":
        assert q["motivo"] in MOTIVOS
    if q["tipo"] != "trampa" or q["comportamiento"] != "rechazar":
        assert q.get("citas") or q["comportamiento"] == "aclarar", "sin cita no hay respuesta"


def test_ids_unicos():
    ids = [q["id"] for q in PREGUNTAS]
    assert len(ids) == len(set(ids))


@pytest.mark.skipif(not DB.exists(), reason="falta data/trafico.db")
def test_gold_coherente_con_los_datos():
    db = sqlite3.connect(DB)
    for q in PREGUNTAS:
        for c in q.get("citas", []):
            assert db.execute(
                "SELECT 1 FROM articulos WHERE norma=? AND id_bloque=?",
                (c["norma"], c["id_bloque"]),
            ).fetchone(), f"{q['id']}: no existe {c}"
        s = q.get("sancion")
        if s and s["codigo"]:
            fila = db.execute(
                "SELECT gravedad, importe_eur, pronto_pago_eur, puntos FROM sanciones WHERE codigo=?",
                (s["codigo"],),
            ).fetchone()
            esperado = (s["gravedad"], s["importe_eur"], s["pronto_pago_eur"], s["puntos"])
            assert fila == esperado, f"{q['id']}: ARCI dice {fila}"
