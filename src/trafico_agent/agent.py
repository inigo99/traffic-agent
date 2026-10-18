"""Agente "¿es multa?" en LangGraph.

    analizar ─┬─ fuera de ámbito ──────────────────────────────► fuera ──► fin
              ├─ situación con datos clave sin dar ────────────► aclarar ► fin
              └─ resto ► buscar ─┬─ situación ► sancion ─► redactar ► fin
                                 └─ factual ──────────────► redactar ► fin

Solo `analizar`, la elección de la fila ARCI (en `sancion`) y `redactar` llaman al LLM.
Importes y puntos salen de `tools` (SQL); el LLM nunca los escribe: se añaden al final.
"""

import os
import re
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from trafico_agent import tools
from trafico_agent.index import tokenizar

# 8 por parecido + filas de los artículos recuperados: la fila correcta está en 47/54 situaciones
# (eval/run_candidatos.py); antes, con 12 por parecido y tope 12, las de artículos no entraban nunca.
VEC_CANDIDATOS = 8
MAX_CANDIDATOS = 30
ELECCION = os.environ.get("TRAFICO_ELECCION", "llm")  # llm | vector
MAX_CHARS_FRAGMENTO = 1500

# Datos sin los que no se puede dar una sanción concreta, por tema.
REQUISITOS = {
    "velocidad": ["velocidad_kmh", "limite_kmh"],
    "alcohol": ["tasa", "conductor"],
    "casco": ["vehiculo"],
}
PREGUNTAS_FALTA = {
    "velocidad_kmh": "¿a qué velocidad ibas exactamente?",
    "limite_kmh": "¿cuál era el límite de velocidad de la vía (o qué tipo de vía era)?",
    "tasa": "¿qué tasa dio el control (en aire espirado, mg/l, o en sangre, g/l)?",
    "conductor": "¿eres conductor novel (menos de dos años), profesional o conductor general?",
    "vehiculo": "¿en qué vehículo ibas (bicicleta, moto, ciclomotor, patinete…)?",
}
AVISO_PENAL = (
    "Atención: esta conducta puede constituir un delito contra la seguridad vial (Código Penal), "
    "además de una infracción administrativa. Consulta con un abogado."
)
RESPUESTA_FUERA = {
    "ordenanza": (
        "Esto depende de la ordenanza municipal de cada ayuntamiento (zonas de estacionamiento "
        "regulado, grúa, carga y descarga, zonas de bajas emisiones, patinetes…), que no está en "
        "mi corpus. Consulta la ordenanza o la web de tu ayuntamiento."
    ),
    "fuera_ambito": (
        "Esa pregunta queda fuera de lo que cubro: solo respondo sobre la Ley de Tráfico "
        "(RDL 6/2015) y el Reglamento General de Circulación, con su guía de sanciones. "
        "No trato permisos, ITV, seguros ni redacto recursos, ni puedo consultar tus datos."
    ),
}


class Hechos(BaseModel):
    velocidad_kmh: int | None = None
    limite_kmh: int | None = None
    tipo_via: Literal["urbana", "interurbana", "autopista_autovia"] | None = None
    tasa_aire_mg_l: float | None = None
    tasa_sangre_g_l: float | None = None
    conductor: Literal["general", "novel", "profesional", "menor"] | None = None
    vehiculo: str | None = Field(None, max_length=40)


class Analisis(BaseModel):
    intencion: Literal["factual", "situacion", "fuera_ambito"]
    motivo: Literal["ninguno", "ordenanza", "fuera_ambito", "penal"] = "ninguno"
    tema: Literal["velocidad", "alcohol", "casco", "otro"] = "otro"
    # max_length: sin tope, qwen a veces repite texto en bucle hasta cortar el JSON (S49)
    consulta: str = Field(
        description="La pregunta reformulada con términos de la norma", max_length=300
    )
    hechos: Hechos = Hechos()


class Eleccion(BaseModel):
    codigo: str | None = Field(description="Código ARCI elegido, o null si ninguno encaja")


class Estado(TypedDict, total=False):
    pregunta: str
    analisis: Analisis
    faltan: list[str]
    fragmentos: list[dict]
    sancion: dict | None
    candidatos: list[str]
    respuesta: str
    comportamiento: str
    fuentes: list[dict]


SISTEMA_ANALISIS = """Analizas preguntas sobre tráfico en España. Devuelve JSON.
- intencion: "situacion" si el usuario describe algo que ha hecho o le ha pasado y pregunta si es multa o qué le cae; "factual" si pregunta qué dice la norma; "fuera_ambito" si depende de una ordenanza municipal (zona azul/ORA, grúa municipal, zonas de bajas emisiones de una ciudad, carga y descarga en una ciudad concreta) o trata de permisos, ITV, seguros, tasas, redactar recursos o datos personales del usuario.
- motivo: "ordenanza" o "fuera_ambito" si intencion es fuera_ambito; "penal" si la conducta puede ser delito (alcohol muy alto, negarse a la prueba, velocidad muy excesiva, conducir sin carné o con él retirado, huir tras un accidente, carreras o conducción temeraria); si no, "ninguno".
- tema: "velocidad", "alcohol", "casco" u "otro".
- consulta: la pregunta reescrita con el vocabulario del Reglamento General de Circulación.
- hechos: solo los datos que el usuario da explícitamente; si no los da, null. No supongas nada."""

SISTEMA_ELECCION = """Eliges qué infracción de la guía de la DGT corresponde a la situación descrita.
Devuelve JSON con el código exacto de una de las opciones, o null si ninguna encaja. No inventes códigos."""

SISTEMA_REDACCION = """Eres un asistente de normativa de tráfico española. Responde en español, en 2-5 frases, usando solo los fragmentos numerados.
- Pon la cita [n] del fragmento detrás de cada afirmación normativa. Sin cita, no afirmes nada.
- No escribas importes en euros ni puntos: el sistema los añade después a partir de la tabla oficial.
- Si los fragmentos no responden a la pregunta, dilo.
- Si la pregunta parte de un dato falso, corrígelo citando el fragmento."""


_VEHICULOS = r"bici(?:cleta)?|moto(?:cicleta)?|ciclomotor|patinete|quad|coche|turismo|furgoneta|cami[oó]n|autob[uú]s"
_NO_VELOCIDAD = r"(?!\s*(?:años|plazas|toneladas|kg|kilos|metros|minutos|euros|€|puntos|mg|g/))"


def extraer_datos(texto):
    """Datos numéricos y de conductor, por reglas: el LLM no los inventa (S3: con el LLM salían
    límites que el usuario no había dado)."""
    t = texto.lower()
    d = {}
    if re.search(r"km/?h|radar|velocidad|kilómetros por hora|cinemómetro", t):
        nums = [int(n) for n in re.findall(rf"\b(\d{{2,3}})\b{_NO_VELOCIDAD}", t)]
        nums = [n for n in nums if 10 <= n <= 300]
        if nums:
            d["tema"], d["velocidad_kmh"] = "velocidad", max(nums)
            if len(nums) > 1:
                d["limite_kmh"] = min(nums)
    tasa = re.search(r"(\d+[,.]\d+)\s*(mg|miligramos|g/|gramos)", t)
    negativa = re.search(r"negu[eé]|negarme|no (?:quise|quiero) soplar", t)  # otra infracción
    if not negativa and (tasa or re.search(r"alcohol|soplar|\bpositivo", t)):
        d["tema"] = "alcohol"
        if tasa:
            valor = float(tasa.group(1).replace(",", "."))
            d["tasa_aire_mg_l" if tasa.group(2).startswith("m") else "tasa_sangre_g_l"] = valor
    if re.search(r"novel|menos de (?:dos|2) años|me (?:lo )?saqué hace (?:un|1) año", t):
        d["conductor"] = "novel"
    elif re.search(r"camion|autob[uú]s|taxi|profesional|ambulancia|mercanc[ií]as peligrosas", t):
        d["conductor"] = "profesional"
    elif m := re.search(r"desde hace (\w+) años", t):
        d["conductor"] = "novel" if m.group(1) in ("un", "1", "dos", "2") else "general"
    if re.search(r"\bcasco\b", t):
        d["tema"] = "casco"
    if m := re.search(rf"\b({_VEHICULOS})\b", t):
        d["vehiculo"] = m.group(1)
    return d


def analizar(estado, llm):
    a = llm(SISTEMA_ANALISIS, estado["pregunta"], Analisis)
    d = extraer_datos(estado["pregunta"])
    # Números, vehículo y tema salen de reglas: el LLM los suponía (S60: casco -> "moto";
    # S46: telepeaje -> alcohol) y entonces no se pedía el dato que falta.
    por_reglas = ("velocidad_kmh", "limite_kmh", "tasa_aire_mg_l", "tasa_sangre_g_l", "vehiculo")
    hechos = a.hechos.model_dump() | dict.fromkeys(por_reglas) | d
    a.hechos = Hechos(**{k: v for k, v in hechos.items() if k in Hechos.model_fields})
    a.tema = d.get("tema", "otro")
    if _penal(a.hechos):
        a.motivo = "penal"
    h = a.hechos
    datos = {
        "velocidad_kmh": h.velocidad_kmh,
        "limite_kmh": h.limite_kmh,
        "tasa": h.tasa_aire_mg_l or h.tasa_sangre_g_l,
        "conductor": h.conductor,
        "vehiculo": h.vehiculo,
    }
    faltan = (
        [c for c in REQUISITOS.get(a.tema, []) if datos[c] is None]
        if a.intencion == "situacion"
        else []
    )
    return {"analisis": a, "faltan": faltan}


def _penal(h):
    """Umbrales del art. 379 del Código Penal (solo para avisar, no se analiza el delito)."""
    if (h.tasa_aire_mg_l or 0) > 0.60 or (h.tasa_sangre_g_l or 0) > 1.2:
        return True
    if h.velocidad_kmh and h.limite_kmh:
        exceso = h.velocidad_kmh - h.limite_kmh
        return exceso > (60 if h.limite_kmh <= 50 else 80)
    return False


def ruta(estado):
    a = estado["analisis"]
    if a.intencion == "fuera_ambito":
        return "fuera"
    return "aclarar" if estado["faltan"] else "buscar"


def fuera(estado):
    motivo = estado["analisis"].motivo
    texto = RESPUESTA_FUERA.get(motivo, RESPUESTA_FUERA["fuera_ambito"])
    return {"respuesta": texto, "comportamiento": "rechazar", "fuentes": [], "sancion": None}


def aclarar(estado):
    preguntas = " ".join(PREGUNTAS_FALTA[c] for c in estado["faltan"])
    texto = f"Para decirte qué sanción corresponde necesito un dato más: {preguntas}"
    return {"respuesta": texto, "comportamiento": "aclarar", "fuentes": [], "sancion": None}


def buscar(estado):
    a = estado["analisis"]
    return {"fragmentos": tools.buscar_normativa(f"{estado['pregunta']}\n{a.consulta}")}


def sancion(estado, llm):
    a = estado["analisis"]
    h = a.hechos
    if a.tema == "velocidad" and h.velocidad_kmh and h.limite_kmh:  # Anexo IV: sin LLM
        v = tools.consultar_velocidad(h.limite_kmh, h.velocidad_kmh)
        if v is None:
            return {"sancion": None}
        return {
            "sancion": {
                "codigo": None,
                "gravedad": v["gravedad"],
                "importe_eur": v["multa_eur"],
                "pronto_pago_eur": v["pronto_pago_eur"],
                "puntos": v["puntos"],
                "hecho_denunciado": f"Circular a {h.velocidad_kmh} km/h con límite de {h.limite_kmh} km/h",
                "aviso": None,
                "fuente": "Anexo IV de la LSV",
            }
        }
    if a.tema == "alcohol" and (codigo := _codigo_alcohol(h)):  # tramos del art. 20 RGC: sin LLM
        return {"sancion": tools.consultar_sancion(codigo)}
    bloques = [(f["norma"], f["id_bloque"]) for f in estado["fragmentos"]]
    candidatos = _candidatos(estado["pregunta"], a.consulta, bloques)
    if not candidatos:
        return {"sancion": None}
    opciones = "\n".join(f"- {c['codigo']}: {c['hecho_denunciado'][:200]}" for c in candidatos)
    hechos = h.model_dump(exclude_none=True)
    usuario = f"Situación: {estado['pregunta']}\nDatos: {hechos}\n\nOpciones:\n{opciones}"
    if ELECCION == "vector":  # la más parecida, sin LLM (para comparar en la evaluación)
        codigo = candidatos[0]["codigo"]
    else:
        codigo = llm(SISTEMA_ELECCION, usuario, Eleccion).codigo
    elegida = next((c for c in candidatos if c["codigo"] == codigo), None)
    return {"sancion": elegida, "candidatos": [c["codigo"] for c in candidatos]}


def _codigo_alcohol(h):
    """Fila ARCI del art. 20 RGC según tasa y tipo de conductor."""
    estricto = h.conductor in ("novel", "profesional")
    if h.tasa_aire_mg_l is not None:
        bajo, alto = (0.15, 0.30) if estricto else (0.25, 0.50)
        if h.tasa_aire_mg_l > alto:
            return "CIR 020 1 5K" if estricto else "CIR 020 1 5I"
        if h.tasa_aire_mg_l > bajo:
            return "CIR 020 1 5G" if estricto else "CIR 020 1 5E"
    if h.tasa_sangre_g_l is not None and not estricto and h.tasa_sangre_g_l > 0.5:
        return "CIR 020 1 5F"
    return None


def _candidatos(pregunta, consulta, bloques):
    """Filas ARCI parecidas por vectores (hechos) más las de los artículos recuperados."""
    parecidas = tools.sanciones_parecidas(f"{pregunta}\n{consulta}", VEC_CANDIDATOS)
    vistos = {c["codigo"] for c in parecidas}
    resto = [c for c in tools.sanciones_de_articulos(bloques) if c["codigo"] not in vistos]
    q = set(tokenizar(pregunta))
    resto.sort(key=lambda c: -len(q & set(tokenizar(c["hecho_denunciado"]))))
    return (parecidas + resto)[:MAX_CANDIDATOS]


def redactar(estado, llm):
    frags = estado["fragmentos"]
    contexto = "\n\n".join(
        f"[{i}] {f['titulo']} ({f['norma']})\n{f['fragmento'][:MAX_CHARS_FRAGMENTO]}"
        for i, f in enumerate(frags, 1)
    )
    s = estado.get("sancion")
    extra = f"\n\nInfracción identificada: {s['hecho_denunciado'][:200]}" if s else ""
    usuario = f"Pregunta: {estado['pregunta']}{extra}\n\nFragmentos:\n{contexto}"
    texto = llm(SISTEMA_REDACCION, usuario)
    usados = _citas(texto, len(frags))
    if not usados:  # un reintento; si sigue sin citar, no se responde
        texto = llm(SISTEMA_REDACCION + "\nOBLIGATORIO: incluye al menos una cita [n].", usuario)
        usados = _citas(texto, len(frags))
    if not usados:
        texto, s = (
            "No he encontrado en la normativa un artículo que responda a esto con seguridad.",
            None,
        )
    orden = sorted(usados)
    texto = re.sub(r"\[(\d+)\]", lambda m: _renumerar(m, orden), _sin_cifras(texto))
    texto = re.sub(r"^(?:\s*\[\d+\])+\s*(?:\d+\.\s+)?", "", texto)  # citas sueltas al inicio
    if s and not re.search(r"[a-záéíóúñ]{3}", texto, re.IGNORECASE):  # solo quedaban cifras
        texto = "La situación que describes corresponde a la infracción indicada abajo."
    fuentes = [frags[i - 1] for i in orden]
    if s and (p := _precepto(s)) and all(f["id_bloque"] != p["id_bloque"] for f in fuentes):
        fuentes.append(p)
    a = estado["analisis"]
    avisos = [x for x in (AVISO_PENAL if a.motivo == "penal" else None, s and s.get("aviso")) if x]
    comportamiento = "avisar" if avisos else "responder"
    return {
        "respuesta": _componer(texto, s, avisos, fuentes),
        "comportamiento": comportamiento,
        "fuentes": [{k: f[k] for k in ("norma", "id_bloque", "articulo", "url")} for f in fuentes],
        "sancion": s,
    }


_CIFRAS = re.compile(r"[^.\n]*(?:€|\beuros?\b|\d+\s*puntos?\b)[^.\n]*\.?\s*", re.IGNORECASE)


def _sin_cifras(texto):
    """Quita las frases del LLM con importes o puntos: esas cifras solo las pone `_componer`."""
    return _CIFRAS.sub("", texto).strip() or texto


def _renumerar(m, orden):
    n = int(m.group(1))
    return f"[{orden.index(n) + 1}]" if n in orden else ""


def _precepto(s):
    """Artículo que la guía ARCI cita para la sanción elegida (base legal de la cuantía)."""
    a = tools.leer_articulo(s["norma"], s["id_bloque"]) if s.get("id_bloque") else None
    return a and {
        "norma": a["norma"],
        "id_bloque": a["id_bloque"],
        "articulo": a["articulo"],
        "titulo": a["titulo"],
        "url": a["url"],
    }


def _citas(texto, n):
    return {int(m) for m in re.findall(r"\[(\d+)\]", texto) if 1 <= int(m) <= n}


def _euros(x):
    return f"{x:g} €".replace(".", ",")


def _componer(texto, s, avisos, fuentes):
    partes = [texto.strip()]
    if s:
        linea = f"Sanción: infracción {s['gravedad'].replace('_', ' ')}"
        if s["importe_eur"] is not None:
            linea += f", multa de {_euros(s['importe_eur'])}"
            if s.get("pronto_pago_eur"):
                linea += f" ({_euros(s['pronto_pago_eur'])} con pronto pago)"
            elif s.get("sin_reduccion"):
                linea += " (sin reducción por pronto pago)"
        if s["puntos"] is not None:
            linea += f", {s['puntos']} puntos"
        origen = f"guía ARCI de la DGT, {s['codigo']}" if s.get("codigo") else s.get("fuente", "")
        partes.append(f"{linea}. Fuente: {origen}.")
    partes += avisos
    if fuentes:
        partes.append(
            "Fuentes:\n"
            + "\n".join(
                f"[{i}] {f['norma']} {f['titulo']} — {f['url']}" for i, f in enumerate(fuentes, 1)
            )
        )
    partes.append(tools.AVISO)
    return "\n\n".join(partes)


def construir(llm):
    g = StateGraph(Estado)
    g.add_node("analizar", lambda e: analizar(e, llm))
    g.add_node("fuera", fuera)
    g.add_node("aclarar", aclarar)
    g.add_node("buscar", buscar)
    g.add_node("sancion", lambda e: sancion(e, llm))
    g.add_node("redactar", lambda e: redactar(e, llm))
    g.add_edge(START, "analizar")
    g.add_conditional_edges("analizar", ruta, ["fuera", "aclarar", "buscar"])
    g.add_conditional_edges(
        "buscar",
        lambda e: "sancion" if e["analisis"].intencion == "situacion" else "redactar",
        ["sancion", "redactar"],
    )
    g.add_edge("sancion", "redactar")
    for nodo in ("fuera", "aclarar", "redactar"):
        g.add_edge(nodo, END)
    return g.compile()


def preguntar(pregunta, llm=None):
    from trafico_agent.llm import ollama

    return construir(llm or ollama()).invoke({"pregunta": pregunta})


if __name__ == "__main__":
    import sys

    print(preguntar(" ".join(sys.argv[1:]))["respuesta"])
