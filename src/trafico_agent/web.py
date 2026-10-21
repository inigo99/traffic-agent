"""Demo web: FastAPI + HTMX sobre el agente.

uv run --extra ml --extra demo uvicorn trafico_agent.web:app        # http://localhost:8000
TRAFICO_LLM=llamacpp ...                                            # como en HF Spaces
"""

import html
import re
import threading
import time
from functools import cache

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from trafico_agent import agent, tools
from trafico_agent.llm import desde_entorno

MAX_PREGUNTA = 500
REPO = "https://github.com/inigo99/trafico-agent"
EJEMPLOS = [
    "Iba a 140 km/h por una autovía limitada a 120. ¿Qué multa me cae?",
    "He dado 0,30 mg/l en un control. Tengo el carné desde hace diez años. ¿Qué me cae?",
    "Iba sin cinturón y me ha parado la Guardia Civil. ¿Cuánto es la multa?",
    "¿A qué distancia mínima hay que adelantar a un ciclista?",
    "Aparqué en zona azul sin ticket en Pamplona. ¿Qué multa es?",
]
_turno = threading.Lock()  # ponytail: una pregunta a la vez (CPU de 2 núcleos); cola si hay tráfico

app = FastAPI(title="trafico-agent")


@cache
def _grafo():
    return agent.construir(desde_entorno())


def _html_respuesta(texto):
    t = html.escape(texto)
    return re.sub(r"(https://[^\s<]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', t)


@app.get("/", response_class=HTMLResponse)
def inicio():
    ejemplos = "".join(
        f'<button type="button" class="ej" onclick="usar(this)">{html.escape(e)}</button>'
        for e in EJEMPLOS
    )
    return PAGINA.format(
        ejemplos=ejemplos, aviso=html.escape(tools.AVISO), repo=REPO, max=MAX_PREGUNTA
    )


@app.post("/preguntar", response_class=HTMLResponse)
def preguntar(pregunta: str = Form(..., max_length=MAX_PREGUNTA)):
    pregunta = pregunta.strip()
    if not pregunta:
        return '<p class="error">Escribe una pregunta.</p>'
    with _turno:
        t0 = time.perf_counter()
        try:
            r = _grafo().invoke({"pregunta": pregunta})
        except Exception:  # noqa: BLE001 — el usuario ve un mensaje, no la traza
            return (
                '<p class="error">No he podido responder (fallo del modelo). Prueba otra vez.</p>'
            )
        segundos = time.perf_counter() - t0
    return (
        f'<div class="respuesta">{_html_respuesta(r["respuesta"])}</div>'
        f'<p class="meta">{r.get("comportamiento", "")} · {segundos:.0f} s</p>'
    )


@app.get("/salud")
def salud():
    return {"ok": True, "versiones": tools.version_normativa()}


PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>¿Es multa? · trafico-agent</title>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<style>
:root {{ --fondo:#fafaf9; --texto:#1c1917; --suave:#78716c; --borde:#e7e5e4; --acento:#b45309; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fondo:#1c1917; --texto:#f5f5f4; --suave:#a8a29e; --borde:#44403c; --acento:#f59e0b; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--fondo); color:var(--texto); font:16px/1.55 system-ui,sans-serif; }}
main {{ max-width:720px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ margin:0 0 4px; font-size:1.6rem; }}
.sub {{ color:var(--suave); margin:0 0 24px; }}
textarea {{ width:100%; min-height:90px; padding:12px; font:inherit; color:inherit; background:transparent;
  border:1px solid var(--borde); border-radius:8px; resize:vertical; }}
button[type=submit] {{ margin-top:8px; padding:10px 18px; font:inherit; font-weight:600; color:#fff;
  background:var(--acento); border:0; border-radius:8px; cursor:pointer; }}
.ejemplos {{ display:flex; flex-wrap:wrap; gap:6px; margin:12px 0 24px; }}
.ej {{ padding:6px 10px; font:inherit; font-size:.85rem; color:inherit; background:transparent;
  border:1px solid var(--borde); border-radius:999px; cursor:pointer; text-align:left; }}
.respuesta {{ white-space:pre-wrap; border-left:3px solid var(--acento); padding:4px 0 4px 14px; }}
.respuesta a {{ color:var(--acento); word-break:break-all; }}
.meta, .pie {{ color:var(--suave); font-size:.85rem; }}
.error {{ color:#dc2626; }}
.htmx-indicator {{ display:none; color:var(--suave); }}
.htmx-request .htmx-indicator, .htmx-request.htmx-indicator {{ display:block; }}
</style></head>
<body><main>
<h1>¿Es multa?</h1>
<p class="sub">Normativa estatal de tráfico (Ley de Tráfico y Reglamento General de Circulación) con el artículo exacto del BOE y la sanción de la guía de la DGT.</p>
<form hx-post="/preguntar" hx-target="#resultado" hx-indicator="#cargando" hx-disabled-elt="button[type=submit]">
  <label for="pregunta" class="pie">Describe lo que pasó o pregunta qué dice la norma</label>
  <textarea id="pregunta" name="pregunta" maxlength="{max}" required></textarea>
  <button type="submit">Preguntar</button>
</form>
<div class="ejemplos">{ejemplos}</div>
<p id="cargando" class="htmx-indicator">Buscando en la normativa… (en CPU tarda alrededor de un minuto)</p>
<div id="resultado" aria-live="polite"></div>
<p class="pie">{aviso} Modelo pequeño en CPU: puede equivocarse; comprueba siempre el artículo citado. <a href="{repo}">Código y evaluación</a>.</p>
</main>
<script>function usar(b){{ const t=document.getElementById('pregunta'); t.value=b.textContent; t.focus(); }}</script>
</body></html>"""
