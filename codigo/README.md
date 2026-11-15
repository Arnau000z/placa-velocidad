# Código

Copia de trabajo de las piezas principales del proyecto. Las rutas absolutas (`D:\Datathon_A\…`, `/root/dt/…`) son las de la torre y las máquinas de la nube; para reproducirlo hay que ajustarlas.

| Carpeta | Fichero | Qué hace |
|---|---|---|
| `entrega/` | `predict.py` | El sistema que corre en la placa: repetidos, letra, programa, reintentos y reserva ([explicado aquí](../docs/03-sistema.md)) |
| | `sim_demo.py` | Pasa `predict.py` por la demo o por val con el reloj de la placa (`--tps-forzado`) y puntúa |
| | `auto_sim.py` | Espera a que cada candidato termine en la nube, baja su GGUF por trozos con md5, lo sirve y lo simula |
| `evaluacion/` | `eval_variantes.py` | Rejilla de más de 40 formas de preguntar (letra, razonar, valor, programa, comprobador de opciones, votos…) con tiempo de placa estimado |
| | `util_opciones.py` | Casar la salida de un programa o un texto con las opciones: fracciones, raíces, unidades, euros, porcentajes, decimales con coma |
| | `duplicados.py` | Estudio de problemas repetidos entre train y val con bge-m3 |
| `entrenamiento/` | `entrenar.py` | LoRA o ajuste completo con transformers + peft, en bf16 o QLoRA |
| | `entrenar_grpo.py` | GRPO con recompensa verificable: el programa se ejecuta y se puntúa si casa con la opción correcta |
| | `exportar.sh` | Junta el LoRA con la base, lo pasa a GGUF y lo cuantiza con llama.cpp |
| | `trabajo_lora_total.sh` | Trabajo de cola: entrenar, exportar a Q8_0 y examinar en la demo y en val |
| | `cadena_3090.sh` | Cadena larga para una 3090: LoRA y examen, sin que la gráfica se quede parada |
| | `mezclar_sft.py` | Junta todas las fuentes de programas verificados en el formato exacto de la placa |
| `datos_sinteticos/` | `prompt_generador.txt` | El encargo para generar problemas al estilo Canguro con su programa |
| | `generar_helmcode.py` | Generación en paralelo con los modelos abiertos de Helmcode |
| | `traducir_helmcode.py` | Traducción al catalán de problemas ya verificados |
| | `control_helmcode.py` | Segunda verificación: otro modelo resuelve a ciegas |
| | `verificar_sintetico.py` | Ejecuta cada programa y se queda con los que imprimen la opción marcada |
| | `generar_masivo.py` | Generación masiva dirigida a los errores del modelo líder: lógica, enunciados largos, medida, geometría sin figura, conteo, «cuál de las opciones», catalán y lecciones de sus fallos reales |
| | `verificar_masivo.py` | Doble filtro: el programa del generador acierta al ejecutarlo y otro modelo, resolviendo a ciegas, también |
| | `helmcode.py` | Cliente mínimo de la API, con reintentos |
| `nube/` | `nube.py` | Alquilar, arrancar, subir, ejecutar y bajar en vast.ai |
| | `vigia3.py` | Vigía cada 2 minutos que rellena las máquinas paradas desde su cola |

### Añadido la noche del 15/11: sopas, datos dirigidos y análisis de errores

| Carpeta | Fichero | Qué hace |
|---|---|---|
| `entrenamiento/` | `sopa_ligera.py` | **Cómo se hizo el modelo final**: base + media de los cambios (B·A·alfa/r) de varios LoRA del mismo Qwen3-1.7B, matriz a matriz (~4,5 GB de RAM), y a GGUF Q8_0 |
| | `sopa_loras.py` | Primera versión de la sopa (más simple, ~10 GB de RAM) |
| | `trabajo_v2.sh` | Trabajo de cola con base elegible (`BASE`), puerto propio y semilla (`SEMILLA`) |
| | `grpo_2b.sh` | GRPO con LoRA del Qwen3.5-2B (descartado: no mejora en la placa) |
| `entrega/` | `puntuar.py` | Puntúa todas las simulaciones con las mismas reglas (sin repetidos, reserva E) para comparar modelos |
| | `sim_local.sh` | Sirve un GGUF en la torre y lo simula en la demo y en val, comprobando que el servidor sirve ese GGUF |
| | `cola_sopas.sh` + `cola_sopas.txt` | Cola de sopas, una a la vez y solo con RAM libre; el `.txt` lista la composición de cada sopa probada (`sopa_z10` es la final) |
| | `auto_loras.py` + `bajar_loras.py` | Bajan el adaptador LoRA de cada candidato en cuanto termina, para las sopas |
| | `predict_exp.py` | Experimento de «segunda opinión» (votar entre varios programas): no mejora, no se usa |
| `evaluacion/` | `errores_lider.py` | Mapa de errores del líder por vía (casa con otra opción, número que no es opción, cortado…) |
| | `diagnosticar_fallos.py` | Un modelo abierto diagnostica cada fallo (causa, explicación y pista mínima); de aquí salen las 48 lecciones |
| `datos_sinteticos/` | `generar_dirigido.py` | Generación dirigida a las 48 trampas que salen del diagnóstico |
| | `verificar_rapido.py` | `verificar_sintetico.py` con los programas en paralelo, y arma la mezcla sin volver a verificar |
| | `pistas_helmcode.py` | Pistas de 3-8 palabras (tipo y método) para el experimento de pistas (descartado: ni la pista perfecta sube) |
| `nube/` | `alquilar_n.py` | Alquila una gráfica grande y la registra con el número de máquina pedido |

La clave de Helmcode se lee de un fichero fuera del repositorio (`.helmcode_key`) y no se incluye.
