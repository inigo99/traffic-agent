# S5 — Producto: demo web, CI, despliegue y README

## Demo web (`src/trafico_agent/web.py`)

FastAPI + HTMX en una sola página: cuadro de pregunta, ejemplos, respuesta con enlaces al BOE y aviso legal. Atiende una pregunta a la vez (lock global), limita la pregunta a 500 caracteres, escapa el texto y cachea las respuestas repetidas (`lru_cache`), para no gastar cuota de la API con los ejemplos.

## Cambios en el agente al probar la demo con qwen2.5:3b

Con el modelo pequeño, el texto redactado contradecía la sanción calculada: "500 euros" en un tramo de 100 €, "no supera el límite" con 0,30 mg/l, "leve" en una grave. Arreglos:

- **Velocidad y alcohol por plantilla**, sin redacción del LLM (y una llamada menos).
- El filtro del texto también borra las frases con "infracción leve/grave"; si el texto queda vacío, ya no se recupera el original.
- **Reglas** para lo que el 3b no detectaba: ordenanza (zona azul, ORA, grúa municipal; bajas emisiones, carga y descarga, patinete o residentes si se nombra una ciudad), posible delito (fuga, negarse a soplar, sin carné, carné retirado, carreras), competencia (Navarra, Cataluña, País Vasco y policía local, con el art. 84 LSV) y fuera de ámbito (recursos, seguros). Si la pregunta trae velocidad o tasa, se trata como situación.

| qwen2.5:3b | Antes | Después |
|---|---|---|
| Situaciones: sanción exacta | 37/56 | 37/56 |
| Trampas: comportamiento | 18/30 (60 %) | 29/30 (97 %) |
| Trampas: claves | 8/25 | 17/25 |

La cifra de trampas es optimista: las reglas se escribieron mirando esas 30 preguntas. Lo que no mejora es corregir premisas falsas (T03, T17–T23).

## CI (`.github/workflows/ci.yml`)

Ruff y pytest en cada push. Sin `data/trafico.db` se saltarían 33 tests, así que la CI genera la base (PDF ARCI + API del BOE, ~5 min) y la guarda en caché con clave `versiones.json` + PDF + código de ingesta. En verde desde el primer push.

## Despliegue: de HF Spaces a Render + Groq

| Intento | Resultado |
|---|---|
| HF Spaces Docker con qwen2.5:3b (llama.cpp) en CPU | **402**: desde 2026, los Spaces Docker y Gradio en CPU gratis piden PRO |
| Render + Qwen2.5-72B por HF Inference Providers | **402**: la cuenta gratis no tiene créditos de inferencia |
| Render + Groq `llama-3.3-70b-versatile` | **404**: el modelo ya no está en Groq |
| **Render + Groq `openai/gpt-oss-120b`** | ✅ https://trafico-agent.onrender.com |

Configuración de la demo publicada (`render.yaml`): plan gratis de 512 MB, BM25 en vez de bge-m3 (sin torch) y el LLM por una API compatible con OpenAI (`llm.api`, `TRAFICO_API_URL`/`TRAFICO_API_MODELO`/`TRAFICO_API_KEY`). El proveedor reintenta en 429 (límite por minuto), pasa a `json_object` si el modelo no acepta `json_schema`, quita bloques `<think>` y deja 4096 tokens a los modelos con razonamiento.

Comparación en Groq con BM25 (10 situaciones):

| Modelo | Comportamiento | Sanción | Cita | s/pregunta |
|---|---|---|---|---|
| qwen/qwen3.8-27b | 7/10 | 4/9 | 4/9 | 6,3 |
| **openai/gpt-oss-120b** | 10/10 | 6/9 | 8/9 | 20,2 |

Con BM25 la fila ARCI correcta entra en las candidatas solo en 4/7: es el límite de la demo ligera.

Comprobado en la demo: velocidad (100 €, 0 puntos, Anexo IV, 16 s en frío) y zona azul (rechazo por ordenanza, 2 s).

## README

Descripción, arquitectura, informe de evaluación (recuperación, cinco modelos, trampas, lo que más pesó), uso (ingesta, agente, web, MCP, evaluación, trazas), despliegue, limitaciones y licencia MIT.

## Pendiente

- Evaluación completa de la demo (`gpt-oss-120b` + BM25) y de las factuales (`--tipo factual`).
- Trampas nuevas que no se usaron para escribir las reglas, para medir sin sesgo.
- Gold de T13 (200 km/h en vía de 120 está justo en el límite del art. 379 CP).
- Publicar el post (`notas/post-rag-legal.md`).
