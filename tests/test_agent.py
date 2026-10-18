from pathlib import Path

import pytest

from trafico_agent import agent, tools
from trafico_agent.agent import Analisis, Hechos

DB = Path(__file__).parents[1] / "data" / "trafico.db"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="falta data/trafico.db")

FRAG_CINTURON = {
    "norma": "CIR",
    "id_bloque": "a117",
    "articulo": "117",
    "apartado": "1",
    "titulo": "Artículo 117. Cinturones de seguridad.",
    "fragmento": "Es obligatorio el cinturón.",
    "url": "https://www.boe.es/buscar/act.php?id=BOE-A-2003-23514#a117",
}


@pytest.fixture(autouse=True)
def _sin_modelos(monkeypatch):
    monkeypatch.setattr(tools, "DB", str(DB))
    monkeypatch.setattr(tools, "buscar_normativa", lambda consulta: [FRAG_CINTURON])


def llm_falso(analisis, codigo=None, texto="El cinturón es obligatorio [1]."):
    def llamar(sistema, usuario, esquema=None):
        if esquema is Analisis:
            return analisis
        if esquema is not None and esquema.__name__ == "Eleccion":
            return esquema.model_construct(codigo=codigo)  # sin validar: simula un código inventado
        return texto(usuario) if callable(texto) else texto

    return llamar


def situacion(tema="otro", **hechos):
    return Analisis(intencion="situacion", tema=tema, consulta="x", hechos=Hechos(**hechos))


def test_velocidad_sale_del_anexo_iv_sin_elegir_con_el_llm():
    # los números los saca extraer_datos del texto, no el LLM (que aquí dice otra cosa)
    llm = llm_falso(situacion("velocidad", velocidad_kmh=99, limite_kmh=80))
    r = agent.preguntar("Un radar me cazó a 71 km/h en una calle limitada a 50", llm)
    assert (r["sancion"]["importe_eur"], r["sancion"]["puntos"]) == (300, 2)
    assert "300 € (150 € con pronto pago), 2 puntos" in r["respuesta"]


def test_pide_aclaracion_si_falta_el_limite():
    r = agent.preguntar(
        "me cazó un radar a 90", llm_falso(situacion("velocidad", velocidad_kmh=90))
    )
    assert r["comportamiento"] == "aclarar" and "límite" in r["respuesta"]


def test_ordenanza_no_busca_ni_responde():
    a = Analisis(intencion="fuera_ambito", motivo="ordenanza", consulta="x")
    r = agent.preguntar("zona azul en Pamplona", llm_falso(a))
    assert r["comportamiento"] == "rechazar" and "ordenanza" in r["respuesta"]


def test_situacion_con_fila_arci_y_cita():
    r = agent.preguntar("iba sin cinturón", llm_falso(situacion(), codigo="CIR 117 1 5E"))
    assert r["sancion"]["codigo"] == "CIR 117 1 5E"
    assert "multa de 200 € (100 € con pronto pago), 4 puntos" in r["respuesta"]
    assert r["fuentes"][0]["id_bloque"] == "a117" and tools.AVISO in r["respuesta"]


def test_codigo_inventado_por_el_llm_se_descarta():
    r = agent.preguntar("iba sin cinturón", llm_falso(situacion(), codigo="CIR 999 9 9Z"))
    assert r["sancion"] is None and "€" not in r["respuesta"]


def test_sin_citas_no_hay_respuesta():
    r = agent.preguntar(
        "algo", llm_falso(Analisis(intencion="factual", consulta="x"), texto="Sin citas.")
    )
    assert r["fuentes"] == [] and "No he encontrado" in r["respuesta"]


def test_aviso_penal():
    a = Analisis(intencion="situacion", motivo="penal", tema="otro", consulta="x")
    r = agent.preguntar("me negué a soplar", llm_falso(a))
    assert r["comportamiento"] == "avisar" and "delito" in r["respuesta"]


def test_metricas_de_la_evaluacion():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_agent", Path(__file__).parents[1] / "eval" / "run_agent.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    q = {
        "id": "S03",
        "comportamiento": "responder",
        "citas": [
            [
                {"norma": "CIR", "id_bloque": "a117", "apartado": "1"},
                {"norma": "LSV", "id_bloque": "a47", "apartado": None},
            ]
        ],
        "sancion": {
            "codigo": "CIR 117 1 5E",
            "gravedad": "grave",
            "importe_eur": 200,
            "pronto_pago_eur": 100,
            "puntos": 4,
        },
    }
    r = agent.preguntar("iba sin cinturón", llm_falso(situacion(), codigo="CIR 117 1 5E"))
    f = m.evaluar(q, r, 1.0)
    assert (f["ok_comportamiento"], f["ok_cita"], f["ok_sancion"], f["ok_codigo"]) == (
        True,
        True,
        True,
        True,
    )


@pytest.mark.parametrize(
    "texto, esperado",
    [
        (
            "Iba a 140 km/h por una autovía limitada a 120",
            {"tema": "velocidad", "velocidad_kmh": 140, "limite_kmh": 120},
        ),
        ("Me ha saltado un radar a 90 km/h", {"tema": "velocidad", "velocidad_kmh": 90}),
        (
            "He dado 0,30 mg/l. Tengo el carné desde hace diez años",
            {"tema": "alcohol", "tasa_aire_mg_l": 0.3, "conductor": "general"},
        ),
        (
            "Conduzco un autobús de 50 plazas, ¿qué tasa de alcohol puedo llevar?",
            {"tema": "alcohol", "conductor": "profesional", "vehiculo": "autobús"},
        ),
        ("Me negué a soplar en un control", {}),
        ("Me han parado por no llevar casco", {"tema": "casco"}),  # S60: falta el vehículo
        ("Iba en bici sin casco", {"tema": "casco", "vehiculo": "bici"}),
        ("Pasé por el telepeaje sin llevar el dispositivo", {}),  # S46: no es alcohol
    ],
)
def test_extraer_datos(texto, esperado):
    assert agent.extraer_datos(texto) == esperado


def test_alcohol_por_tramos_sin_llm():
    r = agent.preguntar(
        "He dado 0,30 mg/l en aire y tengo el carné desde hace diez años",
        llm_falso(situacion(), codigo="CIR 999"),
    )
    assert r["sancion"]["codigo"] == "CIR 020 1 5E"


def test_las_cifras_del_llm_no_llegan_a_la_respuesta():
    texto = "El cinturón es obligatorio [1]. La multa es de 1.000 euros y 8 puntos [1]."
    r = agent.preguntar(
        "iba sin cinturón", llm_falso(situacion(), codigo="CIR 117 1 5E", texto=texto)
    )
    assert "1.000" not in r["respuesta"] and "8 puntos" not in r["respuesta"]
    assert "multa de 200 €" in r["respuesta"]


def test_tema_y_vehiculo_no_salen_del_llm():
    """El LLM supone tema y vehículo (S46, S60): mandan las reglas."""
    a = Analisis(
        intencion="situacion", tema="alcohol", consulta="x", hechos=Hechos(vehiculo="moto")
    )
    r = agent.analizar({"pregunta": "Me han parado por no llevar casco"}, lambda *_: a)
    assert r["analisis"].tema == "casco"
    assert r["faltan"] == ["vehiculo"]


def test_eleccion_limitada_a_los_candidatos():
    esquema = agent._esquema_eleccion(["CIR 117 1 5E", "CIR 117 1 5F"])
    assert esquema.model_json_schema()["properties"]["codigo"]["anyOf"][0]["enum"] == [
        "CIR 117 1 5E",
        "CIR 117 1 5F",
    ]


def test_sin_citas_pero_con_sancion_responde_con_su_articulo():
    r = agent.preguntar(
        "iba sin cinturón", llm_falso(situacion(), codigo="CIR 117 1 5E", texto="Sin citas.")
    )
    assert r["sancion"]["codigo"] == "CIR 117 1 5E" and r["fuentes"][0]["id_bloque"] == "a117"
