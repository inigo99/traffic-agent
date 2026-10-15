# trafico-agent: setup

## 1. Hardware y entornos

| Entorno | Uso |
|---|---|
| **GPU local** | Ollama con un modelo de 7–8 B (Qwen o Llama) para el agente, embeddings y reranker |
| **CPU** | Tests, CI, BM25 e índice vectorial |
| **HF Spaces (CPU gratis)** | Demo pública (usa el modelo por API o uno pequeño) |

## 2. Software

| Herramienta | Para qué |
|---|---|
| Python 3.12 + **uv** | Entorno |
| **LangGraph** (+ langchain-core) | Grafo del agente |
| **FastMCP** (SDK de MCP para Python) | Servidor MCP `trafico-mcp` |
| **Ollama** | LLM local |
| sentence-transformers: **bge-m3** o **multilingual-e5-large**, más un reranker (bge-reranker-v2-m3) | Embeddings y reranking multilingües |
| **LanceDB** o **Qdrant** (modo local) | Índice vectorial sin servidor |
| rank-bm25 o tantivy | BM25 |
| **pdfplumber** / camelot | Extraer la tabla ARCI del PDF |
| SQLite | Tabla de sanciones y consultas estructuradas |
| **RAGAS** + un conjunto de evaluación propio | Evaluación |
| **Langfuse** (Docker, self-hosted) o **Arize Phoenix** | Trazas y observabilidad |
| Gradio, o FastAPI con HTMX | Interfaz |
| pytest, ruff, pre-commit, GitHub Actions | Calidad, CI y tarea semanal de cambios en el BOE |

## 3. Cuentas y claves

| Cuenta | Para qué |
|---|---|
| GitHub | Repo, Actions y releases del MCP |
| Hugging Face | Space de la demo |
| API de LLM (opcional) | Referencia de calidad y modelo de la demo pública; poner límite de gasto |
| PyPI (opcional) | Publicar `trafico-mcp` para instalarlo con `uvx` |

La API del BOE y el PDF de la DGT no necesitan clave.

## 4. Skills de Claude útiles

| Skill | Cuándo usarla |
|---|---|
| `anthropic-skills:mcp-builder` | **Diseñar e implementar el servidor MCP**: herramientas, descripciones y pruebas |
| `engineering:system-design` / `engineering:architecture` | Grafo del agente y ADR sobre la recuperación |
| `engineering:testing-strategy` | Conjunto de evaluación y tests del agente |
| `anthropic-skills:pdf` | Extraer y verificar la tabla ARCI |
| `data:validate-data` | Validar la tabla extraída y el informe de evaluación |
| `data:create-viz` / `dataviz` | Gráficas de la comparativa de recuperación |
| `anthropic-skills:context-engineering-fundamentals` | Diseñar el contexto del agente: qué artículos entran y en qué orden |
| `anthropic-skills:prompt-master` | Prompts del sistema y del juez |
| `engineering:code-review`, `ponytail:ponytail-review` | Revisar PRs |
| `anthropic-skills:verification-before-completion` | Antes de afirmar que una métrica mejora |

## 5. Conectores y MCP

| Conector | Uso |
|---|---|
| Carpeta local `Proyectos\trafico-agent` | Código |
| GitKraken | Ramas, commits y PRs |
| **Context7** | Documentación al día de LangGraph, FastMCP, RAGAS y LanceDB |
| ScraplingServer / Firecrawl | Páginas de la DGT y del BOE, y la guía ARCI |
| **[MCP-BOE](https://github.com/ComputingVictor/MCP-BOE)** (opcional, en desarrollo) | Explorar artículos del BOE desde el chat mientras se escribe el conjunto de test |
| El propio `trafico-mcp` | Probarlo desde Claude Desktop en cuanto exista |

## 6. Estructura inicial del repo

```
trafico-agent/
├── pyproject.toml
├── CLAUDE.md
├── src/trafico_agent/
│   ├── ingest/
│   │   ├── boe.py          # normas por bloque (artículo) vía API BOE
│   │   └── arci.py         # PDF → SQLite
│   ├── index.py            # BM25 + vectores + reranker
│   ├── tools.py            # buscar_normativa, leer_articulo, consultar_sancion
│   ├── agent.py            # LangGraph
│   ├── mcp_server.py       # FastMCP
│   ├── ui.py               # Gradio / FastAPI
│   └── watch.py            # detector de cambios en el BOE
├── eval/
│   ├── questions.yaml      # 150 preguntas con gold
│   └── run_eval.py
└── tests/
```

## 7. Contenido propuesto para el `CLAUDE.md`

```markdown
- Toda afirmación normativa lleva cita (id BOE + artículo). Sin cita, no se responde.
- La tabla ARCI es la única fuente de importes y puntos; el LLM nunca los genera.
- eval/questions.yaml es el contrato: cualquier cambio de prompt/modelo se evalúa antes del merge.
- Aviso legal visible en UI y en la respuesta del MCP.
```

## 8. Primeros pasos en el chat del proyecto

1. Descargar el PDF de la guía ARCI y comprobar si la tabla se extrae bien con pdfplumber (el mayor riesgo del proyecto).
2. Probar `GET /datosabiertos/api/legislacion-consolidada/id/BOE-A-2003-23514/texto/indice` para ver la granularidad de los bloques.
3. Escribir las primeras 20 preguntas del conjunto de evaluación antes de programar nada.
