"""Tras `arci` y `boe`: cruce sanciones↔artículos (tabla `sancion_articulo`) y troceado (`fragmentos`).

Uso: uv run python -m trafico_agent.ingest.postproceso [data/trafico.db]
"""

import re
import sqlite3
import sys

MAX_CHARS = 3000  # ~90 % de los artículos caben enteros (mediana 1 116, p90 2 946)
APARTADO = re.compile(r"^(\d+)\. ")


def estado_apartado(texto, apartado):
    """'ok' | 'sin_apartado' | 'apartado_implicito' | 'apartado_no_encontrado' | 'letra_no_encontrada'.

    `apartado` viene de la ARCI: '2', '1-B' (apartado 1, letra b) o None.
    """
    if apartado is None:
        return "sin_apartado"
    num, _, letra = apartado.partition("-")
    m = re.search(rf"\n{num}\. (.*?)(?=\n\d+\. |\Z)", texto, re.DOTALL)
    if not m:
        numerado = re.search(r"\n\d+\. ", texto)
        return "apartado_implicito" if num == "1" and not numerado else "apartado_no_encontrado"
    if letra and not re.search(rf"(^|\n){letra.lower()}\) ", m.group(1)):
        return "letra_no_encontrada"
    return "ok"


def cruce(db):
    arts = {}
    for norma, art, bloque, texto in db.execute(
        "SELECT norma, articulo, id_bloque, texto FROM articulos"
        " WHERE parte = 'texto' AND tipo = 'articulo'"
    ):
        arts.setdefault((norma, art), []).append((bloque, texto))
    filas = []
    for codigo, norma, art, apartado, lsv_art in db.execute(
        "SELECT codigo, norma, articulo, apartado, lsv_articulo FROM sanciones"
    ):
        m = arts.get((norma, str(art)), [])
        lsv = arts.get(("LSV", str(lsv_art)), [])
        if len(m) == 1:
            estado = estado_apartado(m[0][1], apartado)
        else:
            estado = "ambiguo" if m else "articulo_no_encontrado"
        filas.append(
            (
                codigo,
                m[0][0] if len(m) == 1 else None,
                lsv[0][0] if len(lsv) == 1 else None,
                estado,
            )
        )
    db.execute("DROP TABLE IF EXISTS sancion_articulo")
    db.execute("""CREATE TABLE sancion_articulo (
  codigo TEXT PRIMARY KEY REFERENCES sanciones(codigo),
  id_bloque TEXT,        -- artículo del precepto (CIR o LSV) en `articulos`
  lsv_id_bloque TEXT,    -- artículo LSV equivalente
  estado TEXT NOT NULL)""")
    db.executemany("INSERT INTO sancion_articulo VALUES (?,?,?,?)", filas)
    return filas


def trocear(texto, max_chars=MAX_CHARS):
    """[(apartado | None, texto)]. Entero si cabe; si no, un trozo por apartado numerado
    (y, si aún es largo o no hay apartados, por grupos de párrafos). El título se repite."""
    if len(texto) <= max_chars:
        return [(None, texto)]
    titulo, *lineas = texto.split("\n")
    bloques = []  # [(apartado, [líneas])]
    for linea in lineas:
        if (m := APARTADO.match(linea)) or not bloques:
            bloques.append((m.group(1) if m else None, []))
        bloques[-1][1].append(linea)
    trozos = []
    for apartado, ls in bloques:
        actual = []
        for linea in ls:
            if actual and len("\n".join(actual + [linea])) > max_chars:
                trozos.append((apartado, actual))
                actual = []
            actual.append(linea)
        trozos.append((apartado, actual))
    return [(ap, "\n".join([titulo, *ls])) for ap, ls in trozos]


def fragmentos(db):
    filas = []
    for id_norma, norma, bloque, parte, tipo, art, titulo, contexto, texto, url in db.execute(
        "SELECT id_norma, norma, id_bloque, parte, tipo, articulo, titulo, contexto, texto, url"
        " FROM articulos"
    ):
        for i, (apartado, trozo) in enumerate(trocear(texto)):
            filas.append(
                (
                    f"{id_norma}#{bloque}#{i}",
                    id_norma,
                    norma,
                    bloque,
                    parte,
                    tipo,
                    art,
                    apartado,
                    titulo,
                    contexto,
                    trozo,
                    url,
                )
            )
    db.execute("DROP TABLE IF EXISTS fragmentos")
    db.execute("""CREATE TABLE fragmentos (
  id TEXT PRIMARY KEY,   -- 'BOE-A-2003-23514#a48#0'
  id_norma TEXT NOT NULL, norma TEXT NOT NULL, id_bloque TEXT NOT NULL,
  parte TEXT NOT NULL, tipo TEXT NOT NULL, articulo TEXT NOT NULL,
  apartado TEXT,         -- NULL si es el artículo entero o un trozo sin numerar
  titulo TEXT NOT NULL, contexto TEXT, texto TEXT NOT NULL, url TEXT NOT NULL)""")
    db.executemany(f"INSERT INTO fragmentos VALUES ({','.join('?' * 12)})", filas)
    return filas


def build(db_path):
    with sqlite3.connect(db_path) as db:
        filas = cruce(db)
        resumen = {}
        for *_, estado in filas:
            resumen[estado] = resumen.get(estado, 0) + 1
        print("cruce:", resumen)
        for codigo, _, _, estado in filas:
            if estado not in ("ok", "sin_apartado", "apartado_implicito"):
                print(f"  {estado}: {codigo}")
        print(f"fragmentos: {len(fragmentos(db))}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "data/trafico.db")
