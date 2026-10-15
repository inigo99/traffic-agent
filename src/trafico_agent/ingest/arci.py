"""Guía ARCI (PDF de la DGT) -> tabla SQLite `sanciones`. Solo filas CIR/LSV (corpus v1)."""

import re
import sqlite3
import sys
from pathlib import Path

import pdfplumber

NORMAS_V1 = {"CIR", "LSV"}
GRAVEDAD = {"Leve": "leve", "Grave": "grave", "Muy grave": "muy_grave"}

SCHEMA = """
CREATE TABLE sanciones (
  codigo TEXT PRIMARY KEY,          -- 'CIR 020 1 5E'
  norma TEXT NOT NULL,              -- CIR | LSV
  articulo INTEGER NOT NULL,
  apartado TEXT,                    -- NULL si '-'
  opcion TEXT NOT NULL,
  lsv_articulo INTEGER NOT NULL,    -- precepto equivalente de la LSV
  lsv_apartado TEXT,
  tipificacion TEXT,                -- art. LSV que la califica: '76.h', '77.c', '76.z.3'; NULL en leves
  gravedad TEXT NOT NULL CHECK (gravedad IN ('leve','grave','muy_grave')),
  importe_eur REAL,                 -- NULL si variable
  pronto_pago_eur REAL,             -- NULL si no hay reducción
  sin_reduccion INTEGER NOT NULL,
  puntos INTEGER,                   -- NULL si depende del tramo (velocidad, Anexo IV LSV)
  hecho_denunciado TEXT NOT NULL,   -- recortado en el propio PDF en algunas filas
  responsable TEXT,
  observaciones TEXT,
  materia TEXT,
  abreviado INTEGER NOT NULL,
  pagina INTEGER NOT NULL
)"""


def _lines(cell):
    return [x.strip() for x in (cell or "").split("\n") if x.strip()]


def _join(cell):
    return " ".join(_lines(cell)) or None


def parse_row(r, pagina):
    norma, art, apt, opc, ptos, calif, texto, multa, resp, coment, materia, abrev = r
    normas, arts, apts = _lines(norma), _lines(art), _lines(apt)
    if normas[0] not in NORMAS_V1:
        return None
    cal = _lines(calif)
    tip = None
    if len(cal) > 1:
        art_tip, letra = cal[1].split(".")
        sub = cal[2].rstrip(")") if len(cal) > 2 else "-"
        tip = f"{int(art_tip)}.{letra}" + ("" if sub == "-" else f".{sub}")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", multa or "")]
    sin_red = "REDUC" in (multa or "")
    return {
        "codigo": f"{normas[0]} {arts[0]} {apts[0]} {opc}",
        "norma": normas[0],
        "articulo": int(arts[0]),
        "apartado": None if apts[0] == "-" else apts[0],
        "opcion": opc,
        "lsv_articulo": int(arts[1]),
        "lsv_apartado": None if apts[1] == "-" else apts[1],
        "tipificacion": tip,
        "gravedad": GRAVEDAD[cal[0]],
        "importe_eur": nums[0] if nums else None,
        "pronto_pago_eur": None if sin_red or len(nums) < 2 else nums[1],
        "sin_reduccion": int(sin_red),
        "puntos": int(ptos) if ptos.isdigit() else None,
        "hecho_denunciado": _join(texto),
        "responsable": _join(resp),
        "observaciones": _join(coment),
        "materia": _join(materia),
        "abreviado": int((abrev or "").strip() == "Sí"),
        "pagina": pagina,
    }


def parse(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for r in table:
                    if len(r) != 12:
                        raise ValueError(f"pág. {i}: fila con {len(r)} columnas: {r}")
                    if r[0] != "NORMA" and (row := parse_row(r, i)):
                        yield row


def build(pdf_path, db_path):
    rows = list(parse(pdf_path))
    Path(db_path).unlink(missing_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute(SCHEMA)
        cols = ",".join(rows[0])
        db.executemany(
            f"INSERT INTO sanciones ({cols}) VALUES ({','.join('?' * len(rows[0]))})",
            [tuple(r.values()) for r in rows],
        )
    return len(rows)


if __name__ == "__main__":
    pdf, db = sys.argv[1:3] if len(sys.argv) == 3 else ("data/arci.pdf", "data/trafico.db")
    print(f"{build(pdf, db)} filas -> {db}")
