from trafico_agent.ingest.postproceso import estado_apartado, trocear

ART = "Artículo 14. Carga.\n1. La carga no podrá:\na) Arrastrar.\nb) Caer.\n2. El transporte se cubrirá."


def test_estado_apartado():
    assert estado_apartado(ART, None) == "sin_apartado"
    assert estado_apartado(ART, "2") == "ok"
    assert estado_apartado(ART, "1-B") == "ok"
    assert estado_apartado(ART, "2-A") == "letra_no_encontrada"  # la a) es del apartado 1
    assert estado_apartado(ART, "3") == "apartado_no_encontrado"
    assert estado_apartado("Artículo 2. Usuarios.\nLos usuarios...", "1") == "apartado_implicito"


def test_trocear():
    assert trocear(ART) == [(None, ART)]
    trozos = trocear(ART, max_chars=40)
    assert [ap for ap, _ in trozos] == ["1", "1", "2"]  # el apartado 1 no cabe y se parte
    assert all(t.startswith("Artículo 14. Carga.\n") for _, t in trozos)
    assert "\n".join(t.split("\n", 1)[1] for _, t in trozos) == ART.split("\n", 1)[1]
