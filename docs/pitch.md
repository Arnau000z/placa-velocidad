# Pitch de 3 minutos

El reparto que propone el reto, con nuestras cifras. Ensayadlo con cronómetro al menos dos veces.

| Parte | Tiempo | Qué se ve |
|---|---|---|
| 1. El problema | 0:00-0:20 | La placa en la mano |
| 2. La demo | 0:20-1:50 | `python3 demo.py` en la placa (y la vista 3D en el portátil) |
| 3. Las cifras | 1:50-2:30 | Gráfica «Del azar al 69 %» |
| 4. Lo que aprendimos | 2:30-3:00 | Diapositiva o la vista «Las cifras» |

## 1. El problema (20 s)

> «Esto es una Arduino UNO Q: una CPU de móvil de hace años, 4 GB de memoria y sin internet. Le damos un problema del Canguro matemático y tiene 60 segundos para elegir la respuesta. El modelo que trae el reto acierta un 21 %, lo mismo que tirar una moneda de cinco caras. Nosotros sacamos un 69 %.»

## 2. La demo (90 s)

Antes de empezar: la wifi apagada, los servicios arrancados y `python3 demo.py` abierto en la terminal, con letra grande.

1. Pulsad Enter con el primer problema (inglés, contar dígitos).
   > «El modelo no razona en prosa: no le da tiempo. A 2,7 palabras por segundo, un razonamiento no cabe en un minuto.»
2. Mientras sale el programa:
   > «Escribe un programa de Python de cinco líneas. La placa lo ejecuta en milisegundos y el resultado se compara con las opciones.»
3. Cuando sale la respuesta:
   > «Correcta, en unos 30 segundos de los 60.»
4. Segundo problema, en catalán (las encajadas):
   > «Funciona igual en catalán, porque el programa no depende del idioma.»
5. Si sobra tiempo, la vista 3D en el portátil:
   > «Así va un problema por dentro: el enunciado, la letra rápida, el programa, la ejecución y la respuesta, contra el reloj de 60 segundos.»

Si algo falla en directo, poned el vídeo de reserva.

## 3. Las cifras (40 s)

> «Del 21 % del modelo del reto al 37 % con nuestro sistema y el mismo tipo de modelo sin entrenar. Al 57 % con un modelo entrenado. Al 69 % con el modelo final: la media de los pesos de diez modelos entrenados con veinte mil programas que comprobamos ejecutándolos uno a uno. Cuando el programa casa con una opción, acierta 58 de cada 65 veces. Y en val de M3Kang, en inglés y catalán, 116 de 242.»

Si preguntan por M3Kang:
> «Lo usamos para fabricar el entrenamiento: programas verificados de sus problemas, y sus problemas como modelo de estilo para generar miles de problemas nuevos. Y como banco de errores: lo analizamos por tema, idioma y nivel.»

## 4. Lo que aprendimos (30 s)

> «Tres cosas. Uno: en una placa así, el tiempo es la métrica; una idea que acierta el 50 % sin reloj se queda en el 19 % con él. Dos: un programa verificado vale más que una explicación; entrenar con explicaciones empeoró el modelo nueve puntos. Tres: el RAG con ejemplos parecidos, que era la idea obvia, no ayudaba y no cabía en el tiempo. Lo siguiente sería enseñar al modelo a plantear mejor, porque el 75 % de sus fallos son de planteamiento, no de cálculo.»

## Preguntas probables

| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué no un modelo más grande? | Un 4B sabe más (hasta 70 % sin reloj), pero en la placa solo leer el enunciado le cuesta 35 s. No cabe. |
| ¿Usáis la nube en el examen? | No. Todo corre en la placa, sin red. La nube solo se usó para entrenar. |
| ¿Qué pasa con las figuras? | El examen no trae las imágenes. Contestamos con lo que da el texto (5 de 20 en la demo) y con la mediana de las opciones como reserva. |
| ¿Es determinista? | Sí: temperatura 0 y semilla fija, como pide el reto. |
| ¿Cuánto tarda? | De media, 38-42 s por problema; nunca pasa de 60 s en la simulación. |
