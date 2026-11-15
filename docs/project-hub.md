# Texto para Arduino Project Hub

Listo para copiar en projecthub.arduino.cc → *New project*. Cada sección de abajo es una sección del editor. Donde pone **[FOTO]** o **[VÍDEO]**, subid la imagen o el vídeo.

---

**Título:** A math copilot that thinks in Python, fully offline on the Arduino UNO Q

**Resumen (una línea):** Un Qwen3-1.7B entrenado para escribir programas cortos resuelve problemas del Canguro matemático dentro de la UNO Q, sin red y en menos de 60 s: del 21 % al 69 %.

**Etiquetas:** UNO Q, LLM, llama.cpp, edge AI, education, math

---

## 1. Introducción

Los problemas del Canguro matemático son de opción múltiple (A-E) y están pensados para que un alumno los resuelva razonando. Nuestro reto, del Datathon FME 2026 de Qualcomm, era que un modelo de lenguaje los resolviera **entero dentro de una Arduino UNO Q**: sin internet y con 60 segundos por problema.

El problema es la velocidad. La CPU de la placa lee unos 4,6 tokens por segundo y escribe 2,7. En un minuto no cabe un razonamiento en prosa. El modelo del reto, sin trucos, acierta el 21 %: lo mismo que el azar.

Nuestra idea: **que el modelo no razone en prosa, sino que escriba un programa de Python de cinco líneas**. La placa lo ejecuta en milisegundos y el resultado se compara con las cinco opciones. Con un modelo entrenado para eso, el sistema acierta el **69 %** del examen de prueba de la organización, con el reloj de la placa.

**[VÍDEO]** La demo: un problema en inglés y otro en catalán resueltos en la placa.

## 2. Componentes y apps

- **Arduino UNO Q 4 GB.**
- **llama.cpp** (commit `2cbe0ec`, el del reto) con `llama-server` como servicio.
- **Nuestro modelo** `sopa_z10-Q8_0.gguf` (1,83 GB): Qwen3-1.7B con la media de los pesos de 10 adaptadores LoRA, en GGUF Q8_0. Se descarga de la *release* del repositorio.
- **Nuestro `predict.py`:** un solo fichero de Python con la biblioteca estándar.
- **Dataset M3Kang** (Qualcomm), para entrenar y medir. No se redistribuye.

## 3. Arquitectura

**[FOTO]** El diagrama de arquitectura del README.

Todo corre en la parte Linux de la placa (QRB2210, 4 núcleos Cortex-A53). El microcontrolador no interviene. Para cada problema:

1. **¿Repetido?** Si el problema ya está en el banco de entrenamiento con las mismas opciones, se responde en 2 ms.
2. **Letra rápida.** El modelo da una letra en 1 token. Siempre hay respuesta, y el enunciado queda en la caché del servidor.
3. **Programa.** El modelo escribe un programa corto. El número de tokens se ajusta al tiempo que queda.
4. **Ejecutar y casar.** Un subproceso, con límite de memoria y de tiempo, ejecuta el programa. Su salida se compara con las opciones: números, fracciones, unidades y texto.
5. **Reserva.** Si no casa ninguna opción: la mediana de las opciones si son números, o E.

Dos detalles importan mucho:
- **La caché.** El prompt de sistema es siempre el mismo y el servidor lo reaprovecha, así que cada problema solo lee sus ~70 tokens nuevos. Sin caché, el primer problema tarda 71-78 s.
- **Determinismo.** Temperatura 0 y semilla fija: las mismas respuestas cada vez.

### Cómo usamos M3Kang

- **Fábrica de entrenamiento.** Programas verificados para sus problemas de texto, y sus problemas como referencia de estilo para generar problemas nuevos con modelos abiertos.
- **Banco de repetidos.** El Canguro repite problemas entre niveles.
- **Banco de pruebas** y análisis de errores.

### El entrenamiento

Casi 20.000 problemas con su programa. **Cada programa se ejecutó para comprobar que imprime la respuesta marcada.** Vienen de cuatro fuentes:
- programas verificados de M3Kang;
- programas correctos escritos por el propio modelo;
- problemas sintéticos de modelos abiertos, dirigidos a los fallos del modelo: lógica, enunciados largos, catalán;
- problemas públicos (MathQA, AQuA-RAT).

Con ellos se entrenaron LoRA de rango 32 sobre Qwen3-1.7B. El modelo final es la **media de los pesos de 10** de ellos («sopa de modelos»), que suma más que cualquiera por separado.

## 4. Paso a paso

Desde una UNO Q con los pasos 0-10 del repositorio del reto hechos:

```bash
git clone https://github.com/Arnau000z/placa-velocidad.git ~/placa-velocidad
cd ~/placa-velocidad && ./instalar_en_placa.sh
```

Qué hace `instalar_en_placa.sh`:
1. Baja el modelo de la *release*, si no está, y comprueba su md5.
2. Pone `LLM_FILE=sopa_z10-Q8_0.gguf` en el `config.env` del reto y reinstala los servicios con su script oficial.
3. Copia nuestro `predict.py` al repositorio del reto.
4. Pasa 6 problemas por el servicio real y enseña una tabla con la respuesta, si acierta y los segundos. Debe terminar en «BIEN: ningún problema pasa de 60 s».

**[FOTO]** La tabla del instalador en la terminal de la placa.

Para la demo:

```bash
python3 demo.py
```

Enseña cada problema, la letra rápida, el programa que escribe el modelo, lo que imprime y la respuesta, con un reloj de 60 s.

El jurado lo ejecuta así:

```bash
cd ~/datathon-UPC-maths-qualcomm-arduino-unoq
python3 predict.py --input examen.jsonl --output respuestas.csv
```

Código completo, documentación y todas las pruebas: **https://github.com/Arnau000z/placa-velocidad**

## 5. Resultados

Examen de prueba de la organización (50 problemas en inglés y catalán), con el reloj de la placa:

| Sistema | Acierto |
|---|---|
| Azar | 20 % |
| Modelo del reto (Qwen3.5-0.8B, letra directa) | 21 % |
| Nuestro sistema con Qwen3-1.7B sin entrenar | 37 % |
| Con un LoRA entrenado con programas verificados | 57 % |
| **Modelo final (media de 10 LoRA)** | **69 %** |

- **M3Kang val** en inglés y catalán, solo texto: 116/242 (48 %).
- **Tiempo:** media de 38-42 s por problema y máximo de 52-58 s.
- **Velocidad medida en la placa:** lee 4,3-5,2 tokens/s y escribe 2,7-2,8.

**Análisis de errores:**
- **Por tema** (Qwen3-1.7B, problemas de texto de val): probabilidad 71 %, aritmética 52 %, teoría de números 49 %, conteo 47 %, álgebra 44 %, geometría 42 %, medida 38 %, lógica 27 %.
- **Por idioma** (modelo final): en el examen de prueba, inglés 76 % y catalán 62 %; en val, 51 % y 45 %. El catalán sigue por detrás: 14 puntos en el examen de prueba y 6 en val.
- **Por longitud:** enunciados de menos de 40 palabras, 61 %; de 40 a 80, 33 %.
- **Por causa:** el 75 % de los fallos son de **planteamiento** (olvidar una condición, contar pares dos veces, invertir una relación), no de cálculo ni de tiempo. Con el doble de tiempo solo se recupera 1 de 16 fallos.

**[FOTO]** La gráfica «Del azar al 69 %» (`figuras/progreso.png` del repositorio).

## 6. Qué aprendimos

- **En una placa así, el tiempo es la métrica.** Una variante que acierta el 50 % sin límite se queda en el 19 % con el reloj de la placa. Desde ahí, todo se midió con ese reloj.
- **Un programa verificado vale más que una explicación.** Entrenar con explicaciones en prosa empeoró el modelo 9 puntos. Entrenar con programas comprobados lo mejoró 20.
- **El RAG no ayudó.** Poner ejemplos parecidos en el prompt no subía la nota y costaba 65 s de lectura por problema.
- **La sopa de modelos funciona.** Promediar los pesos de varios entrenamientos suma más que el mejor de ellos.
- **Siguiente paso:** enseñar al modelo a plantear mejor, con datos dirigidos a las trampas típicas del Canguro, y llevar una pista al alumno en lugar de la respuesta (el modo «enseñar» del reto).

M3Kang: Torres-Camps et al., 2026, arXiv:2601.16218. Sus datos no se redistribuyen.
