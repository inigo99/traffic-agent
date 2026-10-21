from fastapi.testclient import TestClient

from trafico_agent import web


class GrafoFalso:
    def invoke(self, estado):
        return {"respuesta": "Ver https://www.boe.es/x <b>", "comportamiento": "responder"}


def test_pagina_y_pregunta(monkeypatch):
    monkeypatch.setattr(web, "_grafo", lambda: GrafoFalso())
    monkeypatch.setattr(web, "_llm", lambda: None)
    web._responder.cache_clear()
    c = TestClient(web.app)
    assert "¿Es multa?" in c.get("/").text
    r = c.post("/preguntar", data={"pregunta": "iba sin cinturón"}).text
    assert '<a href="https://www.boe.es/x"' in r and "&lt;b&gt;" in r  # enlaces y texto escapado


def test_pregunta_demasiado_larga_se_rechaza(monkeypatch):
    monkeypatch.setattr(web, "_grafo", lambda: GrafoFalso())
    monkeypatch.setattr(web, "_llm", lambda: None)
    web._responder.cache_clear()
    r = TestClient(web.app).post("/preguntar", data={"pregunta": "x" * 501})
    assert r.status_code == 422
