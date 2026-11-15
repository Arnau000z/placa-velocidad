# Lo que no funcionó

Más de la mitad del trabajo fue descartar ideas con datos. Esta página las reúne para no repetirlas.

| Idea | Lo que se midió | Por qué se dejó |
|---|---|---|
| Pedir solo la letra | 0.8B 21 %, 2B 22 %, 1.7B 24 % (demo) | Es azar. El 0.8B contesta D 500 veces de 789; el 2B, B 571 veces. |
| Mejorar la pregunta de la letra | «The correct option is (» 21,8 %; logprobs 21,0 %; corregir el sesgo por letra 20,7 % | El modelo no tiene preferencia real por la respuesta correcta. |
| Contestar el valor en vez de la letra (0.8B) | 17,0 % | Peor. |
| **RAG** con ejemplos parecidos | 0.8B: 21 → 25 % con 2 ejemplos; 2B: 35 % con 2 ejemplos explicados frente a 40 % razonando sin ellos | Ver abajo. |
| Modelos de 4B y 8B | 45-49,5 % en la muestra de 200, hasta 70,8 % en val texto | No caben en 60 s: un 4B leería un enunciado en ~35 s. |
| Cuantizar a 4 bits | Q4_K_M: −5 a −7 puntos | La placa no lee más rápido en 4 bits. |
| Ajuste fino con explicaciones | −9 puntos (40,1 % frente a 49,0 %) | El modelo deja de escribir código y la prosa acierta menos. |
| Reintento dirigido con el error («el resultado no está entre las opciones») | 2B: +0; 1.7B: 2 de 8 | Cuesta otra lectura del enunciado entera. |
| Entrada y salida en JSON | 37,8 % frente a 43,0 % | Peor. |
| Prohibir comentarios en el código (`logit_bias` contra `#`) | 30-32 % frente a 41 % | Los comentarios ayudan al modelo a pensar. Mejor quitarlos de los datos de entrenamiento. |
| Dos programas por problema (T = 0 y T = 0,7) | 41 % frente a 45 % | El segundo acierta 2-3 de 6-7 y cuesta 30 s. Sí funciona como *reintento* cuando el primero no casa. |
| Pensar 40-150 tokens antes del programa | demo 55-56 % frente a 58-63 % | Igual o peor, y duplica el tiempo. |
| Quitar las opciones del prompt | 57 % frente a 58 % | Igual. |
| «Valor razonado» después del programa | En la placa nunca entra: tras el programa quedan 15-20 s | Usaba otro prompt de sistema y tiraba la caché. Retirado. |
| Casar con la opción numérica más cercana | 3 de 15 frente a 3 de 15 de la reserva | Convierte un fallo honesto en otro fallo. Apagado. |
| GRPO | 50 frente a 51 en la simulación de placa | Mejora val en la nube (+3,7) pero no la cadena que cabe en la placa. |
| **Pistas** antes del programa (3-8 palabras: tipo y método) | Incluso escritas mirando el propio problema: demo 61 frente a 57 y val 90 frente a 93 | En val la pista arregla 15 y rompe 18. Si con la pista «perfecta» no sube, la pista recuperada de train tampoco. |
| Qwen2.5-Math y Qwen2.5-Coder | 36 % y 40 % | Buen código, pero no siguen el formato o plantean peor. |
| Visión para las figuras (mmproj del 2B) | — | El examen no entrega las imágenes. Todo el esfuerzo pasó a texto. |
| Letra «a priori» según el nivel o la posición | — | Lo decidió el equipo: el modelo responde siempre. Solo queda la mediana como reserva. |

## RAG con bge-m3

Era la idea obvia del enunciado («a retrieval knowledge base»), y la probamos a fondo el primer día:

- **El buscador era excelente.** bge-m3 encontraba la versión inglesa de un problema catalán o castellano el 100 % de las veces; el bge-small del reto, el 74 %.
- **Pero los ejemplos no subían la nota.** Con el 0.8B, +4 puntos como mucho. Con el 2B, poner 2 ejemplos explicados dio el 35 %, frente al 40 % de razonar sin ellos. La mejor variante, 2 programas verificados de problemas parecidos, se quedó en el 41 %: dentro del ruido.
- **En un fallo con un ejemplo casi idéntico explicado al lado**, el modelo copió el método y lo ejecutó mal. El RAG da el método; lo que falla es la ejecución.
- **En la placa no cabe.** Dos ejemplos son unos 300 tokens más por problema: unos 65 s de lectura. Además cambian en cada problema y rompen la caché del prompt de sistema. Y bge-m3 ocupa 600 MB de RAM.

Lo que el RAG pretendía aportar (cómo se resuelve cada tipo de problema) acabó **dentro de los pesos**: el LoRA ha visto 9.603 programas verificados. Así no paga tiempo de lectura ni memoria.

El único uso de la búsqueda que sobrevive es el **detector de repetidos**, y sin modelo de embeddings: misma lista de opciones y `difflib` sobre el enunciado. Un error en la primera versión (el número del problema al principio del enunciado cambiaba entre niveles) hacía que detectara 0 de 789. Corregido: 13 de 13.

## El 0.8B del reto

- Sin límite de tiempo, resuelve el 33 % del examen de prueba.
- Con el reloj de la placa, como mucho el 20 %: azar.
- Es el único que deja tiempo para escribir (lee a 10,6 y escribe a 5,8 tokens/s), pero no tiene nada que escribir.
- Ni el prompt, ni el RAG, ni razonar, ni el ajuste fino lo sacan de ~25 %.
