"""Legislación consolidada del BOE -> tablas `articulos`, `versiones` y `velocidades`.

Uso: uv run python -m trafico_agent.ingest.boe [data/trafico.db]
"""

import hashlib
import json
import sqlite3
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime

API = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{id}/texto"
NORMAS = {"LSV": "BOE-A-2015-11722", "CIR": "BOE-A-2003-23514"}
SIN_CONTENIDO = {"preambulo", "firma", "ir", "texto", "reglamentogeneraldecirculacion"}

SCHEMA = [
    """CREATE TABLE articulos (
  id_norma TEXT NOT NULL,        -- BOE-A-2015-11722
  norma TEXT NOT NULL,           -- LSV | CIR (mismo código que la ARCI)
  id_bloque TEXT NOT NULL,       -- a14, aniv...
  parte TEXT NOT NULL,           -- aprobatoria (RD/RDL que aprueba el texto) | texto | 'ANEXO II'...
  tipo TEXT NOT NULL,            -- articulo | anexo | disposicion
  articulo TEXT NOT NULL,        -- '14', '11 bis', 'ANEXO IV', 'Disposición adicional primera'
  titulo TEXT NOT NULL,          -- 'Artículo 14. Bebidas alcohólicas y drogas.'
  contexto TEXT,                 -- 'TÍTULO II. ... > CAPÍTULO I. ...'
  texto TEXT NOT NULL,
  fecha_version TEXT NOT NULL,   -- fecha de vigencia de la versión usada (AAAAMMDD)
  url TEXT NOT NULL,
  PRIMARY KEY (id_norma, id_bloque))""",
    """CREATE TABLE versiones (
  id_norma TEXT PRIMARY KEY,
  fecha_actualizacion TEXT NOT NULL,
  hash_texto TEXT NOT NULL,
  detectado_en TEXT NOT NULL)""",
    """CREATE TABLE velocidades (    -- Anexo IV LSV (cinemómetro)
  limite INTEGER NOT NULL,
  desde INTEGER NOT NULL,
  hasta INTEGER,                 -- NULL en muy grave (desde en adelante)
  gravedad TEXT NOT NULL,
  multa_eur REAL NOT NULL,
  puntos INTEGER NOT NULL)""",
]


def get(url, accept):
    req = urllib.request.Request(url, headers={"Accept": accept})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _textos(el):
    """Párrafos del bloque sin las notas editoriales (<blockquote>)."""
    for child in el:
        if child.tag == "blockquote":
            continue
        if child.tag == "p":
            if t := " ".join("".join(child.itertext()).split()):
                yield t
        else:
            yield from _textos(child)


def version_vigente(bloque_xml, hoy=None):
    """La versión más reciente ya en vigor: (fecha_vigencia, elemento <version>)."""
    hoy = (hoy or date.today()).strftime("%Y%m%d")
    bloque = ET.fromstring(bloque_xml).find("data/bloque")
    versiones = [v for v in bloque.findall("version") if v.get("fecha_vigencia") <= hoy]
    if not versiones:  # bloque que aún no ha entrado en vigor
        return None, None
    v = max(versiones, key=lambda v: v.get("fecha_vigencia"))
    return v.get("fecha_vigencia"), v


def _tipo(titulo):
    if titulo.startswith("Artículo"):
        return "articulo"
    if titulo.startswith("ANEXO"):
        return "anexo"
    if titulo.startswith("Disposición"):
        return "disposicion"
    return None  # TÍTULO / CAPÍTULO / Sección: solo dan contexto


NIVELES = ("TÍTULO", "CAPÍTULO", "Secci", "Subsecci")


def ingest_norma(norma, fetch=get, pausa=0.2):
    id_norma = NORMAS[norma]
    base = API.format(id=id_norma)
    indice = json.loads(fetch(base + "/indice", "application/json"))["data"][0]["bloque"]
    pila, filas, velocidades = [], [], []  # pila de encabezados: [(nivel, texto)]
    parte = "aprobatoria"  # hasta el primer TÍTULO: artículo único y disposiciones del RD/RDL
    for b in indice:
        if b["id"] in SIN_CONTENIDO or not b["titulo"]:
            continue
        time.sleep(pausa)
        fecha, v = version_vigente(fetch(f"{base}/bloque/{b['id']}", "application/xml"))
        if v is None:
            continue
        parrafos = list(_textos(v))
        tipo = _tipo(b["titulo"])
        nivel = next((i for i, p in enumerate(NIVELES) if b["titulo"].startswith(p)), None)
        if tipo is None and nivel is None:
            if not parte.startswith("ANEXO"):
                continue  # marcadores sin contenido: 'TEXTO', 'REGLAMENTO GENERAL DE CIRCULACIÓN'
            tipo = "anexo"  # apartados numerados de un anexo ('1', '2'...)
        if tipo is None:  # encabezado: 'TÍTULO II' + 'Normas de comportamiento...'
            if nivel == 0 and parte == "aprobatoria":
                parte = "texto"
            while pila and pila[-1][0] >= nivel:
                pila.pop()
            if parrafos:  # algunos encabezados derogados quedan vacíos
                pila.append((nivel, ". ".join(parrafos[:2])))
            continue
        if b["titulo"].startswith("ANEXO"):  # los anexos del RGC tienen su propio articulado
            parte, pila = b["titulo"], []
        elif tipo == "disposicion":
            pila = []
        contexto = [t for _, t in pila]
        if tipo == "articulo":
            art = b["titulo"].removeprefix("Artículo ").strip()
        elif tipo == "anexo" and not b["titulo"].startswith("ANEXO"):
            art = f"{parte}, {b['titulo']}"
        else:
            art = b["titulo"]
        filas.append(
            {
                "id_norma": id_norma,
                "norma": norma,
                "id_bloque": b["id"],
                "parte": parte,
                "tipo": tipo,
                "articulo": art,
                "titulo": parrafos[0] if parrafos else b["titulo"],
                "contexto": " > ".join(([parte] if parte.startswith("ANEXO") else []) + contexto)
                or None,
                "texto": "\n".join(parrafos),
                "fecha_version": fecha,
                "url": f"https://www.boe.es/buscar/act.php?id={id_norma}#{b['id']}",
            }
        )
        if b["id"] == "aniv" and norma == "LSV":
            velocidades = parse_velocidades(v)
    version = {
        "id_norma": id_norma,
        "fecha_actualizacion": max(b["fecha_actualizacion"] for b in indice),
        "hash_texto": hashlib.sha256("".join(f["texto"] for f in filas).encode()).hexdigest(),
        "detectado_en": datetime.now().isoformat(timespec="seconds"),
    }
    return filas, version, velocidades


def parse_velocidades(version_el):
    """Anexo IV: una fila por (límite, tramo). Columnas: 12 límites, multa, puntos."""
    tabla = version_el.find(".//table")
    trs = tabla.findall("tr")
    limites = [int(x) for x in _celdas(trs[0])[-14:-2]]
    filas = []
    for tr in trs[1:]:
        celdas = _celdas(tr)
        gravedad = "muy_grave" if "Muy grave" in celdas else "grave"
        *tramos, multa, puntos = celdas[-14:]
        for limite, tramo in zip(limites, tramos, strict=True):
            nums = [int(n) for n in tramo.split()]
            filas.append(
                {
                    "limite": limite,
                    "desde": nums[0],
                    "hasta": nums[1] if len(nums) > 1 else None,
                    "gravedad": gravedad,
                    "multa_eur": float(multa),
                    "puntos": int(puntos) if puntos.isdigit() else 0,
                }
            )
    if len(filas) != 5 * 12:
        raise ValueError(f"Anexo IV: se esperaban 60 tramos, hay {len(filas)}")
    return filas


def _celdas(tr):
    return [" ".join(_textos(td)) for td in tr.findall("td")]


def _insert(db, tabla, filas):
    cols = list(filas[0])
    db.executemany(
        f"INSERT INTO {tabla} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [tuple(f[c] for c in cols) for f in filas],
    )


def build(db_path, fetch=get, pausa=0.2):
    with sqlite3.connect(db_path) as db:
        for t in ("articulos", "versiones", "velocidades"):
            db.execute(f"DROP TABLE IF EXISTS {t}")
        for ddl in SCHEMA:
            db.execute(ddl)
        for norma in NORMAS:
            filas, version, velocidades = ingest_norma(norma, fetch, pausa)
            _insert(db, "articulos", filas)
            _insert(db, "versiones", [version])
            if velocidades:
                _insert(db, "velocidades", velocidades)
            print(f"{norma}: {len(filas)} bloques, versión {version['fecha_actualizacion']}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "data/trafico.db")
