# S4 — Servidor MCP, trazas y aviso de cambios del BOE

## Servidor MCP (`src/trafico_agent/mcp_server.py`)

`trafico-mcp` (stdio) con 6 herramientas deterministas, sin LLM; cada respuesta lleva `aviso`:

| Herramienta | Qué hace |
|---|---|
| `buscar_normativa(consulta, k)` | Fragmentos de LSV/RGC con artículo y url del BOE (vectores bge-m3; BM25 si no hay vectores) |
| `leer_articulo(norma, id_bloque)` | Texto vigente completo y fecha de la versión |
| `consultar_sancion(codigo)` | Fila ARCI: gravedad, importe, pronto pago, puntos |
| `sanciones_parecidas(hecho, k)` | Filas ARCI cuyo hecho se parece a la descripción |
| `consultar_velocidad(limite, velocidad)` | Tramo del Anexo IV de la LSV |
| `version_normativa()` | Fecha consolidada de cada norma |

- SDK `mcp` 2.x: `FastMCP` pasó a llamarse `MCPServer` (`mcp.server.mcpserver`).
- `tests/test_mcp.py` lo prueba con el cliente del SDK en proceso.
- Probado en Claude Desktop (21-10-2026): "¿qué multa hay por ir a 151 km/h en autovía y qué dice el art. 117 del RGC?" → `consultar_velocidad` + `leer_articulo`, 300 € / 2 puntos y el texto del artículo con su url.

Configuración de Claude Desktop (`claude_desktop_config.json`):

```json
"trafico": {
  "command": "uv",
  "args": ["--directory", "<ruta>/trafico-agent", "run", "--extra", "ml", "trafico-mcp"],
  "env": {"TRAFICO_DB": "<ruta>/trafico-agent/data/trafico.db"}
}
```

## Trazas (`src/trafico_agent/trazas.py`, extra `obs`)

Phoenix local (sin cuenta ni Docker): `uv run --extra obs phoenix serve` y `TRAFICO_TRAZAS=1` al ejecutar.

- Un span por nodo del grafo (instrumentación OpenInference de LangChain/LangGraph).
- Un span `LLM` por llamada a Ollama (`llm.py`), con modelo, prompt, respuesta, tokens de entrada y salida y latencia. Sin trazas activadas es un no-op.
- Se eligió Phoenix frente a Langfuse self-hosted: la versión actual de Langfuse pide Docker con Postgres, ClickHouse, Redis y MinIO.
- Visto en local con 5 situaciones: la primera tarda ~90 s (carga de bge-m3 y del modelo en Ollama), las siguientes ~4 s.

## Aviso de cambios del BOE (`src/trafico_agent/watch.py`)

- Compara el índice de la API de legislación consolidada con `data/versiones.json` (versionado: fecha de cada bloque) y lista los bloques nuevos, modificados o eliminados. Solo biblioteca estándar.
- Sale con 3 si hay cambios (no 1: un error de red también sale con 1).
- `--guardar` tras reindexar: actualiza `versiones.json` y añade la entrada al `CHANGELOG.md`.
- `.github/workflows/boe-semanal.yml`: cada lunes; si hay cambios abre un issue. Reindexar sigue siendo manual (necesita bge-m3).
- Estado guardado el 21-10-2026: LSV y RGC con última actualización 26-06-2026, la misma versión indexada.
