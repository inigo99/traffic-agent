"""Herramientas deterministas sobre `data/trafico.db`. Las usan el agente y el servidor MCP.

Ningún importe ni punto sale de un LLM: todo sale de aquí (tabla ARCI y Anexo IV de la LSV).
"""

import os
import sqlite3
from functools import cache

DB = os.environ.get("TRAFICO_DB", "data/trafico.db")
# bm25 = demo ligera (sin bge-m3): sin vectores tampoco para los hechos ARCI
BUSQUEDA = os.environ.get("TRAFICO_BUSQUEDA")
AVISO = (
    "Información orientativa basada en la normativa estatal publicada en el BOE y en la guía "
    "de infracciones de la DGT. No es asesoramiento jurídico."
)
AVISO_DESFASE = (
    "La guía de la DGT cita un apartado que ya no existe en el texto vigente del BOE: "
    "el importe y los puntos pueden haber cambiado."
)


def _db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


@cache
def _indice():
    from trafico_agent.index import Indice

    return Indice(DB)


def buscar_normativa(consulta, k=5, modo=None):
    """Fragmentos más relevantes, con su artículo y url del BOE.

    Por defecto vectores; BM25 si no están generados (`data/embeddings.npy`) para que el MCP
    funcione sin el extra `ml`."""
    modo = modo or BUSQUEDA or ("vectores" if _indice().emb is not None else "bm25")
    return [
        {
            "norma": f["norma"],
            "id_bloque": f["id_bloque"],
            "articulo": f["articulo"],
            "apartado": f["apartado"],
            "titulo": f["titulo"],
            "fragmento": f["texto"],
            "url": f["url"],
        }
        for f in _indice().buscar(consulta, modo=modo, k=k)
    ]


def leer_articulo(norma, id_bloque):
    """Texto vigente completo de un artículo, con la fecha de su versión."""
    fila = (
        _db()
        .execute(
            "SELECT norma, id_bloque, parte, articulo, titulo, texto, fecha_version, url FROM articulos"
            " WHERE norma = ? AND id_bloque = ?",
            (norma, id_bloque),
        )
        .fetchone()
    )
    return dict(fila) if fila else None


_SANCION = """SELECT s.codigo, s.norma, s.articulo, s.apartado, s.gravedad, s.importe_eur,
  s.pronto_pago_eur, s.sin_reduccion, s.puntos, s.hecho_denunciado, s.observaciones,
  sa.id_bloque, sa.lsv_id_bloque, sa.estado
FROM sanciones s JOIN sancion_articulo sa USING (codigo)"""


def _sancion(fila):
    s = dict(fila)
    s["aviso"] = (
        AVISO_DESFASE if s["estado"] in ("apartado_no_encontrado", "letra_no_encontrada") else None
    )
    return s


def consultar_sancion(codigo):
    """Fila ARCI por código ('CIR 020 1 5E')."""
    fila = _db().execute(f"{_SANCION} WHERE s.codigo = ?", (codigo,)).fetchone()
    return _sancion(fila) if fila else None


def sanciones_de_articulos(bloques):
    """Filas ARCI cuyo precepto (RGC o LSV equivalente) está en `bloques` [(norma, id_bloque)]."""
    filas = []
    for norma, b in bloques:
        filas += (
            _db()
            .execute(
                f"{_SANCION} WHERE (s.norma = ? AND sa.id_bloque = ?) OR (? = 'LSV' AND sa.lsv_id_bloque = ?)",
                (norma, b, norma, b),
            )
            .fetchall()
        )
    unicas = {f["codigo"]: f for f in filas}
    return [_sancion(f) for f in unicas.values()]


def sanciones_parecidas(texto, k=12):
    """Filas ARCI cuyo hecho denunciado se parece más al texto (vectores de los hechos)."""
    if BUSQUEDA == "bm25":
        return []
    from trafico_agent.index import hechos_parecidos

    return [s for c in hechos_parecidos(DB, texto, k) if (s := consultar_sancion(c))]


def consultar_velocidad(limite, kmh):
    """Tramo del Anexo IV de la LSV (cinemómetro). None si no supera el límite."""
    if kmh <= limite:
        return None
    fila = (
        _db()
        .execute(
            "SELECT limite, desde, hasta, gravedad, multa_eur, puntos FROM velocidades"
            " WHERE limite = ? AND desde <= ? AND (hasta IS NULL OR hasta >= ?)",
            (limite, kmh, kmh),
        )
        .fetchone()
    )
    if not fila:
        raise ValueError(f"límite {limite} km/h no está en el Anexo IV")
    v = dict(fila)
    v["pronto_pago_eur"] = v["multa_eur"] / 2  # art. 94 LSV: 50 % en el procedimiento abreviado
    return v


def version_normativa():
    """Fecha de la versión consolidada de cada norma del corpus."""
    return [dict(r) for r in _db().execute("SELECT id_norma, fecha_actualizacion FROM versiones")]
