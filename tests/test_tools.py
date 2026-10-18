from pathlib import Path

import pytest

from trafico_agent import tools

DB = Path(__file__).parents[1] / "data" / "trafico.db"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="falta data/trafico.db")


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(tools, "DB", str(DB))


def test_consultar_sancion():
    s = tools.consultar_sancion("CIR 020 1 5E")
    assert (s["gravedad"], s["importe_eur"], s["pronto_pago_eur"], s["puntos"]) == (
        "muy_grave",
        500,
        250,
        4,
    )
    assert s["aviso"] is None
    assert tools.consultar_sancion("NO EXISTE") is None


def test_aviso_si_la_arci_esta_desfasada():
    assert tools.consultar_sancion("CIR 121 4 5B")["aviso"] == tools.AVISO_DESFASE


def test_sanciones_de_articulos_incluye_el_precepto_lsv_equivalente():
    codigos = {s["codigo"] for s in tools.sanciones_de_articulos([("LSV", "a14")])}
    assert "CIR 020 1 5E" in codigos  # alcohol: RGC 20 ↔ LSV 14


@pytest.mark.parametrize(
    "limite, kmh, esperado",
    [(50, 50, None), (50, 71, ("grave", 300, 2, 150)), (120, 200, ("muy_grave", 600, 6, 300))],
)
def test_consultar_velocidad(limite, kmh, esperado):
    v = tools.consultar_velocidad(limite, kmh)
    assert (v and (v["gravedad"], v["multa_eur"], v["puntos"], v["pronto_pago_eur"])) == esperado


def test_leer_articulo():
    a = tools.leer_articulo("CIR", "a85")
    assert "1,5 metros" in a["texto"] and a["url"].endswith("#a85")
