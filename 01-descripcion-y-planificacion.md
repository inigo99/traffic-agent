# trafico-agent: asistente de normativa de tráfico con citas

> Proyecto B2. Nombre provisional del repo: `trafico-agent`.
> Estado: planificación, sin código.

## 1. Qué es

Un asistente que responde preguntas sobre tráfico y seguridad vial en España **citando el artículo exacto** de la norma. Además, un agente analiza situaciones concretas ("aparqué en doble fila 5 minutos para descargar, ¿es multa?") y devuelve:

- la **infracción aplicable**;
- su **gravedad**, el **importe** y los **puntos**;
- la **reducción del 50 % por pronto pago** cuando corresponde;
- las **fuentes** en las que se basa.

Siempre avisa de que es información y no asesoramiento jurídico.

**Por qué es distinto de lo que ya existe.** En GitHub no he encontrado ningún proyecto de RAG o agente sobre la normativa de la DGT (0 resultados). Lo más parecido son asistentes genéricos sobre el BOE.

**Qué demuestra:**

- RAG con recuperación híbrida y reranking.
- Un agente con herramientas (LangGraph).
- **Un servidor MCP propio** con los datos de la normativa.
- Consulta de datos estructurados (la tabla de sanciones) combinada con texto legal.
- Evaluación seria: recuperación, exactitud de citas y fidelidad.
- Observabilidad.
- Actualización automática cuando cambia la ley.

## 2. Alcance

### Corpus (v1)

Las normas y su identificador en el BOE están comprobados en la API del BOE:

| Norma | Identificador BOE | Uso |
|---|---|---|
| **RDL 6/2015**, texto refundido de la Ley sobre Tráfico, Circulación de Vehículos a Motor y Seguridad Vial | `BOE-A-2015-11722` | Infracciones, sanciones, puntos y procedimiento |
| **RD 1428/2003**, Reglamento General de Circulación | `BOE-A-2003-23514` | Normas de circulación, detallado artículo por artículo |
| **Guía codificada de infracciones (ARCI)** de la DGT, vigente desde el 01-07-2025 ([PDF](https://sede.dgt.gob.es/export/sites/dgt/.galleries/multas/ARCI/Guia-codificada-de-infracciones-ARCI-Vigente-a-partir-del-01-07-2025.pdf)) | — | Tabla que relaciona cada infracción con su precepto, gravedad, importe y puntos |

Posible v2: el Reglamento General de Conductores (permisos) y el de Vehículos (ITV y documentación). Hay que comprobar sus identificadores antes de incluirlos.

### Fuera de alcance (v1)

- **Ordenanzas municipales:** zonas ORA, ZBE, patinetes en cada ciudad. El asistente debe **reconocer** que una pregunta depende de la ordenanza y decirlo, sin inventarse la respuesta.
- Delitos contra la seguridad vial (Código Penal): solo se señala cuándo una conducta puede ser delito, sin analizarla.
- Recurrir multas: se da información general, no se redactan recursos.

## 3. Funcionalidades

1. **Preguntas y respuestas con citas:** "¿Cuál es la distancia mínima al adelantar a un ciclista?" → respuesta más el artículo y el enlace al BOE.
2. **"¿Es multa?":** a partir de una situación descrita, el agente extrae los hechos, busca los preceptos, consulta la tabla ARCI y responde con gravedad, importe, puntos, pronto pago y citas. Si faltan datos (velocidad exacta, vía urbana o interurbana), **hace una pregunta** en lugar de suponer.
3. **Comparar:** "¿Qué cambia entre ir a 71 y a 81 km/h en una vía limitada a 50?" (tabla de velocidades).
4. **Aviso de cambios:** una tarea semanal consulta en la API del BOE si alguna norma del corpus se ha modificado, reindexa y lo anota en el CHANGELOG.
5. **Servidor MCP** `trafico-mcp` con las herramientas `buscar_normativa`, `leer_articulo`, `consultar_sancion` y `version_normativa`, que se pueden usar desde Claude Desktop o cualquier cliente MCP.

## 4. Evaluación

**Conjunto de test propio: unas 150 preguntas** en tres grupos:

- **60 factuales**, con el artículo de referencia (*gold*).
- **60 situaciones "¿es multa?"**, con la infracción, la gravedad, el importe y los puntos de referencia. Se construyen desde la tabla ARCI.
- **30 trampas:** preguntas que dependen de una ordenanza, que están fuera de ámbito o que tienen premisas falsas. Se espera que el asistente se niegue o pida aclaración.

**Métricas:**

- **Recuperación:** recall@5 y MRR del artículo correcto.
- **Exactitud de citas:** el artículo citado contiene de verdad la afirmación.
- **Exactitud de los hechos estructurados:** importe y puntos exactos.
- **Fidelidad y relevancia** (RAGAS o un LLM que actúa como juez, validado con 30 casos revisados a mano).
- **Comportamiento ante las trampas:** % de respuestas correctas (se niega o pide aclaración).
- **Coste y latencia** por pregunta.

Se comparan varias configuraciones de recuperación (solo BM25, solo embeddings, híbrida y con reranker) y dos modelos: local con Ollama frente a uno por API.

## 5. Entregables

1. Repo `trafico-agent` con la ingesta, el RAG, el agente, el MCP, la evaluación, tests y CI.
2. **Demo pública** en HF Spaces.
3. **Servidor MCP** instalable (`uvx trafico-mcp`) con sus instrucciones para Claude Desktop.
4. Informe de evaluación en el README: tabla por configuración y análisis de errores.
5. Post: "Cómo medir que un RAG legal no se inventa artículos".

## 6. Planificación (unas 5 semanas a media jornada)

| Semana | Objetivo | Criterio de "hecho" |
|---|---|---|
| **S1: corpus** | Ingesta de las normas por bloques (artículos) desde la API del BOE. Extraer la tabla ARCI del PDF a SQLite y validarla con muestras | Artículos con metadatos; tabla ARCI con más de 95 % de filas correctas en una muestra de 50 |
| **S2: recuperación + test** | BM25 + embeddings (bge-m3 o multilingual-e5) + reranker. Escribir el conjunto de test de 150 preguntas | recall@5 medido para las 4 configuraciones |
| **S3: agente** | Grafo en LangGraph: extraer hechos → preguntar si falta algo → buscar → consultar la sanción → responder con citas | Las 60 situaciones evaluadas; importe y puntos medidos |
| **S4: MCP + observabilidad** | Servidor MCP (FastMCP). Trazas con Langfuse o Phoenix. Tarea de detección de cambios en el BOE | Funciona en Claude Desktop y las trazas se ven en el panel |
| **S5: producto** | Interfaz (Gradio o FastAPI con HTMX), demo en HF Spaces, README e informe | Demo pública, CI en verde y post |

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Respuesta legal incorrecta | Citas obligatorias; si no hay cita, no hay respuesta. Aviso legal visible. Evaluación de trampas |
| Tabla ARCI mal extraída del PDF | Validación con muestras y tests por fila crítica (velocidad, alcohol, móvil) |
| Normativa desactualizada | Tarea de cambios con la API del BOE; en cada respuesta se indica la fecha de la versión consolidada |
| Un LLM local de 7 B razona peor | Evaluar ambos modelos; la demo puede usar la API con límite de uso |
| Confusión entre vía urbana e interurbana y los límites | El agente pregunta en lugar de suponer, y se comprueba en el test |

## 8. Preguntas abiertas

- ¿La demo pública usa el modelo por API (mejor calidad, con coste y límite) o uno pequeño en CPU (gratis y más lento)?
- ¿Incluir en v1 una sección de Navarra, donde la Policía Foral también tiene competencias de tráfico? Hay que confirmar qué normativa propia aplica.
