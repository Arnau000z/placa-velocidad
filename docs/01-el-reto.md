# El reto

**Datathon FME 2026 · reto de Qualcomm «Math on the Edge»**: construir un copiloto de matemáticas que funcione **entero dentro de una Arduino UNO Q**, sin red, y que use el dataset M3Kang (problemas del Canguro matemático).

El reto ofrece dos caminos: **enseñar** (pistas, práctica adaptativa, análisis de errores) o **razonar** (dado un problema tipo Canguro, elegir la opción correcta, medido por la organización en un test oculto). Elegimos **razonar**: tiene una nota objetiva y es lo más difícil de hacer bien en una placa así.

## La placa

| | Arduino UNO Q (4 GB) |
|---|---|
| CPU | Qualcomm QRB2210, 4 núcleos Cortex-A53 (sin aceleración de IA usable por llama.cpp) |
| Memoria | 4 GB (unos 3,6 GB libres con Linux arrancado) |
| Sistema | Debian en la parte Linux; un microcontrolador aparte para LEDs, botones y sensores |
| Red durante el examen | ninguna |
| Velocidad que anuncia la organización | ~11 tokens/s leyendo y ~5 escribiendo (con el modelo de 0,8B) |

La frase clave del enunciado: *«Every word you put into a prompt costs time.»* En esta placa **leer** un enunciado de 70 tokens con un modelo de 1,7B cuesta unos 15 s, y **escribir** 50 tokens otros 19 s. Todo el proyecto gira alrededor de esa cuenta.

## Lo que da la organización

- **llama.cpp** fijado al commit `2cbe0ec`, compilado en la placa (`llama-server` y `llama-cli`).
- **Qwen3.5-0.8B Q8_0** como modelo de lenguaje y **bge-small-en-v1.5** como modelo de embeddings, como servicios de systemd (`math-llm` en el puerto 8081 y `math-embed` en el 8082).
- Ajustes del servidor: `--ctx-size 4096 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0`.
- Un `predict.py` de referencia que contesta una letra por problema (la *baseline*).

## Los datos: M3Kang

| Conjunto | Problemas | Idiomas |
|---|---|---|
| `train.jsonl` | 4.073 | eng 1.466 · cat 1.466 · esp 1.141 |
| `val.jsonl` | 789 | eng 281 · cat 281 · esp 227 |
| Imágenes | 4.862 PNG | — |

- Cada problema trae enunciado, cinco opciones A-E, la respuesta, el nivel (0-7, de 10 años a bachillerato) y el año.
- Algo más de la mitad de val (440 de 789) depende de una figura.
- El OCR oficial solo leía bien las opciones del 63 % de los problemas. Las limpiamos hasta el 90 % (el resto son opciones que son dibujos): ver [datos y entrenamiento](05-datos-y-entrenamiento.md#limpieza-de-opciones).
- **Licencia solo para investigación.** Este repositorio no incluye ningún enunciado, imagen ni índice de M3Kang: solo identificadores y resultados agregados.

## El examen

Formato del examen final, según el examen de prueba que publicó la organización:

- **20 problemas nuevos** (no son de M3Kang), en **inglés o catalán**, niveles 0-7.
- **16 de texto y 4 con figura**, y **la figura no se entrega**: el JSONL lleva `text_only`, las `options` leídas por OCR y `language`.
- Letras equilibradas entre A y E.
- **60 s por problema**, con el `predict.py` del equipo corriendo en la placa.
- Se pasa el 15/11/2026 a partir de las 12:00.

El **examen de prueba** (50 problemas en inglés y catalán, 100 filas con su respuesta) es nuestra referencia principal: se parece más al examen real que M3Kang. En él los problemas de texto salen unos 12 puntos más fáciles que en val (49 → 61 % con el mismo sistema).

## La línea base

| Sistema | Acierto |
|---|---|
| Azar | 20 % |
| Contestar siempre D | 22,7 % (val) |
| Baseline oficial: Qwen3.5-0.8B, letra directa con gramática | 21,0-21,5 % (val, 789) |

## Lo que hay que entregar

- El proyecto documentado en un repositorio abierto y en Arduino Project Hub: arquitectura, experiencias, cómo replicarlo y **análisis de errores por tema, idioma y dificultad** (ver [resultados](06-resultados.md#análisis-de-errores)).
- Una demo en directo y un pitch de 3 minutos con la placa.
