"""Servidor MCP `trafico-mcp`: las herramientas de `tools.py` para Claude Desktop u otro cliente.

Todas son deterministas (SQL y búsqueda); ninguna llama a un LLM. Cada respuesta lleva `aviso`.
Los errores son `ToolError`: su mensaje llega al modelo y dice cómo corregir la llamada.

Uso: TRAFICO_DB=/ruta/a/data/trafico.db uv run trafico-mcp   (stdio)
"""

import os
import sys
import threading
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

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

# Todas las herramientas solo leen un corpus local cerrado.
LECTURA = ToolAnnotations(read_only_hint=True, open_world_hint=False)

# El calentamiento y las búsquedas no cargan el índice y el modelo a la vez (se duplicarían).
_carga = threading.Lock()


def _calentar():
    """En segundo plano: el servidor responde ya y la 1.ª consulta no espera al modelo."""
    with _carga:
        tools.calentar()  # si falla, solo muere este hilo: la consulta cargará lo que falte


def _bd():
    """Error accionable si falta la base: `sqlite3.connect` crearía un archivo vacío."""
    if not os.path.exists(tools.DB):
        raise ToolError(
            f"No existe la base de datos '{tools.DB}'. Define TRAFICO_DB con la ruta a "
            "trafico.db o genérala con la ingesta (README: ingest.arci, ingest.boe, "
            "ingest.postproceso)."
        )


def _con_aviso(**datos):
    return datos | {"aviso": tools.AVISO}


@servidor.tool(annotations=LECTURA)
def buscar_normativa(
    consulta: Annotated[str, Field(min_length=2, max_length=500, description="Texto libre")],
    k: Annotated[int, Field(ge=1, le=20, description="Número de fragmentos")] = 5,
) -> dict:
    """Busca en la LSV y el RGC los fragmentos más relevantes para una consulta en lenguaje natural.
    Devuelve norma, id_bloque, artículo, título, fragmento y url del BOE."""
    _bd()
    with _carga:
        resultados = tools.buscar_normativa(consulta, k=k)
    return _con_aviso(resultados=resultados)


@servidor.tool(annotations=LECTURA)
def leer_articulo(
    norma: Annotated[Literal["CIR", "LSV"], Field(description="'CIR' (RGC) o 'LSV'")],
    id_bloque: Annotated[str, Field(max_length=40, description="El de buscar_normativa")],
) -> dict:
    """Texto vigente completo de un artículo. id_bloque: el de buscar_normativa
    (p. ej. 'a117', 'aniv')."""
    _bd()
    articulo = tools.leer_articulo(norma, id_bloque)
    if articulo is None:
        raise ToolError(
            f"No existe el artículo {norma}/{id_bloque}. Usa el id_bloque y la norma que "
            "devuelve buscar_normativa (p. ej. 'a117')."
        )
    return _con_aviso(articulo=articulo)


@servidor.tool(annotations=LECTURA)
def consultar_sancion(
    codigo: Annotated[str, Field(max_length=40, description="Código ARCI, p. ej. 'CIR 117 1 5E'")],
) -> dict:
    """Fila de la guía ARCI por código (p. ej. 'CIR 117 1 5E'): hecho denunciado, gravedad,
    importe, importe con pronto pago, puntos y artículo."""
    _bd()
    sancion = tools.consultar_sancion(codigo)
    if sancion is None:
        raise ToolError(
            f"No hay ninguna fila ARCI con el código '{codigo}'. Búscala con sanciones_parecidas."
        )
    return _con_aviso(sancion=sancion)


@servidor.tool(annotations=LECTURA)
def sanciones_parecidas(
    hecho: Annotated[str, Field(min_length=2, max_length=500, description="Hecho denunciado")],
    k: Annotated[int, Field(ge=1, le=20, description="Número de filas")] = 10,
) -> dict:
    """Filas ARCI cuyo hecho denunciado se parece a la descripción dada (para encontrar el código)."""
    _bd()
    if not tools.hechos_disponibles():
        raise ToolError(
            "sanciones_parecidas no está disponible: faltan los vectores de los hechos ARCI "
            "(data/embeddings_sanciones.npz) o el extra ml, o TRAFICO_BUSQUEDA=bm25. Usa "
            "buscar_normativa, o genéralos con 'uv run --extra ml python -m trafico_agent.index'."
        )
    with _carga:
        sanciones = tools.sanciones_parecidas(hecho, k)
    datos = {"sanciones": sanciones}
    if not sanciones:
        datos["nota"] = "Sin coincidencias: prueba otra descripción o usa buscar_normativa."
    return _con_aviso(**datos)


@servidor.tool(annotations=LECTURA)
def consultar_velocidad(
    limite_kmh: Annotated[int, Field(ge=1, le=400, description="Límite de la vía, en km/h")],
    velocidad_kmh: Annotated[int, Field(ge=1, le=400, description="Velocidad medida, en km/h")],
) -> dict:
    """Sanción por exceso de velocidad (cinemómetro) según el Anexo IV de la LSV.
    tramo = null si no supera el límite."""
    _bd()
    try:
        tramo = tools.consultar_velocidad(limite_kmh, velocidad_kmh)
    except ValueError as e:
        validos = ", ".join(map(str, tools.limites_velocidad()))
        raise ToolError(f"{e}. Límites válidos (km/h): {validos}.") from e
    datos = {"tramo": tramo, "fuente": "Anexo IV de la LSV (BOE-A-2015-11722)"}
    if tramo is None:
        datos["nota"] = "No supera el límite: no hay sanción por exceso de velocidad."
    return _con_aviso(**datos)


@servidor.tool(annotations=LECTURA)
def version_normativa() -> dict:
    """Fecha de la versión consolidada de cada norma del corpus."""
    _bd()
    return _con_aviso(versiones=tools.version_normativa())


def main():
    if os.path.exists(tools.DB):
        threading.Thread(target=_calentar, daemon=True).start()
    else:
        print(f"AVISO: no existe {tools.DB}; define TRAFICO_DB.", file=sys.stderr)
    servidor.run()


if __name__ == "__main__":
    main()
