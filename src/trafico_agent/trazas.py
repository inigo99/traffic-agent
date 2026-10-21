"""Trazas en Phoenix (OpenTelemetry + OpenInference): un span por nodo del grafo y otro por
llamada al LLM, con modelo, prompt, respuesta, tokens y latencia.

    uv run --extra obs phoenix serve          # panel en http://localhost:6006
    TRAFICO_TRAZAS=1 uv run --extra obs python eval/run_agent.py --n 5

Sin el extra `obs` o sin TRAFICO_TRAZAS no se activa nada (los spans de `llm.py` son no-op).
"""

import os


def activar(proyecto="trafico-agent"):
    """Registra el exportador hacia Phoenix e instrumenta LangChain/LangGraph."""
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import register

    proveedor = register(project_name=proyecto, verbose=False)
    LangChainInstrumentor().instrument(tracer_provider=proveedor)
    return proveedor


def activar_si_procede():
    return activar() if os.environ.get("TRAFICO_TRAZAS") else None
