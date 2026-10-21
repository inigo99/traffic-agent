import json

from trafico_agent import watch


def test_cambios_detecta_modificados_nuevos_y_eliminados():
    antes = {"CIR": {"a1": "20200101", "a2": "20200101", "a3": "20200101"}}
    ahora = {"CIR": {"a1": "20200101", "a2": "20261001", "a4": "20261001"}, "LSV": {}}
    assert watch.cambios(antes, ahora) == {"CIR": ["a2", "a4", "a3 (eliminado)"]}


def test_main_con_fixture_del_indice(tmp_path, monkeypatch):
    indice = (watch.RAIZ / "tests/fixtures/boe/indice.json").read_bytes()
    monkeypatch.setattr(watch, "VERSIONES", tmp_path / "versiones.json")
    monkeypatch.setattr(watch, "CHANGELOG", tmp_path / "CHANGELOG.md")
    fetch = lambda url, accept: indice
    assert watch.main([], fetch) == watch.HAY_CAMBIOS  # sin versiones guardadas: todo es nuevo
    assert watch.main(["--guardar"], fetch) == 0
    assert watch.main([], fetch) == 0  # ya al día
    guardado = json.loads((tmp_path / "versiones.json").read_text(encoding="utf-8"))
    assert guardado["LSV"]["a14"]
