"""Cliente mínimo de LLM: `llm(sistema, usuario, esquema=None)` -> objeto Pydantic o texto.

Una función por proveedor; el agente solo conoce esta firma (así se cambia de modelo sin tocarlo).
"""

import hashlib
import json
import os
import re
import time
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


def api(modelo=None):
    """Modelo grande por una API compatible con OpenAI (demo ligera: la web no carga modelos).
    Por defecto Groq (capa gratis); vale cualquier otra con TRAFICO_API_URL (p. ej. el router de
    Hugging Face, https://router.huggingface.co/v1). Clave en TRAFICO_API_KEY."""
    import httpx

    base = os.environ.get("TRAFICO_API_URL", "https://api.groq.com/openai/v1").rstrip("/")
    modelo = modelo or os.environ.get("TRAFICO_API_MODELO", "openai/gpt-oss-120b")
    http = httpx.Client(
        timeout=TIMEOUT_S, headers={"Authorization": f"Bearer {os.environ['TRAFICO_API_KEY']}"}
    )
    modo = {"json": "json_schema"}  # pasa a json_object si el modelo no acepta esquemas

    def _cuerpo(sistema, usuario, esquema):
        # más margen que en local: los modelos con razonamiento (qwen3, gpt-oss) gastan tokens pensando
        cuerpo = {"model": modelo, "temperature": 0, "max_tokens": 4096}
        if esquema and modo["json"] == "json_schema":
            cuerpo["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": esquema.__name__, "schema": esquema.model_json_schema()},
            }
        elif esquema:
            cuerpo["response_format"] = {"type": "json_object"}
            sistema += "\nResponde solo con un JSON que cumpla este esquema:\n" + json.dumps(
                esquema.model_json_schema(), ensure_ascii=False
            )
        cuerpo["messages"] = [
            {"role": "system", "content": sistema},
            {"role": "user", "content": usuario},
        ]
        return cuerpo

    def llamar(sistema, usuario, esquema=None):
        with _tracer.start_as_current_span(f"api {esquema.__name__ if esquema else 'texto'}") as sp:
            sp.set_attributes({"openinference.span.kind": "LLM", "llm.model_name": modelo})
            for _ in range(5):
                r = http.post(f"{base}/chat/completions", json=_cuerpo(sistema, usuario, esquema))
                if r.status_code == 429:  # capa gratis: límite de tokens por minuto
                    time.sleep(float(r.headers.get("retry-after", 10)))
                elif r.status_code == 400 and esquema and modo["json"] == "json_schema":
                    modo["json"] = "json_object"
                else:
                    break
            if (
                r.is_error
            ):  # con el cuerpo: "model not found", límites... (raise_for_status no lo da)
                raise RuntimeError(f"{r.status_code} de {base}: {r.text[:500]}")
            datos = r.json()
            texto = re.sub(
                r"<think>.*?</think>",
                "",
                datos["choices"][0]["message"]["content"] or "",
                flags=re.DOTALL,
            )
            uso = datos.get("usage") or {}
            sp.set_attributes(
                {
                    "llm.token_count.prompt": uso.get("prompt_tokens", 0),
                    "llm.token_count.completion": uso.get("completion_tokens", 0),
                }
            )
        return esquema.model_validate_json(_solo_json(texto)) if esquema else texto

    llamar.nombre = f"api:{modelo}"
    return llamar


def _solo_json(texto):
    """Algunos proveedores ignoran el esquema y envuelven el JSON en ```json ... ```."""
    i, j = texto.find("{"), texto.rfind("}")
    return texto[i : j + 1] if i >= 0 and j > i else texto


def desde_entorno():
    """TRAFICO_LLM=ollama (por defecto, con TRAFICO_MODELO) o api (demo publicada)."""
    return api() if os.environ.get("TRAFICO_LLM") == "api" else ollama()


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
