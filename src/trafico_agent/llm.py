"""Cliente mínimo de LLM: `llm(sistema, usuario, esquema=None)` -> objeto Pydantic o texto.

Una función por proveedor; el agente solo conoce esta firma (así se cambia de modelo sin tocarlo).
"""

import hashlib
import json
import os
from pathlib import Path

from opentelemetry import trace

TIMEOUT_S = 180
MAX_TOKENS = 1024  # corta la generación si el modelo se embucla
_tracer = trace.get_tracer("trafico_agent.llm")


def ollama(modelo=None, host=None):
    import ollama as _ollama

    modelo = modelo or os.environ.get("TRAFICO_MODELO", "qwen2.5:7b")
    # timeout: con salida JSON el modelo a veces entra en bucle (espacios sin fin) y no vuelve nunca
    cliente = _ollama.Client(host=host or os.environ.get("OLLAMA_HOST"), timeout=TIMEOUT_S)

    def llamar(sistema, usuario, esquema=None):
        # Span con atributos OpenInference: Phoenix lo muestra como llamada LLM (no-op sin trazas)
        with _tracer.start_as_current_span(
            f"ollama {esquema.__name__ if esquema else 'texto'}"
        ) as sp:
            sp.set_attributes(
                {
                    "openinference.span.kind": "LLM",
                    "llm.model_name": modelo,
                    "input.value": f"{sistema}\n\n{usuario}",
                }
            )
            r = cliente.chat(
                model=modelo,
                messages=[
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": usuario},
                ],
                format=esquema.model_json_schema() if esquema else None,
                options={"temperature": 0, "num_predict": MAX_TOKENS},
            )
            texto = r.message.content
            sp.set_attributes(
                {
                    "output.value": texto,
                    "llm.token_count.prompt": r.prompt_eval_count or 0,
                    "llm.token_count.completion": r.eval_count or 0,
                }
            )
        return esquema.model_validate_json(texto) if esquema else texto

    llamar.nombre = f"ollama:{modelo}"
    return llamar


class Pendiente(Exception):
    """La llamada no tiene respuesta todavía en el fichero de `cola`."""


def cola(nombre, carpeta="eval/cola"):
    """LLM sin API: lee las respuestas de `<carpeta>/<nombre>.json` y apunta en
    `<carpeta>/<nombre>.pendientes.jsonl` las llamadas que aún no tienen (y lanza Pendiente).

    Sirve para evaluar un modelo al que solo se llega a mano (p. ej. Haiku desde el chat):
    se ejecuta la evaluación, se contestan las pendientes y se repite hasta que no quede ninguna.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    respuestas_f = carpeta / f"{nombre}.json"
    pendientes_f = carpeta / f"{nombre}.pendientes.jsonl"
    respuestas = (
        json.loads(respuestas_f.read_text(encoding="utf-8")) if respuestas_f.exists() else {}
    )
    pendientes_f.write_text("", encoding="utf-8")
    vistos = set()

    def llamar(sistema, usuario, esquema=None):
        schema = esquema.model_json_schema() if esquema else None
        clave = hashlib.sha1(
            json.dumps([sistema, usuario, schema], ensure_ascii=False).encode()
        ).hexdigest()[:16]
        if clave not in respuestas:
            if clave not in vistos:
                vistos.add(clave)
                fila = {"clave": clave, "sistema": sistema, "usuario": usuario, "esquema": schema}
                with pendientes_f.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            raise Pendiente(clave)
        texto = respuestas[clave]
        return esquema.model_validate_json(texto) if esquema else texto

    llamar.nombre = f"cola:{nombre}"
    llamar.pendientes = lambda: len(vistos)
    return llamar
