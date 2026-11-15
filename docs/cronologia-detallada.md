# Cuaderno de laboratorio: Datathon FME 2026, reto Qualcomm «Math on the Edge»

Copiloto de matemáticas tipo Canguro que funciona dentro de una Arduino UNO Q (4 GB de RAM, sin red, 60 s por problema). Este cuaderno recoge, por bloques de tiempo, qué se probó, con qué modelo, el resultado con sus cifras y la decisión que tomó el equipo.

## 14/11 mañana (11:58-14:48)

- **14:01** Se encarga la descarga completa del material del reto y el OCR del paso 9 del README. El comando busca una carpeta de datos (también en un pen), reaprovecha la caché de OCR a medias (524 problemas) si existe y, si no, la crea en un disco con al menos 15 GB libres. Todas las descargas se fijan a versión y se verifican con SHA256 (campo `lfs.oid` de Hugging Face).
- **14:35** Prueba de velocidad de OCR con 144 imágenes reales de M3Kang:
  - CPU, 12 hilos: 0,56 imágenes/s.
  - CUDA: no funciona en la RTX 5060 Ti (falla cuDNN y cae a CPU sin avisar).
  - DirectML en la gráfica, 3 procesos: 7,4 imágenes/s (unas 13 veces más rápido que la CPU).
  - Las opciones leídas por la gráfica coinciden en las 144 con las de la CPU.
  - **Decisión:** el OCR va por la gráfica. Se lanzan en paralelo el OCR de las 4.862 imágenes (inglés, catalán y castellano) y la descarga del resto (modelos, M3Kang completo, llama.cpp, App Lab y adb). Se escriben `descargar.py` y `ocr_paralelo.py` y un entorno Python con onnxruntime-directml.
- **14:37** Estado intermedio: OCR en 481 de 4.862 imágenes, a unas 5,5 imágenes/s (unos 13 min restantes). Descargas: 0,5 de unos 10 GB, a ~6 MB/s.
- **14:48** OCR terminado en 12 minutos, sin errores:
  - train: eng 1.466, cat 1.466, esp 1.141 (total 4.073).
  - val: eng 281, cat 281, esp 227 (total 789).
  - Opciones A-E leídas en 3.080 de 4.862 problemas (63 %). En los problemas con solo texto, 76 %. El README da 62 %.
  - Respuesta más frecuente en train: D, con 25 %. Contestar siempre D acierta uno de cada cuatro.
  - Los `.jsonl` del script oficial salen con fin de línea CRLF; se pasan a LF, que es lo que espera la placa.

## 14/11 tarde (14:57-17:09)

- **14:57** Piezas del sistema: Qwen3.5 0,8B (modelo que elige la respuesta), bge-small (convierte textos en vectores para buscar problemas parecidos), llama.cpp (ejecuta los modelos en la placa), M3Kang (unos 1.750 problemas del Canguro en varios idiomas con su respuesta), App Lab y adb (configurar la placa y pasarle ficheros). El OCR es necesario porque en M3Kang las cinco opciones están dibujadas en la imagen; sin ellas el modelo no puede contestar con una letra.
- **14:59** Descargas: 8,5 de ~10 GB, 44 ficheros comprobados, ninguno fallido. Equipo de trabajo: Ryzen 5 3600, RTX 5060 Ti, 32 GB de RAM. No había carpeta de datos previa ni pen conectado, así que todo se hizo desde cero. Los scripts se probaron antes con datos inventados; los entornos de prueba (CUDA y DirectML) se borraron al acabar.
- **15:01** Cierre de la descarga: 9,3 GB, verificación de huellas correcta en todos los ficheros.
  - Repo del reto: commit d6e3f1b, sin modificar.
  - llama.cpp: commit 2cbe0ec, la versión exacta del reto.
  - Modelos: Qwen3.5 0,8B en GGUF (Q8_0, Q4_0, imatrix y mmproj), bge-small y Qwen3.5 0,8B completo (safetensors).
  - M3Kang completo: 14 ficheros de datos (5,8 GB), licencia y README. App Lab 0.12.0 y adb para Windows, macOS y Linux.
  - Datos del paso 9: `train.jsonl` con 4.073 problemas y `val.jsonl` con 789.
  - Todavía no se ha ejecutado ningún modelo local: Qwen y bge solo están descargados y llama.cpp no está compilado. Lo único que ha corrido son los tres modelos del OCR (RapidOCR: detección, orientación y lectura), en la gráfica.
- **15:02-15:08** Flujo general acordado. El OCR se ejecuta una sola vez en el PC. `train.jsonl` es la base de datos del RAG: un problema por línea con `text`, `options`, `label`, `language`, `level` y `year`; cuando las opciones son dibujos, `options` va vacío. `build_index.py` guarda en `index.db` los vectores de bge; en cada problema, bge busca 2-3 parecidos y se pasan a Qwen. Un ejemplo sin opciones enseña una respuesta sin sentido, por eso existe `--only-with-options`. Para medir en el PC se monta el mismo entorno que en la placa (misma versión de llama.cpp, mismo modelo Q8_0, mismos puertos), de modo que `eval.py` funciona sin cambios. La temperatura es cero y la semilla fija. Una ronda de validación tarda unos 45 min en la placa (estimación inicial); en la gráfica, minutos. El PC no mide tiempo ni memoria: la placa lee ~11 palabras/s y escribe ~5/s.
- **15:03-15:05** Medidas de partida, según el README: contestar siempre D da 25 %; Qwen 0,8B tal cual, en 40 problemas con opciones bien leídas, 22,5 %. De 40 respuestas, D 21 veces y A 14. Estimación: con OCR perfecto y el mismo modelo, ~22 %; con el mismo OCR y un modelo al 40 %, ~33 %. Conclusión: el cuello de botella es el modelo, no el OCR. Fallos del OCR: opciones que son dibujos y fracciones mal leídas («1/2» sale como «12»). Duda abierta: si el conjunto oculto llega solo como imagen, el OCR tendría que correr en la placa.
- **15:07-15:10** Fallos a atacar, por orden de impacto probable: sesgo de letra; cálculo sin Python; RAG (solo ejemplos con opciones, umbral de parecido o buscador multilingüe); visión con el mmproj; mejora del OCR; un modelo que quepa en 4 GB.
- **15:12-15:13** Requisitos: copiloto que funcione entero en la placa, sin internet, con M3Kang usado de forma original. Hay que elegir entre «enseñar» (guiar sin dar la respuesta) y «razonar» (acertar el máximo). El `predict.py` de todos los equipos se puntúa con el conjunto oculto, hagan lo que hagan. Entregables: código en GitHub y Arduino Project Hub, arquitectura, cómo replicarlo, análisis de errores por tema, idioma y dificultad; demo en directo y pitch de 3 minutos. Para la nota solo cuenta la letra correcta; cómo se llega a ella es libre. El script mete cada problema y sus traducciones en el mismo lado de train/val, para que no se copie la respuesta de otro idioma.
- **15:15-15:16** Idea de Arnau: que el modelo aprenda a resolver, no a memorizar. Conclusión del equipo: entrenar con problemas y letras no sirve; el conjunto oculto probablemente son problemas nuevos (M3Kang es público), y `val.jsonl` existe precisamente para medir si el modelo sabe resolver. Pregunta clave para la organización: ¿el conjunto oculto es de M3Kang o nuevo?
- **15:17** Planteamiento del sistema: todo pasa por `solve(problem)` en `copilot/pipeline.py`, que usan `predict.py` y `eval.py`. Plan inicial: nota base en el PC, RAG con 1-3 ejemplos, corrección del sesgo de letra, cálculo con Python cuando el problema lo permita y la letra más frecuente de train como salida de emergencia. Regla de trabajo: cada cambio se mide con `eval.py` sobre `val.jsonl`, y si no sube la nota, se descarta.
- **15:19-15:20** El sistema entero resuelve, no solo el modelo; el modelo puede ayudarse de Python, de problemas parecidos y de reglas. «Enseñar» es opcional pero puntúa en originalidad y pitch. La placa es fija; el modelo puede cambiarse si cabe en RAM, responde en 60 s y tiene licencia usable. Estimaciones de tiempo (sin medir): 0,8B Q8 (0,9 GB) lee ~8 s y escribe 50 palabras en ~10 s; ~2B Q4 (~1,3 GB), ~20 s y ~25 s; ~4B Q4 (~2,5 GB), ~40 s y ~50 s. Opinión del equipo: el 0,8B es demasiado pequeño para mates; un modelo de 1,5-2B especializado sería la opción más probable. El Q4_0 del 0,8B va más rápido que el Q8 en CPU (sin cifra medida).
- **15:22** Propuesta de fine-tuning. Entrenar desde cero no es viable en un datathon. Afinar sí: se bajó `Qwen3.5-0.8B-hf` por ser la versión entrenable; con LoRA, el 0,8B se afina en la 5060 Ti en minutos por pasada. Afinar con «problema → letra» produce memorización; la propuesta es **destilación**: un LLM grande de API genera soluciones cortas (30-60 palabras, porque cada palabra escrita cuesta ~0,2 s en la placa), se quedan las que llegan a la letra correcta y se afina con esos pares.
- **15:23-15:25** Limpieza del JSON, antes de tocar el modelo. Propuesta: medir la calidad con una muestra de 100 problemas; cruzar los tres idiomas (si el número coincide en dos, se corrige el tercero); separar los casos sin opciones en dibujos y texto no leído (el 24 % de los «solo texto»); recuperarlos con un modelo de visión local en la gráfica o con un LLM grande de API; comprobaciones automáticas (cinco opciones distintas, letra del `label` presente, sin restos de OCR); y un campo con el origen de cada opción (`ocr`, `cruzado`, `visión`, `figura`). Validez: la preparación del JSON se hace una vez, en el PC, y es válida con cualquier método. Cuidados: la licencia de M3Kang es solo de investigación y no se redistribuye; mandar imágenes a un servicio externo es zona gris. El jurado trae su propio JSON, con tres escenarios posibles: opciones en texto y correctas; opciones del OCR del README; o sin opciones.
- **15:30** Decisión tras confirmar la organización que el JSON del test llegará completo: leer imágenes en la placa queda descartado y el OCR sirve solo para la base de ejemplos. **Prioridades:** (1) nota base en el PC; (2) limpiar `train.jsonl` en 1-2 días, con objetivo de ~90 % de problemas con opciones fiables; (3) RAG con 1, 2 y 3 ejemplos, corrección del sesgo y Python para el cálculo; (4) fine-tuning por destilación; (5) verificar en la placa que responde en menos de 60 s; (6) pistas al alumno, análisis de errores, GitHub, Project Hub y pitch. Preguntas pendientes a la organización: ¿test de M3Kang o nuevo?, ¿en qué idiomas?
- **15:37** **Nota base:** los 789 problemas de `val.jsonl` tardaron **68 segundos** en la gráfica (en la placa, unas 2 horas según la estimación).
  - **Resultado: 21,5 % (170 de 789).** Contestar siempre D daría 22,7 %; azar, 20 %.
  - Por idioma: catalán 23,8 %, inglés 22,1 %, castellano 18,1 %.
  - Con opciones leídas por OCR: 20,8 %. Sin opciones: 22,7 %. Las opciones no mejoran el resultado.
  - Sesgo de letra: contestó D 348 veces y C solo 7, cuando las correctas están repartidas (~150 cada una). Por nivel: 38 % en el nivel 1; 9-10 % en los niveles 3 y 6, por debajo del azar.
  - Montaje: llama.cpp en el commit b12308 (el anterior al del reto; la única diferencia es un arreglo del servidor web, sin efecto en la inferencia). Resultados guardados en `results/`, ignorado por git.
- **15:40-15:58** Limpieza del JSON con un LLM grande de API. Propuesta de Arnau: las 1.747 imágenes en inglés (las tres versiones de un problema comparten opciones) se leen con un LLM grande de API en paralelo, se cruzan con el OCR de los tres idiomas y se validan automáticamente, añadiendo el origen y el tipo (`texto`/`dibujo`). Medición: unos 480 tokens por imagen (1650×220 píxeles). Estimación: ~1,3-1,5 M de tokens en total, equivalentes a 2-4 € de API; 15-20 min de lectura más 10-15 min de revisión de dudosos. Riesgo de licencia: las imágenes salen del PC. Se decide hacerlo en paralelo con un LLM grande de API.
- **16:05-16:18** Lectura y cruce:
  - Arranque en paralelo, 20 lotes a la vez de 49 imágenes; el resto entra según acaban. Mientras, se prepara el script de cruce con el OCR.
  - Primera pasada: 1.011 confirmados (58 %) por coincidencia entre el LLM y el OCR; 185 dibujos (11 %); 396 con solo lectura del LLM, sin OCR con qué compararla (23 %); 155 discrepancias (9 %). En las discrepancias suele fallar el OCR (fracciones «1/3» leídas como «13», raíces «V», euros «∈»), pero el LLM también falló en un caso (copió las opciones de otro problema). Decisión: segunda lectura independiente, con otro orden, de los 550 problemas sin confirmación del OCR. Correcciones manuales: 3 problemas con opciones arregladas y 2 con texto en espejo marcados como dibujo.
  - Verificación final de los 1.747 problemas en inglés: 1.015 confirmados por LLM + OCR; 533 por dos lecturas independientes del LLM; 186 dibujos confirmados; 13 corregidos a mano; 3 con confianza baja (candados y piezas con números). El LLM se equivocó 7 veces de 1.747 en cada pasada, siempre copiando opciones de un problema vecino; la segunda lectura los detectó.
  - Validaciones: cinco opciones por problema, respuesta correcta siempre entre las opciones, UTF-8, finales LF.
  - Ficheros: `train.jsonl` con 3.654 de 4.073 problemas con opciones; `val.jsonl` con 725 de 789. Campos nuevos: `options_type` (text/figures), `options_source` y `options_confidence`. Los originales del OCR se guardan como `train_ocr.jsonl` y `val_ocr.jsonl`.
  - **Nota base con opciones limpias: 21,0 %** (antes 21,5 %). El modelo sigue sin usar las opciones y ahora contesta D 500 veces de 789.
  - Consumo real: ~5 M de tokens de LLM grande de API, más de lo estimado (unos 100k por lote de 49 imágenes, entre instrucciones y herramientas).
- **16:51-16:58** Verificación del JSON:
  - Lo seguro: los 483 problemas sin opciones son dibujos; ninguna opción lleva basura del OCR; la respuesta correcta está siempre entre las opciones; 1.548 de 1.747 tienen las opciones confirmadas por dos fuentes independientes.
  - Lo que no se puede garantizar al 100 %: un carácter mal leído donde las dos lecturas coincidieron en el mismo error. Los 3 problemas de confianza baja están marcados.
  - 95 problemas de catalán y castellano tenían las opciones de palabras en inglés (por ejemplo «Monday» en vez de «dilluns») y se releyeron en su idioma (marcados `vision-eng` hasta entonces). El enunciado (`text`) viene tal cual de M3Kang, con el número del problema delante y algún símbolo mal renderizado (□ en vez de ∈); no se modifica, porque el JSON del jurado llegará igual.
  - Auditoría con un LLM grande de API sobre 60 problemas confirmados al azar: **60 de 60 idénticos**; tasa de error estimada por debajo del 2 %.
  - Se descubren 124 filas de catalán y castellano con opciones de palabras del OCR sin verificar contra la imagen (con basura como «E12» o «PJIN'»); tres lecturas en paralelo las corrigen.
  - **Estado final:** 4.862 problemas (3 idiomas); 4.379 con las cinco opciones; 483 dibujos marcados. Origen de las opciones: 2.771 confirmadas (LLM + OCR), 1.356 por dos lecturas del LLM, 219 leídas en su idioma y 39 corregidas o confirmadas a mano. Dos problemas tienen opciones repetidas, igual que en el examen original. Coste total de la limpieza: unos 6 M de tokens. Scripts, lecturas, correcciones y auditoría quedan documentados en la carpeta de datos para la entrega.
  - Juicio del equipo: el JSON está listo para RAG y entrenamiento, documentado para la entrega, sin garantía de 100 % sin ningún carácter mal.
- **17:05-17:06** Prueba de referencia con el 0,8B en 12 problemas de validación en inglés (niveles 0 a 7):
  - Letra directa, como el reto: **6 de 12** (~8 s estimados en la placa).
  - Razonando paso a paso: **1 de 12** (60-70 s estimados; se pasa del límite).
  - De los 6 aciertos con letra directa, 4 eran D. Contestó D en 8 de 12. Probabilidades por letra muy bajas (D 7 %, B 3 %); en muchos problemas ninguna letra entraba entre sus cinco más probables.
  - Razonando, falla por tres causas: se queda sin espacio (escribe en LaTeX con cabeceras; en 350 tokens no llega a la respuesta en 10 de 12), lee mal el enunciado y falla en el cálculo cuando el planteamiento es correcto.
  - Conclusión: el 0,8B no resuelve estos problemas ni directo ni razonando; el razonamiento largo queda descartado para este modelo. Hay margen en el formato de la pregunta y el 2B es la prueba que más información da.
- **17:09** Entrega al equipo de un paquete con el JSON limpio (zip de 0,5 MB con `train.jsonl` (4.073), `val.jsonl` (789) y `LEEME.txt`). Avisos: la licencia de M3Kang es solo para investigación (compartir por Drive o similar, no en GitHub); `val.jsonl` solo sirve para medir.

## 14/11 tarde-noche (17:12-19:50)

- **17:12-17:13** Plan siguiente: (1) probar formas de preguntar al 0,8B en los 789 de val (objetivo: pasar del 21 % al 28-30 %); (2) probar Qwen3.5-2B. Criterio: si el 2B sube a 35-40 %, se pasa a la placa; si se queda en 25 %, Python y fine-tuning.
- **17:15** Idiomas con el 0,8B: inglés 22 %, catalán 21 %, castellano 19 %. El idioma no es lo que más falla, pero hay que tenerlo resuelto. Decisiones: preguntar a la organización en qué idiomas viene el test; Qwen es multilingüe y no hace falta traducir; el RAG con `bge-small-en` (solo inglés) es el punto flojo, así que se busca un buscador multilingüe; cada problema tiene el mismo `id` en los tres idiomas, así que el ejemplo puede mostrarse en el idioma del alumno. M3Kang tiene 108 idiomas; el fichero usado tiene 14.
- **17:25-17:26** Cambio de embedding: el RAG pide los vectores a un servidor (`/v1/embeddings`). Cambiarlo supone otro GGUF, tres variables en `config.env` (`EMBED_FILE`, `EMBED_QUERY_PREFIX`, `EMBED_CTX`) y reconstruir el índice. Candidatos: bge-small-en (37 MB, solo inglés, referencia); multilingual-e5-small (~120 MB, 100 idiomas, MIT); paraphrase-multilingual-MiniLM (~120 MB, 50 idiomas); bge-m3 (~600 MB, 100 idiomas). Primera apuesta: multilingual-e5-small.
- **17:27-17:30** Con el RAG apagado (`--rag 0`, valor por defecto), el modelo solo ve el enunciado y las opciones; la base del 21 % se midió así. Con `--rag K` recibe K problemas parecidos con su letra como ejemplo. Limitaciones: solo ve la letra del ejemplo, no el procedimiento; cada ejemplo cuesta tiempo en la placa (de ~8 s a ~35 s con 3 ejemplos, estimación); el parecido es de texto, no de método.
- **17:31-17:33** Pruebas lanzadas en paralelo: RAG con bge (1, 2 y 3 ejemplos) sobre los 789 de val; cinco formas de preguntar al 0,8B (letra oficial, «The correct option is (», probabilidades por letra, valor en vez de letra, probabilidades con sesgo corregido); descarga de Qwen3.5-2B (Q8 y Q4, 3,4 GB) y de bge-m3 (600 MB). `multilingual-e5-small` no tiene GGUF accesible.
- **17:39** **Buscador: bge-m3 frente a bge-small.** Prueba: para cada problema de val en catalán o castellano (508), buscar entre los 281 de inglés y ver si aparece su traducción.
  - bge-small-en: primera posición 74 %; entre las tres primeras, 86 %; 82 problemas/s.
  - bge-m3: primera posición 100 %; entre las tres primeras, 100 %; 51 problemas/s (un 40 % más lento).
  - Decisión provisional: bge-m3, pendiente de medir memoria y tiempo en la placa.
- **17:43** **Formas de preguntar con el 0,8B (789 de val):**
  - Oficial (letra con gramática): 21,0 %.
  - «The correct option is (»: 21,8 %.
  - Probabilidad más alta entre las cinco letras: 21,0 %.
  - Escribir el valor en vez de la letra: 17,0 %.
  - Probabilidades con sesgo corregido: 20,7 %. El reparto queda casi uniforme (A 142, B 173, C 154, D 175, E 145) y el acierto no cambia: el modelo no tiene preferencia real por la respuesta correcta. Cambiar el prompt no aporta nada con este modelo.
- **17:43-17:44** **RAG con bge-small, 0,8B:** 0 ejemplos 21,0 %; 1 ejemplo 23,4 %; **2 ejemplos 24,8 %** (+3,8 puntos); 3 ejemplos 22,8 %.
- **17:44** **Qwen3.5-2B Q4, letra directa: 22,2 %**, igual que el 0,8B; contesta B 571 veces de 789 y en el nivel 0 saca un 11 %. Pedir la letra a secas no mide lo que el modelo sabe.
- **17:44-17:52** Razonamiento corto (máximo 400 tokens, terminar con «Answer: X») sobre 200 problemas de val:
  - **0,8B razonando: 23,5 %**, con 315 tokens de media (~63 s en la placa: fuera de tiempo). En 127 de 200 no llega a escribir la letra.
  - **2B Q4 razonando (400 tokens): 28,5 %** frente al 23,5 % del 0,8B en los mismos 200. Por idioma: catalán 30 %, inglés 31 %, castellano 24 %; nivel 0, 40 %. En 127 de 200 se queda sin tokens antes de la letra (~300 tokens, ~60 s en la placa).
  - **2B Q4 con 1.200 tokens de margen: 29,5 %**; en 103 de 200 no llega a la letra; gasta 700 tokens de media (más de 2 minutos en la placa). Nivel 0: 53 %.
- **18:03** Embedding elegido: **bge-m3**, con `EMBED_CTX=1024` y sin prefijo de consulta, pendiente de medir memoria y tiempo en la placa. Motivos: 100 % frente a 74 % en catalán y castellano; en RAG con un ejemplo, 24,2 % frente a 23,4 %; licencia MIT y GGUF oficial. Riesgo de memoria estimado: 600 MB de bge-m3 + ~1,3 GB del 2B Q4 + contexto ≈ 2,5 GB de 4 GB. El índice se construye en el PC y se copia a la placa (`index_m3.db`, 19 MB), porque construirlo allí tardaría más de una hora (estimación).
- **18:06-18:07** RAG con bge-m3: 1 ejemplo 24,2 %; **2 ejemplos 25,3 %** (bge-small, 24,8 %); 3 ejemplos 23,8 %.
- **18:13** **Resumen de la ronda:**

  | Prueba | Mejor resultado |
  |---|---|
  | 0,8B, letra directa (base) | 21,0 % |
  | 0,8B, cinco formas de preguntar | 21,8 % (sin efecto) |
  | 0,8B + RAG 2 ejemplos, bge-small | 24,8 % |
  | 0,8B + RAG 2 ejemplos, bge-m3 | 25,3 % |
  | 0,8B razonando | 23,5 % y fuera de tiempo |
  | 2B Q4, letra directa | 22,2 % (contesta B 571 veces) |
  | 2B Q4 razonando | 28,5 % |
  | **2B Q8 razonando** | **31,0 %** (267 tokens, ~53 s en placa) |

  - Lecciones: la letra a secas no sirve para medir ni para competir; el 0,8B está agotado (techo ~25 %); el 2B sabe más, pero no sabe rematar; el cuello de botella es la disciplina de escritura, no el conocimiento; buscador bge-m3 con 2 ejemplos.
- **18:13** Propuesta de fine-tuning por destilación sobre el 2B: un LLM grande de API genera una solución corta para cada problema de train (~4.000, en los tres idiomas), se quedan las que aciertan, LoRA en la gráfica, GGUF y medida en val. Objetivo: que termine en menos de 150 tokens y supere el 31 %.
- **18:19-18:20** Idiomas: M3Kang tiene 108; el equipo decide trabajar con tres (el README usa inglés y catalán; castellano por ser el idioma de Cataluña y probable en el test). El fichero `high_quality` descargado tiene además francés, indonesio, alemán, suajili, vietnamita, turco, chino, coreano, árabe, japonés y lituano. Recomendación: desarrollar con tres y, si el fine-tuning funciona, probar 5-6 idiomas europeos.
- **18:24-18:28** Embedding: bge-m3 acierta **508 de 508** traducciones (todos los problemas de val en catalán y castellano). Revisión a ojo de 8 problemas con sus dos vecinos: bge-m3 encuentra el mismo tipo de problema en 3 de 8, es peor en 1 de 8 y el resto son parecidos; bge-small se queda en palabras sueltas. bge-m3 está entrenado con más de 100 idiomas, pero lo comprobado son solo catalán, castellano e inglés. El modelo que responde (Qwen) puede rendir peor en idiomas raros; por eso la pregunta a la organización sigue siendo la primera.
- **18:33** Objetivo realista: **40-50 % en val, dentro de 60 s en la placa**; con un 45 % el equipo estaría probablemente entre los mejores, porque todos parten del 21 %. El 100 % no existe: el test son problemas no vistos y lo que se entrena es el método. Datos de entrenamiento: soluciones de ≤ 60 palabras que terminen en «Answer: X», generadas con un LLM grande de API; se guardan las que aciertan (mejor dos o tres por problema, la más corta que acierte). Riesgo: memorizar si la nota de train sube mucho más que la de val.
- **18:43-18:45** Idea de Arnau: que cada problema tenga una mini explicación matemática de cómo se llega a la respuesta. El equipo la acepta: el banco pasa de «problema parecido → letra» a «banco de problemas resueltos», y sirve para RAG, para fine-tuning y para enseñar. Formato: ≤ 60 palabras, estructura fija (qué pide → idea clave → cálculo → comprobación con las opciones → «Answer: X»), en el idioma del problema, con campo de tipo de problema. Coste estimado: unos 4.000 problemas, 3-5 M de tokens. Se lanza un piloto de 200 problemas; en paralelo, 8 lotes del LLM grande de API escriben explicaciones para los 351 problemas de train que el buscador recupera para los 200 de val.
- **18:50-18:51** **Explicaciones del piloto:** 351 terminadas, 188 de confianza alta y 163 baja (la mayoría porque dependen de una figura que el LLM no ve). Media de 50 palabras; todas terminan en «Answer: X».
- **18:55-18:56** Entrega del zip de embedding (16 MB): `index_m3.db` (índice de los 4.073 de train con bge-m3, para copiar a la placa sin reconstruirlo) y `LEEME.txt` (enlace al modelo bge-m3 de 605 MB, que no cabe en el zip, y las tres líneas de `config.env`).
- **19:00** **2B Q8 con dos ejemplos explicados: 34,0 %** (frente al 31,0 % razonando solo y al 22 % de la letra directa).

  | | Razonando solo | Con 2 ejemplos explicados |
  |---|---|---|
  | Aciertos | 31,0 % | **34,0 %** |
  | Tokens que escribe | 267 (~53 s en placa) | **143 (~29 s)** |
  | No llega a dar la letra | 97 de 200 | **42 de 200** |

  Por idioma: catalán 34, inglés 33, castellano 35. Los ejemplos enseñan el formato: el modelo escribe la mitad, remata el doble de veces y acierta más.
- **19:03-19:04** Análisis de 10 fallos: **9 de 10 tienen figura** y el modelo solo recibe el texto. Comportamientos observados: se rinde («sin la figura no se puede determinar»), inventa la figura, o el ejemplo recuperado se parece en palabras pero no en método. El 53 % de los problemas de M3Kang lleva figura. Caso sin figura: el reloj digital, con un ejemplo casi idéntico (parecido 0,93); la respuesta era 10 y el modelo contestó 12. Conclusión: el RAG da el método, no la respuesta; el modelo tiene que ejecutarlo con sus números.
- **19:04** Causas y arreglos: no ve la figura (la mayoría) → visión con el mmproj del 2B; se rinde o inventa datos → fine-tuning; ejecuta mal el método (cuentas) → Python; ejemplo parecido en palabras y no en método → buscar por tipo de problema.
- **19:09-19:11** Separación por tipo de problema y configuraciones de la tanda (200 de val, RAG con 2 ejemplos explicados):

  | Modelo | Aciertos | Tokens | Sin rematar |
  |---|---|---|---|
  | **2B Q8** | **34,0 %** | 143 | 42/200 |
  | 2B Q4 | 29,0 % | 168 | 56/200 |
  | 0,8B Q8 | 27,5 % | 137 | 39/200 |
  | 2B Q8, letra directa | 21,5 % | 1 | — |

  - Solo con explicaciones de confianza alta (el resto con la letra): 34,5 %; 168 tokens; 60 sin letra. Lo que más aporta es el formato: dos ejemplos cortos que terminan en «Answer: X».
- **19:18** **Separación por figura (2B Q8, RAG explicado, 200 problemas):** sin figura, 88 problemas y **43 %**; con figura, 112 problemas y **28 %**. Sin RAG y con el mismo prompt corto: texto 40 %, figura 30 % (34,5 % global en ambos casos). Lo que más subió (del 31 % al 34,5 %) fue el **prompt corto** («≤ 60 palabras, termina en Answer: X»), no el RAG, que no cambia la nota de forma medible (±3-4 puntos de ruido). Sin RAG: 179 tokens; con RAG: 142 tokens y la mitad de respuestas sin rematar (46 frente a 73). Los problemas con figura quedan en el azar (28-30 %).
- **19:18-19:25** Estado: base 21 % → **34,5 %** con 2B Q8 + prompt corto + RAG explicado, ~28 s por problema en la placa (texto 43 %). Pendientes: (1) preguntar a la organización si el test trae imágenes; (2) explicaciones para todo train, con imagen en los problemas con figura (6-8 M de tokens, con un LLM grande de API para los difíciles); (3) fine-tuning del 2B con esas explicaciones, que podría llevar el texto del 43 % al 50-55 % (estimación); (4) medir tokens/s del 2B Q8 en la placa y si cabe bge-m3.
- **19:25** Resumen del día: material descargado y verificado (9,3 GB); OCR en 12 min; JSON limpio (90 % con opciones); nota base 21 %; formas de preguntar sin efecto; bge-m3 elegido (100 % frente a 74 % en catalán y castellano); 2B probado (mejor, pero se alarga); piloto de explicaciones con RAG (34,5 % global, 43 % en texto, ~28 s); guion de descarga para repetirlo todo en otro equipo.
- **19:34** Con el mejor sistema (2B Q8, prompt corto, RAG con dos ejemplos explicados), sobre 200: sin figura, 43 % (88 problemas); con figura, 28 % (112). Sin RAG: 40 % y 30 %. Azar: 20 %. Los problemas con figura cuestan unos 8 puntos en la nota global. Si el test trae imagen, la siguiente prueba es la visión del 2B (mmproj); si no la trae, los problemas con figura son imposibles para todos por igual.
- **19:37-19:38** Análisis de 12 fallos sin figura: **4 por enumerar sin espacio** (se acaban los 300 tokens a mitad de la lista); **4 por leer mal o inventar condiciones** (dragón de nivel 1, gato, aviones de papel); **2 por planteamiento que excede el nivel** (nivel 6); **2 por método correcto y cuenta mal** (reloj: 12 en vez de 10; pulseras: 24 en vez de 28). Lectura: 6 son de ejecución, 4 de lectura y 2 de «no da para más».
- **19:40-19:44** **Programa Python por problema:** el modelo escribe un programa corto que calcula la respuesta; se ejecuta aislado (3 s como máximo) y el resultado se casa con las opciones (entiende fracciones, raíces, unidades y decimales con coma). Si falla, se cae al sistema anterior (razonamiento corto con RAG explicado). Defectos de la primera prueba, corregidos: el modelo copiaba la función del ejemplo, se quedaba sin tokens antes de cerrar el bloque de código y llenaba el programa de comentarios. Ajuste: dos ejemplos cortos sin funciones, «máximo 20 líneas, sin comentarios» y más margen de tokens.
- **19:45** **Idea de Arnau:** tener para cada problema de train un sistema Python «lo más masticado posible». El equipo lo adopta por una razón: **el código se verifica solo**. Se ejecuta y se comprueba que imprime la opción correcta; si no, se descarta o se regenera. Así el banco tiene soluciones demostrablemente correctas. Usos: en el RAG, el modelo adapta un programa en vez de inventarlo; en fine-tuning, el dataset es problema → código correcto; para enseñar, el código da pistas paso a paso. Límite: los problemas con figura.
- **19:45-19:47** Formato de tres capas por problema de train: pasos (3-5 líneas, pista para el alumno), código verificado y letra. En el RAG se muestran pasos y código del problema parecido; al alumno, solo los pasos. Precaución de tiempo: cada ejemplo con pasos y código añade ~150 tokens (~14 s en la placa); con dos entra, con tres no.
- **19:47** **Test de 100 (50 con figura, 50 sin)** sobre el 2B Q8, con cuatro configuraciones: A) letra directa; B) razonamiento corto sin RAG; C) RAG con dos ejemplos explicados; D) Python con fallback. En paralelo, 6 lotes del LLM grande de API escriben código para los **244 problemas del piloto**; se añadirá la configuración E) RAG con código verificado.
- **19:47-19:49** Llegan los primeros lotes de código (41 problemas por lote; `needs_figure` true en 28 de 41 en el primero y en 17 de 41 en el segundo).
- **19:48** Verificación de los dos primeros lotes ejecutando el código: **36 de 36 programas** de problemas sin figura imprimen la opción correcta; los de figura (45 de 81) imprimen `None`, como se pidió cuando no pueden resolverse. Las evaluaciones van lentas porque comparten la gráfica.

## 14/11 noche (19:50-21:12)

- **19:50** Verificación del código masticado del piloto: de los **244 problemas**, **128 no necesitan figura** y el programa acierta en **123 (96 %)** al ejecutarlo; los 5 restantes fallan por tiempo o por un detalle del enunciado y se descartan. Los 115 que dependen de figura imprimen `None`. Se lanza la configuración **E**: Python con ejemplos de código verificado de los dos problemas más parecidos, sobre el test de 100.
- **19:54-20:02** Un informe externo sobre modelos para interpretar imágenes en la placa (UNO Q, 4 GB, ~3,6 GB utilizables) propone un OCR especializado PP-OCRv5 mobile (~20-25 MB), Qwen3.5-0.8B con `mmproj` (+205 MB sobre el 0,8B de 835 MB; 28-38 s por problema con `--image-max-tokens 128`, 68-185 s sin ese límite), un VLM aparte (SmolVLM2) y LightOnOCR (descartado por ser OCR de documentos). Valoración del equipo:
  - La lectura de opciones ya no es el problema: el JSON está al 90 % y la organización confirmó que el test trae opciones completas. RapidOCR mete basura en fracciones y raíces.
  - Lo que falta es entender la figura (53 % de problemas, con 28 % de acierto). Un OCR no sirve para eso; hace falta un modelo que vea. Opción preferida: Qwen con `mmproj` (2B: 670 MB de proyector; 0,8B: 205 MB). SmolVLM podría servir como descriptor de la figura.
  - Si el test no trae imágenes, nada de esto importa. Si las trae, se mide en el PC con 2B + mmproj y 0,8B + mmproj sobre 50 problemas de figura.
  - Correcciones al informe: `data/images/` tiene 4.862 imágenes, no 49. El presupuesto de RAM debe contar el 2B en Q8 (2,1 GB): 2B Q8 + bge-m3 + mmproj del 2B ≈ 3,4 GB, no cabe; con visión habría que elegir entre 2B Q4 o 0,8B + mmproj.
  - **Entrega (20:00-20:02):** zip de 16 MB con 21 ficheros para el resto del equipo: `data/` (`train.jsonl`, `val.jsonl` limpios e `index_m3.db` vectorizado), `experimentos/` (351 explicaciones, 244 programas verificados, scripts de evaluación y `RESULTADOS.md`) y `LEEME.txt`. Los modelos (Qwen3.5-2B Q8, 2,1 GB, y bge-m3, 605 MB) se bajan aparte. Avisos: licencia de M3Kang; las explicaciones y el código solo cubren el piloto, así que las pruebas comparables son con `--limit 200` o `--balanced 50`.
- **20:02-20:06** Ideas tomadas de un proyecto anterior del equipo (un modelo pequeño que resolvió problemas parecidos), por orden de utilidad:
  1. Reglas en código, no en el prompt, con verificador y reintento dirigido (`guard.py`): si el código falla, reintentar con el error; si el resultado no está entre las opciones, reintentar; si no termina en «Answer: X», pedir solo la letra; si el modelo dice que no puede por la figura, no gastar tokens. Dato medido: en el modo Python de la prueba E, 60 % de aciertos cuando el código produce un valor válido, pero solo en 25 de 100 problemas; en 53 la salida no casa con las opciones y en 16 hay error.
  2. Razonar solo cuando hace falta, decidido por código (enrutador: texto numérico a Python, texto no numérico a razonamiento corto, figura lo más barato).
  3. Regla de «no inventar» aplicada a las figuras.
  4. Buscador híbrido (vector + tipo de problema + nivel) y reranker (en el proyecto anterior, +20 puntos en preguntas nuevas).
  5. Método de medida: ablaciones una a una, muestra fija, examen que distinga.
- **20:08-20:11** **Test de 100 (50 con figura, 50 sin), 2B Q8:**

  | Configuración | Total | Con figura | Sin figura |
  |---|---|---|---|
  | A) Letra directa (base del reto) | 23 % | 24 % | 22 % |
  | B) Razonamiento corto, sin RAG | **40 %** | 40 % | 40 % |
  | C) RAG con 2 ejemplos explicados | 35 % | 32 % | 38 % |
  | D) Python con 2 ejemplos fijos + fallback | 35 % | 30 % | 40 % |
  | E) Python con código masticado de 2 parecidos + fallback | **41 %** | 32 % | **50 %** |

  - Razonar en vez de dar la letra: +17 puntos.
  - En texto, el código masticado es lo mejor (50 %). Cuando el modelo consigue un programa que da una opción válida, acierta el 60 %, pero solo lo consigue en 25 de 100.
  - En figura, ninguna configuración pasa del 30-40 %.
  - El RAG con explicaciones de texto no gana a razonar solo (35 frente a 40): aporta disciplina (menos tokens), no aciertos.
  - La heurística de la mediana (en train, la respuesta es el valor central de las cinco opciones el 30 % de las veces y uno de los tres centrales el 79 %) suma unas veces +4 y otras −5 en figura: se descarta como sustituto.
  - Con 50 problemas por grupo, el ruido es de ±7 puntos.
- **20:13** Qué nos hace fallar: la figura (50 % de los problemas), que no se arregla con software; y el texto (50 %), donde en 3 de cada 4 problemas el 2B no consigue un programa válido y cae al razonamiento (40 % de acierto).
- **20:26-20:27** Acceso a alquiler de GPUs en vast.ai: la cuenta está configurada en el PC y no hay máquinas alquiladas. Referencia de precio: una RTX 4090 ronda 0,35-0,50 $/h. Plan: primero LoRA en la gráfica local para validar la tubería; después, lanzar 4 variantes a la vez en GPUs alquiladas.
- **20:29** Análisis de las 59 de 100 pérdidas de la configuración E: no ve la figura, ~34 de 100; no consigue un programa válido y cae al razonamiento que falla, ~20; programa válido pero equivocado, ~5. Es decir: 57 % de lo que se falla es la figura y 35 % es que el 2B no traduce bien el enunciado a código.
- **20:30-20:35** Propuesta de Arnau: alquilar una GPU potente y montar en paralelo muchos modelos con distintas configuraciones, una vez validado el reto. Setup en la carpeta `nube` del equipo, reutilizando la infraestructura de alquiler del proyecto anterior (CLI de vast.ai, entrenador y vigía). Oferta: **RTX PRO 6000 de 96 GB desde 1,14 $/h**. Flujo: alquilar; arrancar (sube repo, datos y scripts; compila llama.cpp en el commit del reto; bge-m3 en marcha); lanzar 4-5 trabajos a la vez (LoRA, unir, GGUF Q8 y Q4, examen sobre los mismos 200 problemas); vigilar; traer resultados y apagar la máquina; descargar el ganador a la placa.
  - Matriz inicial: `2b_codigo` (¿aprende el 2B a escribir el programa?), `2b_mixto`, `2b_codigo_3ep` y `2b_codigo_r32`, `08b_codigo` (¿basta el 0,8B entrenado?) y `4b_codigo` (techo).
  - Coste estimado: 6 LoRA de un 2B con ~3.600 ejemplos, de 4 en 4, más exportar y examinar: 1,5-2,5 horas, **2-4 $**.
  - Antes de alquilar: datos completos de todo train (~3.600 problemas con opciones de texto; ~60 lotes del LLM grande de API, 8-10 M de tokens; el piloto tiene 354 ejemplos de código y 299 de explicación) y una prueba local de 20 pasos de LoRA del 0,8B.
- **20:39** Petición de Arnau: perfeccionar todo el sistema, probar modelos que quepan en la placa, mejorar el RAG con mucho testing y entrenar con LoRA (o entero, si el 0,8B parece ir bien) cuando el RAG deje de ser el problema. Usar un LLM grande de API para preparar los JSON completos o parciales y analizar siempre los errores.
- **20:56** Estado de la campaña:
  - Código para todo train: 32 lotes hechos. **766 de 853 programas de texto son correctos (90 %)**; con figura, `None`.
  - Explicaciones para todo train (3 idiomas): 50 de 71 lotes hechos o en curso; casi todas con confianza alta.
  - Hallazgo: **17 problemas donde el programa correcto da otra opción que la etiqueta de M3Kang**, casi todos del bloque `lvl-4_2022_*`. Son etiquetas erróneas; quedan fuera del entrenamiento y se anotan en un fichero de etiquetas sospechosas.
  - Sistema completo (enrutador, Python con código parecido, reintentos y fallback): **41 %** en el test de 100 (texto 50 %, figura 32 %). Los reintentos con el error delante no suman: el 2B no sabe corregir su código.
  - Tiempo en placa estimado (11 tokens/s leyendo, 5 escribiendo): media de **120-155 s por problema**; **75 de 100 pasan de 60 s**. Los dos ejemplos del RAG son lo que más cuesta leer. Conclusión: hace falta un fine-tuning que resuelva sin ejemplos y escribiendo poco.
  - Modelos que caben en la placa: Qwen3-1.7B y Qwen2.5-Math-1.5B descargados y evaluándose con el mismo sistema.
  - Tubería de entrenamiento local validada (20 pasos de LoRA del 0,8B en la gráfica, pérdida bajando).
- **21:03-21:11** Explicaciones en paralelo (tope de 20 lotes a la vez):
  - Texto: terminado, **1.925 explicaciones**, 95 % con confianza alta (1.833 high / 92 low).
  - Figura: los lotes se rehacen **viendo la imagen**: 376 explicaciones con ~85 % de confianza alta, frente a ~30 % cuando no se veía la figura. Después, 840 explicaciones de figura con imagen; la proporción de confianza alta en figura pasa de ~30 % a ~54 % y sigue subiendo.
  - Script `resumen_explicaciones.py` que junta los lotes en `explicaciones_total.jsonl`; si un problema aparece dos veces, se queda la versión que vio la imagen.
  - Etiquetas sospechosas confirmadas por una segunda vía: todo el bloque `lvl-4_2022_*` (5, 11, 12, 17, 25, 26), más `lvl-7_2017_28/30`, `lvl-7_2018_27`, `lvl-7_2015_11/30` y `lvl-5_2012_14`. Quedan fuera del entrenamiento.
  - **Comparación de modelos con el sistema completo (test de 100, Q8):**

    | Modelo | Total | Figura | Texto |
    |---|---|---|---|
    | Qwen3.5-2B | 41 % | 32 % | 50 % |
    | **Qwen3-1.7B** | **45 %** | **44 %** | 46 % |
    | Qwen2.5-Math-1.5B | 36-39 % | 26-28 % | 50 % |

    Qwen3-1.7B (1,8 GB) iguala o supera al 2B y razona mejor en figura. Math-1.5B escribe buen código pero se salta el formato y suelta la letra. Se lanza el 1.7B sobre los 200 para confirmar.
  - Hito de la noche: **0,8B con el sistema completo, test de 100: 33 %** (frente al 23 % con letra directa). **1.7B en los 200: 42 %**.
- **21:09** Estado de la alquiladora: la máquina de 96 GB (RTX PRO 6000, 1,14 $/h en California, la más barata en ese momento) la alquila Arnau con el comando del equipo; a partir de ahí, el arranque, la vigilancia y la recogida de resultados se hacen con los scripts. `configs.json` queda con el 1.7B como prioridad: `17b_mixto`, `17b_explicacion`, `2b_mixto`, `08b_mixto`, `17b_codigo`, etc. (10 trabajos; la máquina corre 5-6 a la vez). `preparar_datos.py` usa `explicaciones_total.jsonl`, prefiere la versión con imagen, solo confianza alta y excluye ~110 filas de etiqueta dudosa: 2.781 ejemplos de explicación, 2.102 de código y 2.044 mixtos. En local: descarga del Qwen3-1.7B y 20 pasos de LoRA de 4 bits para validar la plantilla de Qwen3 (`enable_thinking=False`, igual que `--reasoning off` en la placa). Servidores del 0,8B, 2B y Math parados.
- **21:11-21:12** Terminan todos los lotes; fusión final y regeneración de los datos de entrenamiento.

## 14/11 noche - alquiler de la máquina y campaña masiva (21:13-22:45)

- **21:13** Balance: explicaciones de todo train terminadas: **3.684** (texto 95 % de confianza alta; figura 78 % viendo la imagen, frente a 30 % sin verla). Datasets de entrenamiento regenerados: **3.037 explicación / 2.099 código / 2.057 mixto** (+5 % de val por id), solo confianza alta y sin 114 filas de etiqueta dudosa. Paquete para el equipo: `explicaciones_m3kang.zip` (2 MB). El 1.7B razonando sin ayuda saca solo **27,5 %** en los 200 (se corta 64 veces y contesta A 102 veces); con el sistema, 42 %.
- **21:14-21:16** El comando de alquiler no encontró la oferta indicada, que ya no estaba disponible («No encuentro ninguna oferta»); no se alquiló nada ni se gastó. Nueva oferta: Japón, 96 GB, 4,5 Gb/s de bajada, **1,335 $/h**.
- **21:15** Motivo de otra máquina: tiempo, no capacidad. La 5060 Ti (8 GB) solo entrena un LoRA a la vez y en 4 bits; el 1.7B con 2.000 ejemplos × 2 épocas son ~2-3 h por configuración, y los 10 trabajos serían un par de días. Una RTX PRO 6000 de 96 GB corre 5-6 LoRA a la vez sin cuantizar; toda la campaña, unas 2 h, por **2-4 $**.
- **21:17** La organización del equipo autoriza alquilar una máquina grande para decenas de pruebas con distintos sistemas y análisis de errores.
- **21:21** **Máquina alquilada:** vast.ai, **RTX PRO 6000 de 96 GB, India, 1,34 $/h**. Arranque: sube repo, datos y scripts; compila llama.cpp con CUDA; instala el entrenador (10-15 min); lanza los **10 LoRA** de `configs.json` de 5 o 6 en 5 o 6, cada uno con exportación a GGUF Q8/Q4 y examen en los 200. En paralelo: techos con Qwen3-4B, Qwen3-4B-Instruct-2507, Qwen3.5-4B y Qwen3-8B con el sistema completo; el 1.7B y el 4B pensando (presupuesto de 1.200 tokens); y el 1.7B en Q4_K_M. En la torre: pasada de los 789 de val guardando la traza de cada problema, para que un LLM grande de API clasifique cada fallo.
- **21:21-21:23** Plan de uso de la gráfica: `lanzar.py` mete trabajos hasta llenar 90 GB (5-6 LoRA a la vez, de 10-18 GB cada uno) y las evaluaciones extra en paralelo (≤ 9 GB); vigilancia con `nvidia-smi` y trabajos adicionales si baja la utilización del 85-90 %. Idea de Arnau: usar también la CPU de la máquina para lo que no requiera IA, como buscar la combinación óptima de respuestas.
- **21:27** Torre: el LoRA de prueba del 1.7B va bien (pérdida 2,85 → 1,08, 3 s por paso). Se lanza el **LoRA completo del 1.7B mixto en la 5060 Ti** (QLoRA 4 bits, 2 épocas, ~1 h).
- **21:27** **Primer resultado de CPU: duplicados entre train y val.** El Canguro repite enunciados entre niveles (el mismo problema en lvl-2 y lvl-3 del mismo año). Para cada uno de los 789 de val, se busca el vecino más parecido en train con bge-m3:
  - Parecido ≥ 0,95: 33 casos; copiar la etiqueta acierta el 67 % (hay enunciados idénticos con opciones distintas, por ejemplo `lvl-0_2024_1` ≡ `lvl-1_2024_1`).
  - Parecido ≥ 0,85 **y las mismas 5 opciones**: **19 casos (2,4 %), 100 % de acierto**.
  - Se integra como «paso 0» del sistema (`duplicado`): responde en 0 s sin tocar el modelo. Estimación: +2 puntos si el test se parece a val.
- **21:29** Incidencia en la nube: la preparación falló en `pip` (la imagen de PyTorch 2.11 tiene Python «gestionado» y rechaza instalar sin `--break-system-packages`). Corregido y relanzado. La máquina tiene además **152 núcleos de CPU y 4 TB de RAM**: `evals_extra.sh` corre dos cadenas, una en GPU (≤ 9 GB: Qwen3-4B, Qwen3-4B-Instruct-2507, Qwen3.5-4B, Qwen3-8B y el 4B pensando) y otra en CPU (32-48 hilos: 1.7B en Q4_K_M y 1.7B pensando).
- **21:32** Petición de Arnau: probar muchas combinaciones de modelos y estructuras de JSON, buscando el porcentaje de respuestas más alto, sobre todo en preguntas sin figura.
- **21:37** Nube lista: llama.cpp compilado y `lanzar.py` arranca los LoRA (`17b_mixto` el primero). **Rejilla de 18 variantes** para los problemas sin figura (`eval_variantes.py`; 1.7B Q8 con 8-16 peticiones en paralelo sobre ~370 problemas de texto de val, y después el 2B): cuántos ejemplos de código (`k0`, `k1`, `base` con 2, `k3`); qué ejemplos (`tipo`: vecinos del mismo tipo); estructura del prompt (`json`, `json_tras_codigo`, `valor` para pedir el valor numérico y casarlo con las opciones, `pasos`, `ingles`); solo razonar (`razona_k0`, `razona_k2`, `razona_k4`); combinaciones (`razona_primero`, `voto_mixto`, `verifica`); votación como techo (`voto3_codigo`, `voto3_razona`). Probada con 4 problemas en local.
- **21:46** **9 LoRA entrenando a la vez** en la nube (17b mixto, explicación y código; 17b con 3 épocas y r32; 2b mixto, explicación y código; 08b mixto y explicación; el 4b entra cuando haya hueco). Gráfica al 100 %, 50 GB usados. Torre: pasada de val por 750 de 789 (35 %). Se deja `combinar_variantes.py` (solo CPU) para buscar votaciones entre 3-5 variantes y enrutado por nivel o idioma con validación cruzada.
- **21:51** **Pasada completa de val (789) con el 1.7B y el sistema actual: 35,5 %** (texto 46 %, figura 27 %). Los 200 daban 42 % por ruido de muestreo; a partir de aquí la referencia son los 789.
- **21:51-21:53** Los **509 fallos** se trocean y entre 20 y 21 lotes de un LLM grande de API los clasifican por causa (modelado, cálculo, cortado, formato, casado de opciones, error de código, sesgo de letra, idioma, figura imprescindible, etiqueta dudosa) y por arreglo, resolviendo cada problema por su cuenta para detectar etiquetas malas. Patrón: en texto manda «modelado»; en figura, «figura imprescindible». Etiquetas dudosas detectadas, por ejemplo: `lvl-2_2017_17`, `lvl-4_2022_27/29`, `lvl-5_2023_30`, `lvl-5_2018_20`.
- **21:58** **Mapa de fallos del 1.7B** (508 fallos de val):
  - Sin figura (188 fallos de 349): modelado **61 %**; cálculo 11 %; sesgo de letra 11 % (programas que imprimen una constante o `print('B')`); error de código 7 % (por ejemplo, `Fraction` o `comb` sin importar, bucles de 10⁹); cortado, casado y formato, 3 + 3 + 2 %; etiqueta dudosa 3 %.
  - Con figura (320 de 440): 70 % imposibles sin ver el dibujo; 19 % modelado.
  - Arreglo ya hecho en CPU, sin tocar el modelo: preludio de imports antes de ejecutar cada programa y casador de unidades (€, %, km/h). Simulado sobre las trazas: la vía Python pasa de 92 a **101 aciertos** (+1,1 puntos). Rechazar programas «cableados» quita 27 fallos pero también 14 aciertos: neutro, descartado.
  - Conclusión: con ingeniería se rascan ~2 puntos; el 60 % de «modelado» solo lo mueve un modelo mejor o ejemplos del mismo tipo. La rejilla en la nube se prioriza y se acelera (16 peticiones en paralelo). `base` da 43 % en los 349 de texto. El 2B sale de la rejilla para no alargar el presupuesto de cómputo.
- **22:06** Estado de la nube: `17b_codigo` y `17b_mixto` entrenados (pérdida final 0,33 y 0,67), exportados y en examen; techos (primeros 50 de 200): Qwen3-4B Q8 54 %, 1.7B Q4_K_M en CPU 40 %. Torre: LoRA local en la época 2. Pérdidas finales de la campaña: código 0,33; mixto 0,67; explicación 0,97-0,99.
- **22:08-22:09** Pregunta sobre modificar el modelo interno (podar o moldear). Análisis:
  1. **Full fine-tuning** (todos los pesos, sin LoRA): factible; el 1.7B en bf16 ocupa 3,4 GB y con optimizador ~25 GB; ~20 min por pasada. Expectativa frente al LoRA r16 con 3.000 ejemplos: +0 a +3 puntos, con riesgo de olvidar matemáticas generales.
  2. **Podar** capas o cabezas: no. El cuello de botella en la placa es el prefill de los ejemplos (200 s de media por el RAG), no el tamaño del modelo.
  3. **Refuerzo con recompensa verificable (GRPO):** el modelo genera varias soluciones por problema; se extrae su letra o se ejecuta su código, y recibe recompensa si acierta. Con 3.600 problemas de train, 1-3 h de máquina. Expectativa: +5 a +10 puntos en texto sobre el SFT. Riesgos: 2-3 h de montaje, etiquetas malas (~3 %) y el techo de conocimiento (el 4B marca el techo: 54 % con el mismo sistema).
  4. Fusionar Math-1.5B con Qwen3: no se puede (tokenizadores y arquitecturas distintas).
  - Recomendación: esperar a los exámenes de los LoRA; si el SFT da el salto, una pasada de full fine-tuning y, si hay tiempo disponible, GRPO.
- **22:17** El LoRA local del 1.7B termina en la torre (55 min; pérdida 0,73 → eval 0,75; **80 % de acierto por token**). Queda validada la tubería de entrenamiento de punta a punta. El adaptador se guarda; no se exporta porque el entreno en bf16 viene de la nube ya examinado.
- **22:23** Aclaración: el 80 % es **acierto por token** (el modelo predice bien 8 de cada 10 palabras de la explicación). Mide estilo y formato, no resolución de problemas. El número que importa es el acierto de letra en val. Referencia a batir: 1.7B sin entrenar, 42 % en los 200 y 35,5 % en los 789 (texto 46 %).
- **22:37** **Primeros números de la rejilla de variantes** (1.7B Q8, los **349 problemas de texto de val**):

  | Variante | Acierto | s/problema en placa | Lectura |
  |---|---|---|---|
  | `base` (2 ejemplos de código + razona) | 43,0 % | 212 | referencia |
  | `k0` (sin ejemplos) | 43,6 % | **145** | los ejemplos no aportan precisión, solo tiempo |
  | `k1` (1 ejemplo) | 47,3 % | 157 | con el preludio de imports y el casador nuevo: Python 105/172 |
  | `tipo` (ejemplos del mismo tipo) | 45,3 % | 205 | ayuda poco |
  | **`valor`** (pide el valor numérico y lo casa con las opciones) | **48,7 %** | 206 | **+5,7 puntos**: quita el sesgo a la «A» |
  | `json` (entrada y salida en JSON) | 37,8 % | 157 | peor; descartado |

  - Estructura ganadora: pocos o ningún ejemplo, código y «dime el valor, no la letra». Se encolan `k1_valor` y `k0_valor`, y versiones recortadas a 300 y 220 tokens para caber en 60 s.
  - **Techos** (200, sistema completo): Qwen3-4B Q8 **47 %** (texto 56 %, figura 40 %) frente al 1.7B Q8 con 42 %; el 1.7B en **Q4_K_M cae a 36 %** (−6). Si va a la placa, Q8 (1,8 GB) o Q5/Q6, no Q4.
- **22:38** Desglose sobre val (789) para fijar expectativas, a petición de Arnau (que pide un 100 % con entrenamiento o lógica):
  - **56 % de los problemas tienen figura**; el modelo está en 27 %, casi azar. Ningún entrenamiento sobre texto lo arregla.
  - **44 % son de texto**: 43 % → 49 % solo con pedir el valor en vez de la letra; el 4B hace 56 %.
  - **~3 % de etiquetas de M3Kang están mal** (comprobado por dos vías): máximo teórico ~97 %.
  - Objetivo realista: texto 55-60 % (1.7B afinado, valor y verificación de opciones; 60-65 % si cabe el 4B); figura sin imagen 30-35 %; **total ~45-48 %**, frente al 21 % de la letra directa inicial.
- **22:43** Por qué el texto no llega al 100 %: los problemas son de competición y la dificultad es de contenido. 61 % de los fallos de texto son de comprensión (ejemplos de las trazas: confunde la diagonal con el lado; supone 36 caras donde hay 50; divide por g² en vez de g³; ignora que dos corredores se cruzan). Presupuesto de la placa: 60 s a 5 tokens/s son **~300 tokens escritos**, y antes hay que leer el enunciado (10-25 s); un problema de nivel 6-7 bien razonado necesita 500-1.500 tokens. Etiquetas malas ~3 %. Lo que sí se puede mejorar: valor, ejecución de programas, verificación de opciones, votación, duplicados (+2) y fine-tuning para escribir corto (+3-8). Conclusión: 50-60 % en texto con un 1,7B en una placa de 4 GB es un resultado muy bueno.
- **22:44** **Aclaración de la organización: el texto oculto NO incluye las imágenes.** Consecuencia: nadie ve las figuras, así que la ingeniería de texto cuenta más.
- **22:45** Sesgos medidos en train (CPU) que se pueden explotar:
  - Problemas con figura (56 % del test): un 30 % se resuelve solo con el texto. Las opciones que son dibujos (20 % de los de figura) tienen como correcta **D en el 30 %**, E en el 24 % y A solo en el 12 % (contestar D vale 30 % frente al 20 % del azar, sin coste de tiempo).
  - Opciones numéricas: la correcta es el valor central el **30 %** de las veces y uno de los tres centrales el **78 %**; los extremos, 10 % y 13 %. Regla: si el modelo propone un extremo sin cálculo que lo sostenga, se usa la mediana.
  - Duplicados de train: etiqueta directa.
  - Estimación: la figura puede pasar del 27 % a ~32-35 % sin gastar tiempo de placa.
  - **Sistema final propuesto, en orden de coste:** (1) duplicado de train con mismas opciones → etiqueta (0 s); (2) opciones vacías o dibujos → D (0 s); (3) figura imprescindible y opciones numéricas → intento corto con valor; si no casa o es un extremo, mediana (≤ 25 s); (4) texto: código (0-1 ejemplos) → valor casado → verificación de opciones, con presupuesto duro de 55 s y fallback a mediana o D. Total estimado: **46-50 %** con el 1.7B, y más con el 4B.

## 14/11 noche - texto como prioridad y segunda máquina (22:47-23:34)

- **22:47** Variantes nuevas de texto:
  - `razona_primero` (razona y código, prefiere el acuerdo): **44,1 %**. Cuando código y razonamiento coinciden, aciertan el **76 %** (65/86): señal de confianza para decidir cuándo gastar más tiempo.
  - `ingles` (reformular en inglés antes): **44,7 %** (+1,7 sobre la base).
- **22:48** Pedir la letra directa cuesta 6 puntos medidos en 349 problemas: el modelo calcula un valor y el sistema lo traduce a letra.
- **22:49** **Decisión: se eliminan los priors por letra** (la D del 30 % en dibujos). El sistema responde con el razonamiento del modelo, y lo que no se puede razonar se queda como está. Desglose de fallos en los 789 de val (clasificados uno a uno):
  - Figura imprescindible: **223**. Sin arreglo.
  - El modelo plantea mal el problema (texto y figura resoluble): **176**. Arreglo parcial: modelo mayor (el 4B suma +7 en texto), fine-tuning, verificación de opciones, más tokens.
  - Error de cálculo: **32**. Arreglo parcial: código en vez de cálculo mental, verificación de opciones.
  - Elige una letra sin calcular: **24**. Arreglo: pedir el valor en vez de la letra (+5,7 medido) y rechazar programas que no calculan.
  - Código que no se ejecuta o se corta: **29**. Arreglo: preludio de imports (hecho), más tokens, reintento con el error.
  - Casado con opciones o formato: **15**. Arreglo: casador nuevo (hecho).
  - Etiqueta mal en M3Kang: **8**. Techo 97 %.
- **22:49** **Foco: solo problemas de texto**, para tenerlos resueltos el día del examen (15/11). Plan: leer los 9 LoRA; rejilla final solo en texto (349 problemas) con `k1_valor`, `k0_valor`, recortes a 60 s, verificación de opciones, reintento dirigido y votación; combinar con CPU; 4B en Q4 y 1.7B pensando si queda margen; `predict.py` final fuera del repo oficial; medir en la placa con App Lab; pasada completa de val en la torre. Pendiente: la hora del examen y la disponibilidad de la placa.
- **22:51** Criterio del equipo: primero un modelo que rinda muy bien; la placa se usa cuando el modelo tenga resultados sólidos. Objetivo: **texto ≥ 60 % en val con el 1.7B** antes de pasar a la placa. Dos palancas: entrenamiento (LoRA y luego GRPO con la etiqueta como recompensa) y estructura de inferencia (valor, verificación, reintento y votación).
- **22:52** Elección del 1.7B, con el mismo sistema (200 de val):

  | Modelo | Tamaño Q8 | Acierto | Nota |
  |---|---|---|---|
  | Qwen3.5-0.8B | 0,9 GB | 33 % | rápido, flojo |
  | Qwen2.5-Math-1.5B | 1,6 GB | 36-39 % | buen código, se salta el formato |
  | Qwen3.5-2B | 2,1 GB | 41 % | |
  | **Qwen3-1.7B** | **1,8 GB** | **42 %** (49 % en texto con «valor») | mejor relación tamaño/acierto |
  | Qwen3-4B | 4,4 GB (no cabe) / 2,5 GB Q4 | 47 % | +5, pero lento y justo de RAM |

  Descartados por criterio: Llama 3.2 1B/3B y Gemma 3 1B (peores en matemáticas); DeepSeek-R1-Distill-1.5B (piensa cientos de tokens; no cabe en 60 s); Phi-4-mini (3,8B; no cabe en memoria). El 1.7B tiene modo *thinking* y pesos abiertos para entrenar. Velocidad real en la placa: pendiente (estimada ~6 tokens/s de lectura y 3 de escritura).
- **22:53-22:54** ¿Es matemáticas? Es matemática elemental con razonamiento de varios pasos y trampas de lectura; el 4B, con el mismo sistema, hace 56 % en texto. El cuello de botella son las evaluaciones, no la memoria. Propuesta: una RTX 4090 (24 GB) a ~0,35 $/h (una 3090, ~0,20) para toda la rejilla de texto; la de 96 GB, solo para entrenar.
- **22:59-23:02** Se alquila una segunda máquina: **RTX 3090 (24 GB) a 0,16 $/h** (México; la 4090 más barata estaba a 0,44 $/h). Trabajo: `investigar.sh` solo con problemas de texto (349): 1.7B Q8 con las variantes principales; 4B Q8 con `k1_valor`, `k0_valor`, `valor`, `base` y `k0`; 4B Q4_K_M con `k1_valor` y `k0_valor_corto`, con velocidad estimada de placa (3 tokens/s leyendo, 1,5 escribiendo). Gasto de referencia: ~1,34 $/h + 0,16 $/h.
- **23:04-23:08** Causas de fallo en texto (188 fallos):
  1. Plantea otro problema (61 %): toma la diagonal por el lado, olvida una condición, cuenta 36 caras donde hay 50, responde a la pregunta de al lado.
  2. Contesta sin calcular (11 % sesgo de letra y 11 % cálculo): programas que imprimen una constante, afirmaciones sin paso, aritmética mal hecha.
  3. Fallos mecánicos (≈ 17 %): código que no se ejecuta (`Fraction` sin importar, `str+int`, bucles eternos), se queda sin tokens a los 300, o el valor correcto no casa con la opción («22,5 km/h», «2,80 €»).
  - Peso de cada causa: mecánicos, 8 % del total de texto (+5 a +7 puntos); contesta sin calcular, 12 % (+5 a +6); plantea otro problema, 33 % (+7 a +10). Suma estimada: de 43 % a **60-65 %**.
- **23:08** Forma de entregar la información al modelo. Resultados de la rejilla (349 de texto):
  - Problema y respuesta en JSON: 37,8 % frente a 43 % (peor).
  - Reformular en inglés: +1,7.
  - Ejemplos del mismo tipo: +2,3.
  - Pedir el valor y no la letra: +5,7 (la mejor).
  - Pasos numerados y verificación de la respuesta: en medición.
  - Nueva variante: una llamada corta que «digiera» el enunciado a un esquema fijo (Datos, Se pide, Condiciones, Unidades) antes de resolver (`parseo`), y otra que simplifique el enunciado (`simplifica`). Cuestan 30-40 s más en la placa.
- **23:13** Entran en la rejilla `verifica_opciones`, `checker_primero`, `parseo` y `simplifica`, probadas en local y en la máquina 2. El sistema óptimo se plantea como una cadena: forma de leer el enunciado, vía que resuelve (código, verificador de opciones o valor), número de ejemplos y cuándo votar. `combinar_variantes.py` buscará la mejor combinación dentro de 60 s, con validación cruzada.
- **23:20-23:21** Cinco pasos que siguen los buenos resultados: leer qué dan y qué piden (la mayoría de fallos del 1.7B están aquí); reconocer el tipo de problema; elegir una vía mecánica fiable (enumerar o plantear ecuaciones); comprobar contra las opciones; sentido numérico. El modelo pequeño tiene aceptable el paso 3 y flojos los demás, por eso el sistema le pone andamios.
- **23:22** Estado: la máquina grande al 100 % (9 LoRA, rejilla y techos). La 3090 todavía compila llama.cpp.
- **23:25-23:29** vLLM frente a llama.cpp: vLLM, con batching continuo, movería el 1.7B en bf16 a miles de tokens/s agregados en la 3090 (cada variante en 1-2 min en vez de 10). Regla adoptada: **vLLM para explorar, llama.cpp para decidir**; el número final se confirma con el GGUF Q8 que irá a la placa. Riesgos: instalación (si falla, `investigar.sh` con llama.cpp sigue preparado) y bf16 frente a Q8 (1-2 puntos, sin cambiar el orden entre variantes). Plantilla de chat: `enable_thinking=false`, equivalente a `--reasoning off` de llama.cpp.
- **23:28** Tres gráficas ocupadas: máquina 1 (96 GB) con los exámenes de los 9 LoRA en llama.cpp y el resto de la rejilla; máquina 2 (3090) instalando vLLM para las 25 variantes de texto con el 1.7B en bf16 a 64 peticiones a la vez, y después 4B y 4B-Instruct-2507; torre: LoRA local del 1.7B fusionado con la base y convertido a GGUF Q8, para medir en los 349 de texto.
- **23:34** **Resultados (200 de val, sistema completo, Q8):**

  | Modelo | Total | Texto | Figura |
  |---|---|---|---|
  | Qwen3-1.7B | 42 % | 46 % | 38 % |
  | Qwen3.5-4B | 45 % | 61 % | 32 % |
  | Qwen3-4B | 47 % | 56 % | 40 % |
  | **Qwen3-4B-Instruct-2507** | **49,5 %** | **69 %** | 34 % |

  - Qwen3-4B-Instruct-2507 en Q4 pesa 2,5 GB; la CPU de la UNO Q leería a ~2 tokens/s (~75 s solo para leer el enunciado). No cabe en 60 s según la estimación; se pide medirlo en la placa.
  - **LoRA, primeros exámenes (1.7B): sin mejora**: código 36 %, razona 26-27 %, igual o peor que la base. El examen usó el prompt de la base, no el que aprendieron; se lanza el **examen justo** (`sft`, con su propio prompt y sin ejemplos) para los 9 LoRA y la base.
  - Variantes nuevas de texto (349): `k3` 45,8 %, `verifica` 44,4 %, `voto_mixto` 44,4 %, `pasos` 41,8 %, `razona_k0` 33,2 %. Siguen ganando `valor` (48,7 %) y `k1` (47,3 %).
  - **Dato incómodo:** con el 1.7B Q8 en la placa (5-6 tokens/s de lectura y ~3 de escritura), tras leer el enunciado quedan **~90-100 tokens** de salida. Variantes para ese régimen: `codigo_corto` (130 tokens), `k0_valor_60`, `valor_directo`. El 1.7B en Q4 pierde 6 puntos pero va al doble de velocidad; el 0.8B tiene 270 tokens de margen. Criterio final: máximo acierto dentro de 60 s; hace falta la velocidad real de la placa.

## 14/11 noche - 15/11 madrugada: examen de prueba y velocidad de placa (23:36-01:06)

- **23:36-23:37** Full fine-tuning del 0,8B (lr 2e-5, 2 épocas, datos mixtos) lanzado en la máquina grande, y después el del 1.7B (lr 1e-5). Cadena: entrenamiento, GGUF Q8, examen en los 349 de texto con variantes de placa. Se añade al entrenador el modo `--completo`.
- **23:42** Máquina 2 en reparación: el `pip` del sistema chocaba con un paquete de Debian y el entorno virtual no tenía pip (faltaba `python3-venv`). Se instala vLLM en un entorno propio. Mientras, la rejilla de llama.cpp corre en la 3090.
- **23:42-23:46** Análisis de patrones de comprensión en los 349 problemas de texto (1.7B), con 14 fallos revisados uno a uno. Por tipo: probabilidad 71 %, aritmética 52 %, teoría de números 49 %, contar 47 %, álgebra 44 %, geometría 42 %, medida 38 %, **lógica 27 %**. Por longitud: enunciados de menos de 40 palabras, 61 %; de 40 a 80, 33 %. Por vía: con código, 61 %; razonando en prosa, 36 %.
  - Patrón: el plan es casi siempre correcto y falla una condición o un concepto («a cada lado» olvida el ×2; «en parejas» no iguala hombres y mujeres; «por la diagonal» no cuenta los dos triángulos; «juntos» en los dígitos de 2016).
  - Las opciones son distractores de esos errores; por eso «casar con una opción» no es una señal fiable.
  - Replicable: una lista de condiciones antes de resolver (`parseo`); idiomas de código canónicos por tipo (`toolbox`: `permutations`, `range`, `while`, `Fraction`); enrutar por la forma de la pregunta (`ruta_pregunta`: «cuál no puede ser» → verificador de opciones).
  - Apoyo numérico: `verifica_opciones` 50,7 % (el verificador decide en 17 casos y acierta 12); `k1_valor` 49,0 %.
  - **Descartado:** el LoRA entrenado con explicaciones **empeora 9 puntos en texto** (40 % frente a 49 %): aprende a escribir prosa y deja de usar código.
- **23:51** **Tercera máquina alquilada: RTX 3090 a 0,17 $/h** (China), para llama.cpp y solo texto: 1.7B Q8 con las estructuras del análisis (`toolbox`, `ruta_pregunta`, `parseo`, `simplifica`, `toolbox_k1`, `checker_primero` y las de 60 s) más `sft`; 4B-Instruct-2507 Q8 con las ganadoras; 4B-Instruct-2507 Q4_K_M. Coste total de las máquinas: ~1,7 $/h.
- **23:57** **Hallazgo de presupuesto de tiempo:** la variante recortada a 60 s (`k0_valor_60`: programa de 130 tokens y valor de 90) da **18,9 %** en texto; con ~120 tokens de salida, el 1.7B no termina ni el programa ni el razonamiento. Las variantes de 47-50 % gastan 130-200 s en la placa y **ninguna cabe en 60 s**. Se reconoce que se había optimizado el acierto a tiempo ilimitado, y eso era un error de enfoque.
  - Nueva familia de presupuesto: `codigo100/150/200/270/350`, `valor100/150/200`, combinaciones y con un ejemplo. Estimaciones de salida con los GGUF reales (velocidad estimada de placa): 0.8B Q8 (~270 tokens útiles), 1.7B Q4_K_M (~200, −6 puntos de calidad), 1.7B Q6_K, 1.7B Q8 (~120) y 4B-2507 Q4 (~70).
  - En vLLM (1.7B), los números repiten los de llama.cpp (±2): `k1_valor` 47-48 %, `verifica_opciones` 46-51 %; `toolbox` 43,8 % (descartado); `sft` sobre la base 37,5 %.
- **23:59-00:09** Análisis independiente: un LLM grande de API, sin contexto previo, lee `RESULTADOS.md`, la nota del proyecto, el código de las variantes, los 508 fallos y el README, y devuelve diagnóstico, recomendación priorizada para 8 h con el criterio «máximo acierto dentro de 60 s en la placa» y riesgos del día del examen. Conclusiones del informe:
  - Bien: la vía Python con valor casado (quita el sesgo de letra); preludio y casador (+9 aciertos baratos); el SFT en prosa mata el código.
  - Error de método: optimizar a 130-200 s y luego recortar. El 19 % del recorte era en parte un artefacto (contaba «sin respuesta» como fallo y cambiaba el prompt). Simulado bien, con mediana de reserva, da ~37 % en texto. Curvas: `valor200` 30 %, `valor270` 33,5 %, frente a 48 % sin límite.
  - Los programas que aciertan son cortos (mediana 56 tokens); sin comentarios, aciertan el 71 % cuando casan.
- **00:21** **Examen de prueba (demo de la organización) desempaquetado** con el guion oficial (`laptop/prepare_m3kang.py`, que hace el OCR de las opciones). Características del examen final:
  - 20 problemas nuevos (no de M3Kang), uno por idioma (inglés o catalán), niveles 0-7, **16 de texto y 4 con figura**, letras equilibradas. Cada problema vale 5 puntos.
  - El JSONL que recibe `predict.py` trae `text_only`, `options` (del OCR; en la demo salen 100/100, con errores como «LIuC» por «Lluc») y `language`. Hay opciones, y el enrutador de figura es gratis.
  - La demo son 50 problemas × 2 idiomas = **100 filas con etiqueta**: a partir de aquí es el val realista.
  - Estilo mucho más limpio y estándar que M3Kang (por ejemplo, «canguro que salta +3, −1…» o «f(x)+2f(1/x)=3x, ¿cuánto vale f(2)?»).
- **00:25** **Resultados del examen de prueba, 1.7B Q8 en la torre** (100 filas: 80 de texto y 20 de figura, en inglés y catalán):

  | Variante | Total | Texto | Figura | eng | cat | cabe en 60 s (a 6/3 tok/s) |
  |---|---|---|---|---|---|---|
  | `k1_valor` (código 1 ej. → valor) | 54 % | **61 %** | 25 % | 58 % | 50 % | 30 % |
  | `valor` (2 ej.) | 53 % | 62 % | 15 % | 58 % | 48 % | 7 % |
  | **`valor200`** (≤200 tokens, solo valor razonado) | 47 % | **54 %** | 20 % | 50 % | 44 % | **84 %** |

  - Estimación para un examen de 20: en torno a **9-10 de 20**. Por nivel, los niveles 5-6 son los más flojos (3/10 y 5/10); los de nivel 0 fallan sobre todo por figura.
- **00:26-00:32** Síntesis: sin límite de tiempo, texto 61 % (49 de 80) y figura 25 %, total 54 %; dentro de 60 s (según la velocidad estimada), texto 54 % y total 47 %. El flujo de ejemplo de la organización (letra directa) saca ~4-5 de 20. Con 200 tokens se acierta el 54 % del texto; con 100, la mitad. Meta propuesta por el equipo: 90 % en el examen; se aclara que con 1,7B en 60 s no es alcanzable y que lo realista es **60-65 % en texto dentro de tiempo** (9 a 11-12 aciertos de 20).
- **00:42-00:44** Velocidades reales de la placa: se usa la tabla de medidas de Arnau (la tabla no aparece en el texto); el equipo trabaja con una estimación de 3-4 tokens/s de lectura. Con esa velocidad, el 1.7B no tiene tiempo para razonar (un enunciado de 150 tokens son 40-50 s; solo queda la letra, ~21-25 %). Candidato: el 0,8B Q8 (lectura ~10,6 tokens/s y escritura ~5,8; ~250 tokens útiles).
  - Demo con el 0,8B Q8 (velocidades 10,6/5,8), total y texto (sobre 80):
    - `valor` / `base` sin límite: 33 % (27/80).
    - `k0_valor`: 22 % (18/80).
    - `codigo270_valor150` (cabe en 60 s el 83 %): 20 % (15/80).
    - `valor270` (cabe el 100 %): 16 % (12/80).
    - El 0,8B queda descartado; el 1.7B hace 63 % en las mismas condiciones.
  - Medida pendiente: `llama-bench` del 1.7B y el 0,8B en la placa (`pp128` para leer y `tg64` para escribir). Regla: si el 1.7B lee por debajo de 5 tokens/s, se descarta para razonar.
- **00:51** Propuesta de Arnau: que el modelo razone en pocos pasos y Python revise cuentas y casado. Análisis:
  - Es la vía `valor` ya usada (+6 puntos frente a pedir la letra). La revisión de cuentas en Python es barata de añadir.
  - La respuesta directa sin programa es azar en la demo (1.7B 24 %, 0,8B 20 %); corregir el sesgo de la A y la D no lo sube.
  - La «libreta» en Python (el programa como registro de datos) es lo que mejor funciona: si casa, acierta el 80 %, pero solo casa en la mitad de los problemas. La libreta en dos pasos (`parseo`) no mejoró: 43,6 frente a 47,9 en M3Kang.
  - **Autodestilación** (propuesta nueva): el propio 1.7B genera 6 programas por problema de train; Python ejecuta y se queda solo con los correctos, cortos y sin trampas; se hace LoRA sobre sus propios aciertos. Sustituye al fine-tuning anterior, que enseñaba prosa. **En marcha en la máquina 2.** Si gana ≥ 3 puntos en la demo con la cadena de placa, se usa. Ajuste completo en una RTX 6000 si hay 1.000+ ejemplos (una hora de esa máquina son 1,3 $).
  - Datos de la tanda (demo, 1.7B Q8): letra directa 24 % (con dos ejemplos, 21 %; con una frase de razonamiento, 24 %). El programa corto cabe en la placa incluso a 3,8 tokens/s (mediana 50 tokens de salida, 64 de enunciado): el cuello de botella es la precisión del programa, no el tiempo.
- **00:54** **Resultados en el examen de prueba (1.7B Q8):**
  - Sin límite de tiempo: `k0_valor` (programa → si no casa, valor razonado) **63 %** (70 % en inglés, 56 % en catalán; figura 20 %); `valor` y `verifica_opciones` 53-56 %; `k1_valor` 54 %.
  - Dentro de 60 s, con velocidad estimada de placa (3,8 tokens/s leyendo y 2,5 escribiendo):
    - **`codigo150_letra`** (programa de ≤150 tokens → si casa, esa; si no, letra): **41 %**. El programa casa en 40 de 100 y acierta 30 (75 %); la letra de respaldo acierta 11 de 60 (azar).
    - `codigo220_letra`: 39 %.
    - `valor270` (solo razonar, cabe el 80 %): 51 %, pero a 6/3 tokens/s, no a 3,8/2,5.
    - Letra directa (flujo del reto): 24 %.
    - 0,8B, cualquier variante: 16-33 %; descartado.
  - Estimación para un examen de 20: **~8 aciertos** con lo que cabe seguro; **~12** si la placa es más rápida (a 6/3 tokens/s entran `valor270` y `k0_valor`).
  - Existe el **`predict.py` del equipo** (en la carpeta de entrega, fuera del repo oficial): mide la velocidad con los `timings` del servidor, calcula cuántos tokens caben, encadena programa → valor → letra con gramática, comprueba duplicados de train por huella, limita la memoria del código y siempre devuelve una letra. Probado con 12 problemas de la demo: 8/12.
- **00:57** `predict.py` completo sobre la demo (100 problemas, torre sin límite de tiempo): **58/100**. Texto 50/80 (62,5 %), figura 8/20. Por vía: programa 43 problemas (34 bien, 79 %), valor razonado 47 (21 bien, 45 %), letra 8 (2 bien), duplicados 0. Es la cota superior del sistema actual; en la placa manda la velocidad.
- **00:58** Se añade al `predict.py` un modo de simulación de placa (`--tps-forzado`, velocidades fijas, prompt en caché descontado) para probar a 3,8/2,5 y 6/3 tokens/s.
- **00:59-01:05** Arnau propone alquilar cinco máquinas para probar muchos caminos y tener certeza de que están mapeados todos. Cola de la máquina 4 con otros modelos:
  - **Phi-4-mini (3,8B)**: ~2 tokens/s leyendo en la CPU de la placa; solo entraría si la placa va mucho más rápida de lo estimado. Se mide en Q4 y Q8.
  - **DeepSeek-R1-Distill-Qwen-1.5B**: pensamiento largo; se mide con el pensamiento limitado a 150 tokens y sin pensar.
  - **Multimodales** (Qwen2.5-VL-7B, Gemma 3 4B/12B): descartados; el test no trae imágenes y los modelos de 7-12B no caben en 3,6 GB.

  | Máquina | Qué hace |
  |---|---|
  | 2 (3090) | Autodestilación: primera pasada hecha (solo 184 programas válidos: el filtro «sin comentarios» rechazaba casi todo); LoRA entrenado y en examen; segunda pasada encolada quitando comentarios en vez de rechazar, 8 muestras, 3 épocas |
  | 3 (3090) | 1.7B Q4_K_M, Q6_K y Q8, y 4B-2507 Q4, con la familia de presupuesto (texto de M3Kang) |
  | 4 (3090, arrancando) | Otros modelos: Qwen2.5-Coder-1.5B, Qwen2.5-1.5B, Qwen3-0.6B, SmolLM2-1.7B, Gemma-3-1B, Qwen3.5-2B, DeepSeek-R1-1.5B, Phi-4-mini, y el 1.7B de referencia; demo y M3Kang con `codigo150_letra`, `k0_valor`, `valor270` |
  | 5 (3090, arrancando) | 1.7B con pensamiento corto (40/80/150 tokens) antes del programa, sin opciones en el prompt, y **Q4_0** (llama.cpp reempaqueta Q4_0 para ARM; puede leer más rápido en la placa) |
  | Torre | `predict.py` simulando la placa a 3,8/2,5 y 6/3 |

  - Para la placa, además del `llama-bench` del Q8, se mide también el Q4_0.
- **01:06** Simulación del `predict.py` completo en la demo con la caché contada correctamente: primer resultado en curso (ver el bloque siguiente).

## 15/11 madrugada - fábrica de problemas y «super modelo» (01:36-03:59)

- **01:36-01:39** Primera oleada de problemas sintéticos generada por un LLM grande de API: **480 problemas, 231 de 240 verificados (96 %)** en la primera mitad. Cada programa se ejecuta y solo se guarda si imprime la opción marcada; se quitan duplicados. Calidad: correcta y variada, algo «de libro». Segunda oleada en paralelo, con instrucciones más duras (dos o más pasos, trampas típicas, 20 % en catalán).
- **01:41** Bucle de revisión de las máquinas cada 2 minutos. Resumen de conclusiones de una búsqueda bibliográfica del equipo: cambiar cómo se pide la respuesta (leer las probabilidades de A-E en vez de la letra); ningún modelo de 2,5 B o menos tiene resultados publicados en Canguro en catalán o castellano claramente por encima del azar; un 3,8 B que razona y ve imágenes saca 26,5 % en catalán, 27,4 % en castellano y 30,3 % en inglés en M3Kang; el mejor candidato es Qwen3.5-2B; la placa escribe a 2-6 tokens/s, así que el razonamiento largo no encaja.
- **01:41-01:45** **Hallazgo:** de los 100 programas de la demo, **37 no casan** con las opciones. 32 se ejecutan y dan un valor que no es opción (es un error de planteamiento, no un bug); 5 son bugs simples (3 sin `print`, 1 `NameError`, 1 `TypeError`). Reparaciones automáticas (`zip(l,l)` → `permutations`, `print` que falta, extraer el último número): **0 aciertos recuperados**. Se encuentra un fallo del casador: los decimales largos como `-0.3333333333` se rechazaban (`-1/3` era la opción). Arreglado: +1.
- **01:23** Lectura de las cuatro máquinas. Autodestilación, primera pasada (184 ejemplos): sin efecto (demo `k0_valor` 58 %, `codigo150_letra` 39 %; M3Kang 39 frente a 37). 1.7B Q4_K_M (texto de M3Kang, a 9/5 tokens/s): `k1_valor` 42 %, `valor200` 31 % (cabe el 100 %), `codigo270_valor150` 34 % (cabe el 53 %). Pierde 5-7 puntos frente al Q8.
- **01:25** Última tanda en la demo (1.7B Q8, velocidad 3,8/2,5): **programa 150 → mediana 45 %** (programa 31/42 bien, mediana 12/47, letra 2/11; cabe el 68 %); programa 110 → mediana 43 %; dos programas (T=0 y T=0,7) → mediana 41-44 % (no compensa los 30 s extra); programa 150 → letra 41 %. **Receta:** un programa del tamaño que permita el tiempo → casar con las opciones → mediana si no casa.
- **01:26** Sobre el uso de cinco máquinas sin resultados nuevos: el techo lo pone el modelo que cabe en la placa (1,7 B a 3-4 tokens/s), y ninguna máquina alquilada cambia la CPU de la placa. La palanca es entrenar: el LoRA con explicaciones empeoró y el autodestilado con 184 ejemplos no movió nada. El dato decisivo, la velocidad real del 1.7B en la placa, aún no estaba medido.
- **01:28** Full fine-tuning «a lo grande» con todos los tipos de problema: es la idea correcta, pero no para esa noche. Haría falta generar 20.000-50.000 problemas nuevos con solución verificada, y un ajuste completo en una GPU grande (~1 h, ~1,5 $). Eran las 6:00 y el examen empezaba a las 12:00.
- **01:30-01:33** Quedan más de 15 horas. Bases públicas consideradas: GSM8K (8k), MATH (12k), AQuA-RAT (100k, opción múltiple), MathQA (37k, opción múltiple con programas), NuminaMath (860k) y OpenMathInstruct. Qwen3 ya se entrenó con ellas, así que re-enseñarlas aporta formato, no conocimiento. No existe ninguna pública de estilo Canguro con soluciones; M3Kang es la única. Se lanza la generación con un LLM grande de API: 8 lotes en paralelo, cada uno con ~18 problemas reales como referencia de estilo, escriben 60 problemas nuevos cada uno con 5 opciones (correcta repartida entre A-E) y el programa que los resuelve. El verificador (`verificar_sintetico.py`) ejecuta cada programa y guarda solo los que imprimen la opción marcada. Objetivo: 10-20k problemas en 1-2 h.
- **02:03** **Primer entrenamiento que mejora:** autodestilado del 1.7B con 516 programas propios que habían acertado:

  | Demo | Base | Autodestilado |
  |---|---|---|
  | programa ≤150 tokens → letra | 39-41 % | **47 %** |
  | programa ≤220 tokens → letra | 39 % | **50 %** (casa en 50 problemas, frente a 42) |
  | M3Kang texto, programa ≤150 → letra | 25-30 % | **34 %** |

  - Fábrica de problemas: un LLM grande de API, **40 lotes, 2.269 problemas verificados**; control independiente: una segunda lectura resolvió 60 sin ver la respuesta y coincidió en **60 de 60**.
  - Servicio de modelos abiertos **Helmcode** (del hackathon): funciona; modelos disponibles `deepseek-v4-flash`, `glm5.3-flash`, `qwen3.6` y `gemma4`. Se generan unos 7.000 problemas más con DeepSeek V4 y GLM-5.3, para fabricar datos (no van a la placa, que no tiene red).
  - Dataset total: 3.908 ejemplos (sintéticos + autodestilado + 1.728 programas verificados de M3Kang).
  - Entrenamiento grande: se alquila otra **RTX PRO 6000 de 96 GB** para el ajuste completo del 1.7B a 2 y a 3 épocas, y un LoRA r32.
  - El vigía pasa de solo avisar a **rellenar**: `vigia3.py` revisa las máquinas cada 2 minutos y lanza el siguiente trabajo de cada cola.
  - Descartado con datos: pensar antes del programa (40-150 tokens): 29,8 % frente a 30 %; quitar las opciones del prompt: no cambia nada; 4B-2507 en Q4 con código: 48,7 % en texto, pero solo cabe en tiempo el 15 % de los problemas.
- **02:04** Otros modelos en la demo: Qwen2.5-Coder-1.5B saca `codigo150_letra` 34 %, `k0_valor` 40 % y `valor270` 19 %; Qwen3-1.7B, con las mismas variantes, 39-41 %, 58 % y 51 %: **peor en todo**. Pensar 150 tokens antes del programa (M5): 34,7 % frente a 39 % sin pensar en M3Kang. 4B-2507 en Q4 (M3): 45,8 % en texto con `codigo200_valor120`, pero solo cabe el 14 % de los problemas.
- **02:06-02:11** Objetivo del equipo: la máxima nota en examen y demo. Reorientación: todo lo que genera o comprueba datos usa modelos abiertos de Helmcode, no los tokens del LLM grande de API. Plan:
  1. Modelo: Qwen3-1.7B Q8. El entrenamiento con sus propios programas correctos ya sube la cadena de placa del 39-41 % al 47-50 % en la demo.
  2. Datos de modelos abiertos verificados por ejecución: DeepSeek V4, ~3.868 problemas nuevos en 8 minutos; GLM-5.3, Qwen3.6 y Gemma4 (los dos últimos ilimitados en el plan); doble verificación (DeepSeek resuelve cada problema sin ver la respuesta y solo se quedan los que coinciden); DeepSeek como profesor, que escribe el programa corto para cada problema de texto de M3Kang.
  3. Entrenamiento con todos los datos en todas las gráficas, y examen de cada modelo en la demo con la cadena de placa.
  4. Inferencia: programa corto → casar con las opciones → reserva (mediana, 45 %, o letra del modelo, 41 %; decisión pendiente).
  5. En la placa: medir la velocidad real, ajustar `predict.py` y congelar la versión dos horas antes del examen.
- **02:13-02:14** ¿Sirven los modelos abiertos? Sí, para fabricar el modelo, no para estar dentro de él: fábrica de datos, profesor y revisor. No caben en la placa (entre 35 y 744 mil millones de parámetros frente a 3,6 GB). Fusionar pesos con un modelo grande no es posible (arquitecturas y vocabularios distintos); pegar capas (frankenmerge) queda descartado. Sí es viable fusionar varios 1.7B entrenados por el equipo con TIES o DARE (`mergekit`), porque todos parten de Qwen3-1.7B. Propuesta: fusionar las dos o tres mejores versiones a las 6:00-7:00 y examinarlas.
- **02:14-02:15** Kit de medida de placa preparado en paralelo por otro miembro del equipo (repo privado de medición con copia de `predict.py`). `./todo.sh` (unos 50 min; `rapido`, unos 15): llama-bench del 1.7B en Q8_0, Q4_0, Q4_K_M y Q6_K, del 0,8B Q8 y del 2B Q4_0 (lectura de 200 tokens, escritura de 64); llama-server con caché del prompt de sistema; `predict.py` sobre 15 problemas de val con el límite real; resumen de los tokens de programa que caben en 56 s por modelo.
- **02:20-02:22** Propuesta de Arnau: MathQA y AQuA-RAT encajan con la cadena «programa → valor → casar». Advertencias: estilo tipo GMAT, no Canguro; MathQA tiene etiquetas erróneas (ejemplo: «coste si vendes a 600 con un 30 % de beneficio» da 461,5, que no está entre las opciones, y la etiqueta marca 400). Decisión: que el 1.7B escriba sus propios programas (4 por problema), ejecutarlos y quedarse solo con los que imprimen la opción marcada, lo que filtra las etiquetas malas sin pagar un verificador. Se bajan MathQA y AQuA-RAT (127.000 problemas) y se convierten; se quedan **12.000** (cinco opciones distintas, enunciados de 15-120 palabras, opciones numéricas, sin duplicados). Encolado en la máquina 2.
- **02:22** Un intento de alquilar una sexta máquina fue bloqueado por el sistema, porque Arnau había autorizado cinco; el trabajo quedó encolado en la máquina 2.
- **02:49** **Mejor resultado de la noche: LoRA r32 de 3 épocas sobre el dataset total** (sintéticos + autodestilado + M3Kang verificado). Demo, cadena de placa:

  | Demo, cadena de placa | Base | Ajuste completo 2 ép. | Ajuste completo 3 ép. | **LoRA r32 3 ép.** |
  |---|---|---|---|---|
  | programa ≤150 → letra | 41 % | 47 % | 47 % | **52 %** |
  | programa ≤220 → letra | 40 % | 47 % | 48 % | **56 %** |
  | programa ≤150 → mediana | 44 % | 46 % | 53 % | 52 % |

  - El programa casa en 52 de 100 problemas y acierta 44 de ellos (antes, 40 y 30).
  - Helmcode: **6.947** sintéticos verificados por ejecución (2.269 de un LLM grande de API, 3.868 de DeepSeek y los de Qwen3.6 y Gemma4; GLM sigue generando). Doble verificación con DeepSeek a ciegas: los del LLM grande coinciden en **99,9 %** (2.266 de 2.269).
  - Máquinas: M1, GRPO sobre el LoRA ganador (recompensa = el programa casa con la opción correcta, con penalización si es largo); M2, autodestilado sobre los 12.000 de MathQA y AQuA; M3, LoRA de lr bajo; M4, LoRA de rango 64; M5, autodestilado a escala (2.206 programas propios correctos).
- **02:50-02:51** Calendario, hora local 02:50. El examen se entrega tras el *last call* de las **12:00**. Plan: 03:30 primeros resultados de la segunda ronda; 03:45 mezcla v2 en M1 y prueba con MathQA/AQuA en M2; 04:00-04:30 comparar y fusionar; 04:30-06:30 tercera ronda; 06:30-08:00 elegir el modelo final, exportar Q8 y simular; 08:00-10:00 en la placa con `./todo.sh` (50 min) y `predict.py` con 15-20 problemas; **10:00 congelar** la versión; 10:00-12:00 margen. Coste de las gráficas: ~1,9 $/h.
- **02:54-02:55** Primeras medidas en la placa (una imagen que no aparece en el texto). Qwen3.5-2B va igual de rápido que el 1.7B: lee 4,5-4,9 tokens/s y escribe 2,7 (el 1.7B lee 4,5-5,2 y escribe 2,8). Cuenta con esas velocidades (prompt en caché, ~70 tokens nuevos): leer ~15 s; ejecutar y casar ~3 s; quedan ~38 s para escribir, unos **100 tokens de programa**; los programas que aciertan tienen mediana de 50 tokens. Un 4B (Qwen3-4B, Phi-4-mini) leería a ~2 tokens/s (35 s solo el enunciado) y escribiría ~1,1 tokens/s: no cabe.
  - El 2B sin entrenar: texto 50 % (frente a 46 % del 1.7B); total 41 % (frente a 45 %). Se encola el mismo LoRA ganador (r32, 3 épocas) sobre Qwen3.5-2B en M4.
  - Cambios en `predict.py`: se desactiva el paso de «valor razonado» (usaba otro prompt de sistema, y tiraría la caché: el problema siguiente se leería en frío, 71-78 s); velocidades de partida = las medidas en la placa (4,6 leyendo, 2,7 escribiendo).
- **02:58** Mezcla v2 lista y entrenando en M1: **9.603 ejemplos**: 8.120 sintéticos verificados por ejecución (LLM grande de API, DeepSeek, Qwen3.6 y Gemma4), 3.950 autodestilados del propio 1.7B y 1.728 programas verificados de M3Kang (las fuentes suman más que el total porque los duplicados cuentan una vez). Misma receta que el ganador.
- **03:00** Dos trabajos más en los modelos ilimitados: **traducción al catalán con Qwen3.6** de 3.000 problemas sintéticos verificados (mismas opciones, misma respuesta y mismo programa), porque en catalán se acierta entre 6 y 8 puntos menos; y otra tanda de **Gemma4** con la mitad de los problemas escritos directamente en catalán.
- **03:09-03:14** Cambios en `predict.py` revisados por el equipo: quitar el «valor razonado» no quita nada, porque con las velocidades de la placa no llega a ejecutarse (solo se lanza si quedan más de ~63 s, y tras el programa quedan ~15-20). Velocidades de partida: el 1.7B Q8 da 4,3 tokens/s leyendo y 2,7 escribiendo en la prueba corta de la placa.
- **03:20** Estado de `predict.py` (probado en la torre):
  - Corte en cuanto se cierra el bloque de código (`stop`): hecho.
  - Letra primero (1 token con gramática, mismo prompt de sistema): hecho.
  - Opción más cercana: pendiente de medir en los logs.
  - Figura con respuesta directa: ~11 s por problema en vez de 40.
  - Log de lo que escribe el modelo (`.log.jsonl`): hecho.
  - Extras: espera a `/health`; reserva «descarte» (la letra se elige solo entre las tres opciones centrales cuando son números, porque la menor y la mayor casi nunca son la respuesta).
  - El LoRA r32 entrenado esta noche: **52-56 %** en la demo con la cadena de placa, frente a 40-41 % de la base.
- **03:26** **Simulación del sistema completo a la velocidad medida en la placa** (4,6/2,7 tok/s), 100 problemas de la demo:

  | Sistema en la demo | Aciertos | Texto |
  |---|---|---|
  | Baseline oficial del reto | ~22 % | — |
  | `predict.py` nuevo + Qwen3-1.7B **sin entrenar** | 37 % | 32/80 |
  | `predict.py` nuevo + **1.7B entrenado (LoRA r32)** | **51 %** | **49/80** |
  | Lo mismo, con la placa un 15 % más lenta | 46 % | 44/80 |

  - Ningún problema pasa de 56 s (media 34 s, máximo 52 s). En el examen de 20, unos **10 aciertos** frente a 4-5 del baseline.
  - Por qué funciona: el programa casa con una opción en 45 de 80 problemas de texto (sin entrenar, 25), y cuando casa acierta el 82 %; los programas son cortos y sobra tiempo para un segundo intento (+3 aciertos); la letra va primero y siempre hay respuesta.
  - Observaciones en los logs: el modelo entrenado, al contestar solo la letra, dice casi siempre «A»; por eso la reserva usa la mediana cuando las opciones son números (en la demo da lo mismo que la letra, 48 frente a 49; en M3Kang sí ayuda). El GRPO no mejora al LoRA (51 frente a 52-56).
  - Pasos para la placa: `subir_a_placa.ps1 -Extra` con el GGUF entrenado; `llama-server` con el modelo; `predict.py` con 15 problemas de la demo; entregar el `.log.jsonl`.
- **03:29-03:31** Candidatos al «super modelo» (hora local, ~03:30):

  | Candidato | Máquina | Progreso | Resultado en simulación de placa |
  |---|---|---|---|
  | Qwen3.5-2B + LoRA r32 (receta ganadora) | M4 | 658/735 pasos | ~3:50 (estimado) |
  | GRPO desde la base | M1 | 179/200 | ~3:50 |
  | 1.7B + mezcla v2 (9.600 ejemplos) | M1 | 1.019/1.803 | ~4:05 |
  | 1.7B + autodestilado + MathQA/AQuA | M2 | 95/642 | ~4:25 |
  | 1.7B + mezcla v2 con lr 2e-4 | M3 | 361/1.803 | ~4:30 |
  | 1.7B + mezcla v2 a 4 épocas | M5 | 306/2.404 | ~5:15 |

  - Un proceso (`auto_sim.py`) espera a que cada modelo termine, baja su GGUF a la torre y le pasa la misma simulación de placa; resultados en `candidatos.txt`. Si dos o más superan al 51 %, se fusionan (unos 20 min más); GGUF final hacia las 5:00.
- **03:59** **Qwen3.5-2B con LoRA r32 saca 53/100** en la demo simulada a velocidad de placa; el 1.7B en cabeza, **51/100**. Diferencia dentro del ruido de la demo (±5). Ningún problema pasa de 52 s. Para decidir, cada candidato se simula también sobre los problemas de texto de val de M3Kang en inglés y catalán (**246 filas**).

## 15/11 madrugada - segunda ronda, pistas y mapa de errores (04:00-04:32)

- **04:00** Arreglos de la tanda: la subida de datos a M4 llegó cortada y se repitió comprimida; el 2B entrena la mezcla v2 y acabaría hacia las 6:00. La descarga de modelos dejaba ficheros truncados: ahora baja por trozos, reintenta y comprueba el tamaño. Había dos simulaciones peleando por el mismo puerto: queda una. M1 estaba parado porque su guion arrancaba el servidor en un puerto y esperaba en otro; se lanzó a mano. El vigía de colas se había cerrado: se relanza para 10 horas sobre las cinco máquinas. M2 cambia un trabajo con datos viejos por el GRPO del 2B.
  - Descartado: casar la salida del programa con la opción más cercana (3 de 15 en la demo, igual que la reserva actual).
  - Riesgo para la placa con el 2B: la cadena reaprovecha el enunciado leído para la letra al escribir el programa (en la torre, la segunda petición lee solo 4 tokens nuevos). Si no se reaprovecha en la placa, cada problema tarda ~30 s más.
- **04:01-04:02** Otro miembro del equipo detecta que el paso 0 de `predict.py` (duplicados de train) no encuentra ninguno en los 789 de val: el número inicial del enunciado («23. …») cambia entre niveles, y se exigían ≥3 números. Sustituto con la biblioteca estándar: busca problemas de train con las mismas 5 opciones y enunciado parecido (difflib ≥ 0,6). En val: **13 contestados y 13 correctos**, 2 ms por problema. Con bge-m3 (≥0,85 + mismas opciones) saldrían 17/17, pero cuesta 600 MB y embeberlo en la placa. Se integra en `predict.py`.
- **04:02** Candidatos del sistema de placa:

  | Modelo | Demo | Validación, texto eng+cat | Suma |
  |---|---|---|---|
  | 1.7B LoRA r32 | 51/100 | 86/246 | 137/346 |
  | 2B LoRA r32 | 53/100 | 80/246 | 133/346 |

  - El 1.7B con la mezcla v2 apunta mejor: su examen en la nube da 58 en la demo (frente a 52 del LoRA r32); en validación, 128 de 349 frente a 126. Escribe programas más cortos, así que caben más en 60 s.
  - M1 empieza GRPO sobre el v2, porque el v2 iguala al anterior en validación.
  - Las simulaciones de validación restan desde ahora 4 aciertos gratis del duplicado.
- **04:06** **GRPO sobre el LoRA r32: descartado.** Demo 50/100; validación sin duplicados 81/246 (frente a 86/246 del LoRA r32). En la nube la validación subía de 36,1 % a 39,8 %, pero en la cadena real de placa los programas casan menos (61 frente a 63).
- **04:10** Qué es la demo: el **examen de práctica que dio la organización** (zip «Qualcomm_practica»): 50 problemas de Canguro de 2026, cada uno en inglés y en catalán (100 filas); 40 solo de texto y 10 con figura. Se pasa al formato del reto con el script oficial. El **examen final** son 20 problemas nuevos que no salen de M3Kang, en inglés o catalán, que la organización pasa con `predict.py` después de las 12:00. Para elegir modelo se suman demo (50 problemas, ruido de ~5 puntos) y validación (**123 problemas de texto de M3Kang**, apartados del entrenamiento, en inglés y catalán: 246 filas).
- **04:11-04:12** Propuesta de un RAG pequeño como «chuleta» que el modelo afinado consulte. Medido: no conviene una chuleta distinta por problema.
  - Coste en la placa: un ejemplo con su programa (~120 tokens, ~27 s); dos ejemplos (~250 tokens, ~55 s). Cada problema ya gasta 34-45 s de los 56 disponibles.
  - Ya probado: con el 0,8B, dos ejemplos subieron la nota 4 puntos como mucho; con el 2B y ejemplos explicados quedó igual (34,5 % con RAG y sin él).
  - El fine-tuning ya hace de chuleta: el modelo ha visto 9.600 programas cortos verificados. El examen final no sale de M3Kang, así que los parecidos serán peores.
  - Alternativa que sí cabe: una chuleta fija de unos pocos trucos en el prompt de sistema, leída una vez al calentar y en caché. Riesgo: el modelo se entrenó con el prompt actual.
- **04:17** Propuesta de Arnau: una pista de 1 a 10 palabras (coste en placa de ~3 s de lectura). Nuevo 1.7B entrenado con la mezcla v2: **57/100 en la demo** y **89/246 en validación** (sin duplicados), frente a 51/100 y 86/246 del LoRA r32. Modelo para la placa: `17b_lora32_v2-Q8_0.gguf`. Se pasa el GGUF al equipo de medición de la placa para la prueba.
  - Pistas probadas: (1) pista perfecta, escrita por un modelo abierto mirando el propio problema; (2) pista realista, del problema de train más parecido (con umbral de parecido). Se simula la (1).
- **04:19** **Pista descartada.** 1.7B v2 en la placa simulada: sin pista, 57/100 en demo y 93/246 en validación; con pista perfecta, 61/100 en demo y 90/246 en validación. En total +1, que es ruido. La pista cambia el programa al azar: en validación arregla 15 problemas y rompe 18. La versión realista no se simula. Entrenar con pistas costaría otra hora de generación para 9.600 ejemplos. El código queda apagado tras una variable de entorno.
  - Modelo para la placa: 1.7B v2. En curso: GRPO sobre el v2 en M1 y tres variantes del v2 en M3, M4 y M5.
- **04:21-04:29** **Mapa de errores del modelo líder.** Se revisan **178 fallos de texto** (demo y validación); un modelo abierto diagnostica cada uno con el problema, la respuesta correcta y el programa escrito.

  | Causa | Problemas |
  |---|---|
  | Planteamiento equivocado | 75 de 103 |
  | Error de código o de cuenta | 17 |
  | Programa largo que no termina | 10 |
  | No conoce el método | 1 |

  - Planteamientos típicos: ignora una condición; cuenta dos veces los pares (a,b) y (b,a); invierte una relación; toma el autobús anterior en vez del siguiente; suma cifras en vez de mirar el número entero.
  - Pruebas: (1) el tiempo no es el problema: a los 74 programas cortados se les dio el doble de tiempo y solo acertaron 6 más; (2) la mejor pista posible, escrita viendo la respuesta, arregla 30 de 178 (es el techo de una chuleta); (3) una pista real rompe aciertos: en validación arregla 15 y rompe 18.
  - Lo que hace falta: que el modelo aprenda a plantear bien, y eso solo entra en los pesos. La mezcla v2 subió de 51 a 57 en la demo.
  - Plan: **48 lecciones genéricas** a partir de los diagnósticos (por ejemplo, «cuenta los pares sin orden una sola vez», «respeta el valor total, no solo el número de monedas», «estrictamente después»). Dos modelos abiertos de Helmcode generan problemas en los que esas trampas deciden la respuesta, con programas que comprueban cada condición. Verificación por ejecución y **mezcla v3** (con el v2) en M1, con simulación hacia las 6:30. Aviso: las lecciones salen de fallos de demo y validación, así que la mejora medida será algo optimista.
- **04:31-04:32** Pregunta de Arnau: ¿no sería directamente el modelo de plantear el problema? Respuesta en curso: se escribe el promediador de modelos (fusión de pesos) para la torre mientras termina la generación. **Fin del cuaderno** (última entrada del 15/11, 04:32).

## Modelos mencionados

Notas: «LLM grande de API» agrupa todos los modelos grandes de API usados para generar, explicar, auditar o clasificar datos. Los modelos sin cifra no tienen resultado registrado («sin cifra»).

### Modelos de inferencia (en la placa o en el PC)

- **Qwen3.5-0.8B** (el del reto, en Q8 y Q4_0; también la versión `hf` para entrenar): letra directa 21,0 % (val, 789); razonando 23,5 % (200); sistema completo 33 % (test de 100); demo sin límite de tiempo 33 %. **Mejor: 33 %.** Descartado para la placa.
- **Qwen3.5-2B** (Q4 y Q8): letra directa 22,2 % (Q4) y 21,5 % (Q8, con explicaciones); razonando 31,0 % (Q8, 267 tokens); 34,0 % con dos ejemplos explicados (Q8); 41 % sistema completo (test de 100); sin entrenar, texto 50 %. Con el LoRA r32 de la receta ganadora: **53/100** en la demo simulada a velocidad de placa (80/246 en validación). Velocidad en placa igual que la del 1.7B (lee 4,5-4,9 tokens/s, escribe 2,7).
- **Qwen3-1.7B** (Q8, Q6_K, Q4_K_M y Q4_0): 42 % sistema completo (200 de val, Q8; texto 46 %); 35,5 % en val completo (789; texto 46 %, figura 27 %); demo con `valor200`, `valor` y `k1_valor`: 54 % (texto 61 %); `k0_valor` sin límite de tiempo: 63 %; 45 % en la demo simulada con programa 150 → mediana; Q4_K_M cae a 36 % (200) y a 42 % en texto (M3Kang, 9/5 tokens/s). **Mejor en placa simulada: 57/100 (demo) y 89/246 (validación), con la mezcla v2.**
- **Qwen3-1.7B con pensamiento corto (40/80/150 tokens)**: 29,8 % frente a 30 % sin pensar; 34,7 % frente a 39 % en M3Kang con `k0_valor`. Descartado.
- **Qwen3-4B** (Q8): 47 % sistema completo (200 de val, Q8; texto 56 %, figura 40 %). Descartado en placa: en Q8 no cabe en memoria; en Q4 pesa 2,5 GB y va a ~1,1-2 tokens/s.
- **Qwen3-4B-Instruct-2507** (Q8 y Q4_K_M): **49,5 %** sistema completo (200 de val; texto **69 %**, figura 34 %). En Q4_K_M con código, 48,7 % en texto, pero solo cabe en 60 s el 15 % de los problemas; con `codigo200_valor120`, 45,8 % en texto y cabe el 14 %. Descartado en placa.
- **Qwen3.5-4B**: 45 % sistema completo (200; texto 61 %, figura 32 %). Descartado en placa.
- **Qwen3-8B**: en la lista de techos de la nube, sin cifra.
- **Qwen2.5-Math-1.5B-Instruct**: 36-39 % sistema completo (texto 50 %; figura 26-28 %); escribe buen código pero se salta el formato. Descartado.
- **Qwen2.5-Coder-1.5B**: `codigo150_letra` 34 %, `k0_valor` 40 %, `valor270` 19 % (demo). Peor que Qwen3-1.7B. Descartado.
- **Qwen2.5-1.5B**: en la comparativa de la máquina 4, sin cifra.
- **Qwen2.5-VL-7B**: descartado (sin cifra; no cabe en 3,6 GB y el test no trae imágenes).
- **Qwen3-0.6B**: en la comparativa, peor que el 1.7B (sin cifra).
- **Qwen3.6**: modelo abierto de Helmcode; genera problemas sintéticos y traduce 3.000 al catalán (sin cifra de acierto propia).
- **Gemma 3 1B**, **Gemma 3 4B / 12B**: descartados (sin cifra; Gemma 3 1B está en la comparativa de la máquina 4).
- **Gemma4**: modelo abierto de Helmcode; genera problemas sintéticos (sin cifra).
- **SmolLM2-1.7B**: en la comparativa de la máquina 4, sin cifra.
- **Llama 3.2 1B/3B**: descartados por criterio, sin cifra.
- **DeepSeek-R1-Distill-Qwen-1.5B**: pensamiento limitado a 150 tokens; sin cifra.
- **Phi-4-mini (3,8B)**: candidato a medir en Q4 y Q8, sin cifra.
- **SmolVLM2-256M/500M** (informe externo): propuesto como descriptor de figuras, sin probar.
- **LightOnOCR**: descartado (OCR de documentos).
- **PP-OCRv5 mobile** (informe externo): propuesto para leer opciones en la placa; no probado.
- **RapidOCR** (detección, orientación y lectura): OCR de las imágenes de M3Kang en la gráfica; leyó las opciones A-E del 63 % de los problemas (3.080 de 4.862). Después, las opciones se revisaron con un LLM grande de API.
- **mmproj de Qwen3.5-0.8B (205 MB) y de Qwen3.5-2B (670 MB)**: proyectores de visión; propuestos para la figura, sin prueba. Como el test no trae imágenes, no se usan.
- **Qwen3-1.7B-Q8 de referencia en vLLM** (bf16): `k1_valor` 47-48 % y `verifica_opciones` 46-51 % en los 349 de texto (repetición de llama.cpp ±2).

### Embeddings (buscador del RAG)

- **bge-small-en** (el del reto, 37 MB, solo inglés): primera posición 74 % en catalán y castellano (508 problemas, contra los 281 de inglés); entre las tres primeras, 86 %; RAG con 1, 2 y 3 ejemplos: 23,4 %, 24,8 % y 22,8 %. **Mejor: 24,8 %** (RAG con 2 ejemplos, 0,8B).
- **bge-m3** (600 MB, multilingüe; GGUF Q8 de 605 MB; índice `index_m3.db` de 19 MB): **100 %** en primera posición y entre las tres primeras (508 de 508); RAG con 1, 2 y 3 ejemplos: 24,2 %, **25,3 %** y 23,8 %. **Elegido.** Usado también en la detección de duplicados.
- **multilingual-e5-small**: propuesto; sin GGUF accesible; sin cifra.
- **paraphrase-multilingual-MiniLM**: propuesto; sin cifra.

### Generadores, profesores y revisores (no van a la placa)

- **LLM grande de API, lector y generador**: leyó las imágenes de M3Kang (1.747 problemas en inglés, más catalán y castellano) para la limpieza de opciones (JSON al 90 % con opciones; 2.771 + 1.356 + 219 + 39 opciones confirmadas por dos lecturas, por el cruce con el OCR o por revisión); escribió explicaciones (3.684 de todo train; texto 95 % de confianza alta, figura 78 % viendo la imagen); escribió programas verificados (766 de 853 problemas de texto correctos, 90 %; 123 de 128 del piloto, 96 %); generó problemas sintéticos verificados (2.269 por ejecución; control de 60 de 60 coincidentes); y clasificó los 509 fallos. Coste de la limpieza: ~5-6 M de tokens.
- **LLM grande de API, auditor**: auditoría de 60 problemas de la lectura de opciones: **60 de 60 iguales**. Propuesto también para explicaciones difíciles (sin cifra).
- **LLM grande de API, revisor**: revisión de los casos dudosos (13 problemas corregidos a mano en la limpieza) y revisión independiente de la estrategia (sin cifra propia).
- **DeepSeek V4** (`deepseek-v4-flash`, en Helmcode): genera problemas sintéticos (**3.868** en 8 minutos) y resuelve a ciegas para la doble verificación (coincidencia con los del LLM grande de API: 99,9 %; 2.266 de 2.269). Es el profesor que escribe programas para M3Kang-train (en marcha; sin cifra final).
- **GLM-5.3** (`glm5.3-flash`, en Helmcode): genera problemas sintéticos en la última ronda (sin cifra).

### Modelos entrenados por el equipo (nombres internos y resultados)

- **`08b_mixto`, `08b_explicacion`, `08b_codigo`**: LoRA sobre el 0,8B con la mezcla mixta, de explicaciones y de código. Sin cifra individual; en la demo, el 0,8B entrenado da lo mismo que la base (16-33 %).
- **Ajuste completo del 0,8B** (lr 2e-5, 2 épocas): en marcha; sin cifra.
- **`2b_mixto`, `2b_codigo`, `2b_explicacion`**: LoRA sobre el 2B; sin cifra individual, salvo el LoRA r32 (abajo).
- **`2b_codigo_3ep`, `2b_codigo_r32`** (matriz inicial): sin cifra.
- **`4b_codigo`** (matriz inicial): sin cifra.
- **`17b_mixto`, `17b_codigo`, `17b_explicacion`** (LoRA sobre el 1.7B): primeros exámenes sin mejora (código 36 %, razona 26-27 %). Pérdidas finales: código 0,33, mixto 0,67, explicación 0,97-0,99. **Descartados como receta.**
- **LoRA con explicaciones sobre el 1.7B**: empeora 9 puntos en texto (40 % frente a 49 %); descartado.
- **1.7B con LoRA local en la torre** (QLoRA 4 bits, 2 épocas, 55 min): pérdida 0,73 → eval 0,75, **80 % de acierto por token** (no es acierto en problemas). Validó la tubería de entrenamiento.
- **Autodestilado del 1.7B** (516 programas propios correctos): programa ≤220 → letra **50 %** en la demo (base 39 %); programa ≤150 → letra **47 %** (base 39-41 %); M3Kang texto **34 %** (base 25-30 %). Primera pasada con 184 programas: sin efecto. **Mejor de este tipo: 50 %.**
- **Autodestilación a escala** (2.206 programas propios correctos en M5; 8 muestras por problema en M2): en curso; sin cifra final.
- **Ajuste completo del 1.7B** (2 y 3 épocas): demo, programa ≤150 → letra 47 %; ≤220 → letra 47-48 %; programa ≤150 → mediana 46-53 %.
- **`17b_lora32` (LoRA r32, 3 épocas, sobre el dataset total)**: demo con la cadena de placa, 52 % (≤150 → letra) y 56 % (≤220 → letra); demo simulada a velocidad de placa **51/100**; validación 86/246. Referencia hasta la mezcla v2.
- **`17b_lora32_v2` (mezcla v2: 9.603 ejemplos, misma receta)**: **57/100 en la demo simulada a velocidad de placa; 89/246 en validación sin duplicados** (y 58/100 en el examen de la nube). **Mejor resultado de la campaña.** Modelo elegido para la placa (`17b_lora32_v2-Q8_0.gguf`).
- **Qwen3.5-2B + LoRA r32** (receta ganadora sobre el 2B): **53/100** en la demo simulada; 80/246 en validación.
- **GRPO sobre el LoRA r32** (recompensa: el programa casa con la opción correcta): 50/100 en la demo; 81/246 en validación. Descartado.
- **GRPO desde la base y GRPO sobre el v2** (M1): en curso; sin cifra final.
- **1.7B + mezcla v2 con lr 2e-4 y a 4 épocas**, **1.7B + autodestilado + MathQA/AQuA**, **LoRA de rango 64**, **LoRA de lr bajo (5e-5)**: en curso o en cola; sin cifra final.
- **Mezcla v3** (con las 48 lecciones genéricas): planificada para simular hacia las 6:30; sin resultado.
- **Modelo fusionado** (TIES o DARE con `mergekit` de varios 1.7B entrenados): propuesto para la madrugada; sin resultado.
- **1.7B v2 con pista perfecta** (pista escrita mirando el problema, sin entrenar con pistas): 61/100 en demo, 90/246 en validación. Descartado.

---

*Este cuaderno se escribió durante la madrugada del 15/11. Algunos experimentos aparecen como «en curso» o «sin cifra»; las cifras finales de cada modelo están en [los modelos](04-modelos.md) y en [`pruebas/`](../pruebas).*

## 15/11 madrugada - generación masiva dirigida (04:45-)

- **04:45** Generación masiva dirigida a los errores del líder, en los cuatro modelos abiertos de Helmcode a la vez. Son unas 900 peticiones de 20 problemas, con ocho focos sacados del mapa de errores:
  - lógica (27 % de acierto);
  - enunciados largos con varias condiciones (33 %);
  - medida y tiempo (38 %);
  - geometría sin figura (42 %);
  - conteo con trampas;
  - «cuál de las opciones»;
  - catalán (6-9 puntos por debajo del inglés);
  - las lecciones de los fallos reales.

  El 40 % va en catalán y los programas tienen 8 líneas como máximo.
- **04:46** Primer filtro sobre los 512 primeros: 299 pasan la ejecución (58 %).
- **04:51** Prueba del segundo filtro: otro modelo abierto resuelve a ciegas cada problema escribiendo su propio programa, igual que el alumno, y solo se guardan los problemas en los que los dos coinciden. Sale 8 de 8 con gemma4 y 8 de 8 con qwen3.6.
- **05:44** Primera mezcla v4: 2.018 problemas con doble filtro. Entre los que el resolvedor contestó, coinciden el 89 %. Pero 2.951 se quedan sin respuesta: qwen3.6 ignora el formato JSON pedido y contesta con un bloque de código por problema.
- **05:47** **Fallo cazado antes de entrenar:** 365 de los ejemplos nuevos son programas de una línea tipo `print(6)`. Cuando el resolvedor a ciegas daba un programa más corto, se usaba el suyo, y qwen3.6 a veces imprime la constante. El entrenamiento de v4 se para al minuto. Al revisar aparece el mismo vicio en las mezclas anteriores: 141 constantes en v2 y 289 en v3.
- **05:54** **v4 corregida (17.904 ejemplos).** Fuera las «constantes puras» de todas las fuentes (`print(48)`, o `x = 48` y `print(x)` sin ninguna operación), con 343 menos en la parte v3. Se quedan los de una línea que sí calculan, como `print(36 // 3 - 36 // 4)`: en la placa cada token cuesta 0,37 s.
- **06:15** **v4b (19.984 ejemplos):** 4.014 problemas dirigidos con doble filtro (coinciden el 87 %), 2.111 de ellos en catalán. El filtro a ciegas se cortó al 82 % por falta de memoria en la torre. Lo hecho estaba guardado por problema, así que se montó la mezcla con eso.
- **06:20-06:50** **Sopas de modelos.** Se promedian los pesos de varios 1.7B entrenados: 1 minuto y 4,5 GB de RAM con `sopa_ligera.py`. Sumando la demo (100) y val sin repetidos (242):

  | Sopa | Demo | Val | Suma |
  |---|---|---|---|
  | `17b_lora32_v2` solo | 57 | 97 | 154 |
  | v2 + v2_lr2e4 | 58 | 104 | 162 |
  | v2 + v2_lr2e4 + v3 + v3_2ep | 60 | 107 | 167 |
  | v3 + v3_2ep | 63 | 105 | 168 |
  | v2 ×3 + v3 ×2 | 66 | 103 | 169 |
  | **v3 + v3_2ep + v4c (la v4 limpia)** | **69** | **108** | **177** |

  Los v3 sueltos bajaban en val (escribían el triple de programas `print(constante)`, que solo aciertan el 31 % de las veces que casan), pero en sopa suben. Con la v4 limpia, en la sopa líder los programas que casan aciertan 58 de 65 en la demo. `predict.py` añade dos cambios: rechazar el programa que imprime una constante (pide otro) y probar el programa también en los problemas con figura.
