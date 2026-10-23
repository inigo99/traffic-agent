# Cómo medir que un RAG legal no se inventa artículos

He hecho un asistente que responde preguntas sobre la normativa de tráfico en España citando el artículo exacto del BOE. Si le cuentas «iba sin cinturón y me ha parado la Guardia Civil», te dice la infracción, la multa, el pronto pago y los puntos, con el enlace al artículo.

Lo difícil no fue que respondiera. Fue saber cuándo respondía bien. Esto es lo que aprendí midiéndolo.

## Primero, el test

Antes de tocar el agente monté un conjunto de 150 preguntas: 60 factuales («¿a qué distancia hay que adelantar a un ciclista?»), 60 situaciones («¿es multa?») y 30 trampas (zona azul, posibles delitos, premisas falsas, cosas fuera de ámbito).

Cada pregunta tiene su respuesta de referencia: el artículo que hay que citar y, en las situaciones, la fila exacta de la guía de infracciones de la DGT. Un test comprueba esas referencias contra los datos, así que si cito un artículo que no existe, falla antes de evaluar nada. Revisé 30 a mano y había 2 mal (una pregunta ignoraba que los noveles empiezan con 8 puntos, no con 12).

## Con pocas preguntas, el ganador era otro

Con las 18 primeras preguntas, BM25 (búsqueda por palabras) parecía la mejor recuperación. Con 135 preguntas parafraseadas se dio la vuelta: los vectores de bge-m3 sacaban 0,77 de recall@5 frente a 0,57 de BM25. Un test pequeño no sirve para decidir.

El reranker era el mejor (0,79), pero tardaba unos 30 segundos por consulta en CPU. Me quedé con los vectores solos.

## El LLM no escribe números

La regla más útil del proyecto: el modelo nunca genera importes ni puntos. Salen de SQL, de la tabla de la DGT y de los tramos de velocidad de la ley. El LLM solo hace tres cosas: entender la pregunta, elegir una fila de la guía entre unas candidatas y redactar.

Aun así, el modelo pequeño (qwen2.5 de 3B) escribía «500 euros» encima de una sanción de 100, o «no supera el límite» con 0,30 mg/l de alcohol. Así que borro del texto cualquier frase con euros, puntos o gravedad, y en velocidad y alcohol la respuesta es una plantilla. Menos LLM, menos sitio donde equivocarse.

## El mayor salto fue un bug

La fila correcta de la guía solo estaba entre las opciones del modelo en 30 de 54 situaciones. Un tope de 12 candidatas dejaba fuera, siempre, todas las filas que venían de los artículos encontrados. Al arreglarlo pasó a 43 de 54, más que con cualquier cambio de prompt.

Lo encontré porque medía cada paso por separado: si la fila correcta estaba en las candidatas, y si el modelo la elegía. Con una sola métrica final no lo habría visto.

## Los modelos pequeños necesitan barandillas

Con qwen2.5 de 1,5B, el 9 % de las sanciones salía bien. Dos cambios lo subieron al 62 %: limitar la respuesta del modelo a los códigos de la lista (la salida JSON con un enum) y no tirar la sanción cuando el texto no traía cita, si la sanción ya trae su artículo.

Comparando modelos en las 60 situaciones, la sanción exacta quedó así: Claude Haiku 86 %, qwen2.5 7B 77 %, 3B 66 % y 1,5B 62 %. Donde más se nota la diferencia es al elegir entre filas casi idénticas de la guía.

## Lo que todavía no mido bien

Las trampas pasaron del 60 % al 100 % al añadir reglas para ordenanzas, delitos y competencias. Pero escribí esas reglas mirando las mismas 30 trampas, así que la cifra es optimista. El siguiente paso es un lote de trampas nuevas que el sistema no haya visto.

Y corregir premisas falsas («como el móvil quita 8 puntos…») sigue fallando con modelos pequeños. Eso no lo arregla una regla.

## Dónde verlo

El código, la evaluación y las notas de cada decisión están en GitHub (inigo99/trafico-agent), y hay una demo en trafico-agent.onrender.com. También tiene un servidor MCP para usarlo desde Claude Desktop.

Es información orientativa, no asesoramiento jurídico (eso también lo dice el asistente en cada respuesta).
