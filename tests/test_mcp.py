"""El servidor MCP de punta a punta con el cliente del SDK (en proceso, sin modelos)."""

import json
from pathlib import Path

import anyio
import pytest
from mcp import Client

from trafico_agent import tools
from trafico_agent.mcp_server import servidor

DB = Path(__file__).parents[1] / "data" / "trafico.db"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="falta data/trafico.db")


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(tools, "DB", str(DB))


def llamar(nombre, args=None):
    async def go():
        async with Client(servidor) as c:
            return (await c.list_tools()).tools, await c.call_tool(nombre, args or {})

    lista, r = anyio.run(go)
    assert not r.is_error, r
    return [t.name for t in lista], r.structured_content or json.loads(r.content[0].text)


def test_lista_de_herramientas_y_aviso():
    nombres, r = llamar("consultar_sancion", {"codigo": "CIR 117 1 5E"})
    assert set(nombres) == {
        "buscar_normativa",
        "leer_articulo",
        "consultar_sancion",
        "sanciones_parecidas",
        "consultar_velocidad",
        "version_normativa",
    }
    assert r["sancion"]["puntos"] == 4 and r["aviso"] == tools.AVISO


def test_velocidad_y_articulo():
    _, r = llamar("consultar_velocidad", {"limite_kmh": 120, "velocidad_kmh": 151})
    assert r["tramo"]["multa_eur"] == 300 and r["tramo"]["puntos"] == 2
    _, r = llamar("leer_articulo", {"norma": "CIR", "id_bloque": "a117"})
    assert "cinturones de seguridad" in r["articulo"]["texto"].lower()
