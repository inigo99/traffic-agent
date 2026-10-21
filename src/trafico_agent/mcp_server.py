"""Servidor MCP `trafico-mcp`: las herramientas de `tools.py` para Claude Desktop u otro cliente.

Todas son deterministas (SQL y búsqueda); ninguna llama a un LLM. Cada respuesta lleva `aviso`.

Uso: TRAFICO_DB=/ruta/a/data/trafico.db uv run trafico-mcp   (stdio)
"""

from mcp.server.mcpserver import MCPServer

from trafico_agent import tools

servidor = MCPServer(
    "trafico-mcp",
    instructions=(
        "Normativa estatal de tráfico de España: Ley de Tráfico (RDL 6/2015, 'LSV'), Reglamento "
        "General de Circulación (RD 1428/2003, 'CIR') y la guía de infracciones ARCI de la DGT. "
        "Cita siempre el artículo y su url del BOE; importes y puntos solo de estas herramientas. "
        "No cubre ordenanzas municipales ni el Código Penal."
    ),
)


def _con_aviso(**datos):
    return datos | {"aviso": tools.AVISO}


@servidor.tool()
def buscar_normativa(consulta: str, k: int = 5) -> dict:
    """Busca en la LSV y el RGC los fragmentos más relevantes para una consulta en lenguaje natural.
    Devuelve norma, id_bloque, artículo, título, fragmento y url del BOE."""
    return _con_aviso(resultados=tools.buscar_normativa(consulta, k=k))


@servidor.tool()
def leer_articulo(norma: str, id_bloque: str) -> dict:
    """Texto vigente completo de un artículo. norma: 'CIR' (RGC) o 'LSV'; id_bloque: el de
    buscar_normativa (p. ej. 'a117', 'aniv')."""
    return _con_aviso(articulo=tools.leer_articulo(norma, id_bloque))


@servidor.tool()
def consultar_sancion(codigo: str) -> dict:
    """Fila de la guía ARCI por código (p. ej. 'CIR 117 1 5E'): hecho denunciado, gravedad,
    importe, importe con pronto pago, puntos y artículo."""
    return _con_aviso(sancion=tools.consultar_sancion(codigo))


@servidor.tool()
def sanciones_parecidas(hecho: str, k: int = 10) -> dict:
    """Filas ARCI cuyo hecho denunciado se parece a la descripción dada (para encontrar el código)."""
    return _con_aviso(sanciones=tools.sanciones_parecidas(hecho, k))


@servidor.tool()
def consultar_velocidad(limite_kmh: int, velocidad_kmh: int) -> dict:
    """Sanción por exceso de velocidad (cinemómetro) según el Anexo IV de la LSV.
    tramo = null si no supera el límite."""
    return _con_aviso(
        tramo=tools.consultar_velocidad(limite_kmh, velocidad_kmh),
        fuente="Anexo IV de la LSV (BOE-A-2015-11722)",
    )


@servidor.tool()
def version_normativa() -> dict:
    """Fecha de la versión consolidada de cada norma del corpus."""
    return _con_aviso(versiones=tools.version_normativa())


def main():
    servidor.run()


if __name__ == "__main__":
    main()
