"""El conjunto de evaluación es el contrato: estructura válida y gold coherente con los datos."""

import sqlite3
from collections import Counter
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).parents[1]
PREGUNTAS = yaml.safe_load((RAIZ / "eval" / "questions.yaml").read_text(encoding="utf-8"))
DB = RAIZ / "data" / "trafico.db"

TIPOS = {"F": "factual", "S": "situacion", "T": "trampa"}
COMPORTAMIENTOS = {"responder", "aclarar", "rechazar", "corregir", "avisar"}
MOTIVOS = {"ordenanza", "penal", "premisa_falsa", "competencia", "fuera_ambito", "arci_desfasada"}
CAMPOS_SANCION = {"codigo", "gravedad", "importe_eur", "pronto_pago_eur", "puntos"}


def grupos(q):
    """Cada elemento de `citas` es una cita o una lista de citas equivalentes."""
    return [g if isinstance(g, list) else [g] for g in q.get("citas", [])]


@pytest.mark.parametrize("q", PREGUNTAS, ids=[q["id"] for q in PREGUNTAS])
def test_esquema(q):
    assert TIPOS[q["id"][0]] == q["tipo"]
    assert q["pregunta"].strip()
    assert q["comportamiento"] in COMPORTAMIENTOS
    for g in grupos(q):
        for c in g:
            assert set(c) == {"norma", "id_bloque", "apartado"} and c["norma"] in {"CIR", "LSV"}
    if q["tipo"] == "situacion" and q["comportamiento"] in ("responder", "avisar"):
        assert set(q["sancion"]) == CAMPOS_SANCION
    if q["comportamiento"] == "aclarar":
        assert q["falta"]
    if q["tipo"] == "trampa" or q["comportamiento"] == "avisar":
        assert q["motivo"] in MOTIVOS
    if q["comportamiento"] in ("responder", "corregir"):
        assert q.get("citas"), "sin cita no hay respuesta"


def test_ids_unicos_y_tamano():
    assert len({q["id"] for q in PREGUNTAS}) == len(PREGUNTAS)
    assert Counter(q["tipo"] for q in PREGUNTAS) == {"factual": 60, "situacion": 60, "trampa": 30}


@pytest.mark.skipif(not DB.exists(), reason="falta data/trafico.db")
def test_gold_coherente_con_los_datos():
    db = sqlite3.connect(DB)

    def texto(c):
        fila = db.execute(
            "SELECT texto FROM articulos WHERE norma=? AND id_bloque=?",
            (c["norma"], c["id_bloque"]),
        ).fetchone()
        assert fila, f"no existe {c}"
        return fila[0].lower()

    for q in PREGUNTAS:
        textos = [texto(c) for g in grupos(q) for c in g]
        if q["tipo"] == "factual":  # las claves salen del propio texto citado
            for clave in q.get("claves", []):
                assert any(clave.lower() in t for t in textos), (
                    f"{q['id']}: '{clave}' no está en las citas"
                )
        s = q.get("sancion")
        if s and s["codigo"]:
            fila = db.execute(
                "SELECT gravedad, importe_eur, pronto_pago_eur, puntos FROM sanciones WHERE codigo=?",
                (s["codigo"],),
            ).fetchone()
            esperado = (s["gravedad"], s["importe_eur"], s["pronto_pago_eur"], s["puntos"])
            assert fila == esperado, f"{q['id']}: ARCI dice {fila}"
