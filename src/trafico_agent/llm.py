"""Cliente mínimo de LLM: `llm(sistema, usuario, esquema=None)` -> objeto Pydantic o texto.

Una función por proveedor; el agente solo conoce esta firma (así se cambia de modelo sin tocarlo).
"""

import os

TIMEOUT_S = 180
MAX_TOKENS = 1024  # corta la generación si el modelo se embucla


def ollama(modelo=None, host=None):
    import ollama as _ollama

    modelo = modelo or os.environ.get("TRAFICO_MODELO", "qwen2.5:7b")
    # timeout: con salida JSON el modelo a veces entra en bucle (espacios sin fin) y no vuelve nunca
    cliente = _ollama.Client(host=host or os.environ.get("OLLAMA_HOST"), timeout=TIMEOUT_S)

    def llamar(sistema, usuario, esquema=None):
        r = cliente.chat(
            model=modelo,
            messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
            format=esquema.model_json_schema() if esquema else None,
            options={"temperature": 0, "num_predict": MAX_TOKENS},
        )
        texto = r.message.content
        return esquema.model_validate_json(texto) if esquema else texto

    llamar.nombre = f"ollama:{modelo}"
    return llamar
