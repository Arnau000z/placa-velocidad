# Velocidad en la placa

Pruebas para medir en la Arduino UNO Q lo que no se puede simular desde el PC: a qué velocidad lee y escribe cada modelo, cuánto ocupa, si se frena por calor y cuánto tarda de verdad `predict.py` con el límite de 60 s.

Con esos datos se decide el modelo, la cuantización y el presupuesto de tokens de la entrega.

## Uso

**1. Llevar el repo a la placa** (desde el PC, con la placa por USB-C):

```powershell
.\subir_a_placa.ps1
```

Copia los scripts y el `predict.py` más reciente del equipo (`D:\Datathon_A\entrega\predict.py`). Por SSH vale igual: `scp -r placa-velocidad arduino@IP:~`.

**2. Medir** (en la placa):

```bash
cd ~/placa-velocidad
./todo.sh            # completo, unos 50 min
./todo.sh rapido     # solo 1.7B Q8 y Q4_0, unos 15 min
```

Pide la contraseña de `sudo` una vez: para los servicios `math-llm` y `math-embed` mientras mide y los vuelve a arrancar al acabar.

**3. Traer los resultados** (desde el PC):

```powershell
.\traer_resultados.ps1
```

O pega el contenido de `resultados/<placa>_<fecha>/resumen.md`.

## Qué hace cada paso

| Paso | Qué mide | Tiempo |
|---|---|---|
| `00_preparar.sh` | Compila `llama-bench` y baja los modelos que falten (el repo del reto no compila `llama-bench`) | 2-10 min, según la wifi |
| `01_info.sh` | CPU y sus instrucciones (dotprod, i8mm), frecuencias, temperatura, memoria y versión de llama.cpp | segundos |
| `02_bench.sh` | `llama-bench` de cada modelo: lee 200 tokens, escribe 64, 2 repeticiones | unos 20 min |
| `03_servidor.py` | `llama-server` con los ajustes del reto y el prompt de sistema del equipo en caché: carga, RAM y velocidad real por problema | unos 5 min |
| `04_cadena.py` | `predict.py` entero sobre 15 problemas de `val.jsonl`: aciertos, segundos por problema, cuántos pasan de 60 s, vías | unos 15 min |
| `vigia_temp.sh` | De fondo, cada 5 s: temperatura, MHz de cada núcleo, carga y memoria | toda la pasada |
| `resumen.py` | Lo junta todo en `resumen.md` | segundos |

Modelos que mide `llama-bench`: Qwen3-1.7B en Q8_0, Q4_0, Q4_K_M y Q6_K, Qwen3.5-0.8B Q8_0 (referencia: el README del reto da 11 t/s leyendo y 5 escribiendo) y Qwen3.5-2B Q4_0.

## Ajustes

Todo se cambia con variables al lanzar, por ejemplo `HILOS=3 ./todo.sh`:

| Variable | Por defecto | Para qué |
|---|---|---|
| `PRINCIPAL` | `Qwen_Qwen3-1.7B-Q8_0.gguf` | Modelo del servidor y de la cadena |
| `SOLO` | los 6 de la lista | `SOLO="a.gguf b.gguf"` mide solo esos |
| `EXTRA` | vacío | Modelos propios, p. ej. `EXTRA=~/models/afinado.gguf` |
| `MODELOS_SERVIDOR` | `PRINCIPAL` | Varios modelos en la prueba del servidor |
| `N_CADENA` | 15 (5 en rápido) | Problemas de la cadena completa |
| `HILOS` | 4 | Hilos de llama.cpp |
| `P_TOKENS`, `N_TOKENS`, `REPS` | 200, 64, 2 | Tamaños de `llama-bench` |
| `PREDICT` | `equipo/predict.py` | Otro `predict.py` |
| `DATOS` | `~/datathon-UPC-maths-qualcomm-arduino-unoq/data` | Dónde están `val.jsonl` y `train.jsonl` |

Cada paso se puede lanzar suelto (`./02_bench.sh`, `python3 03_servidor.py --modelos X.gguf`) y escribe en la misma carpeta de resultados si se exporta `RES`.

## Cómo leer el resumen

- **Programa que cabe**: tokens de programa que da tiempo a escribir en 56 s con un enunciado de 180 tokens y el sistema en caché. Es la misma cuenta que hace `predict.py`. Por debajo de unos 80 tokens, el programa corto ya no entra.
- **dotprod: no** quiere decir que llama.cpp va por el camino lento. Ahí el Q4_0 no tiene por qué leer más rápido que el Q8_0: lo dice la tabla.
- **Lee con caché** frente a **lee frío**: si se parecen, el prompt de sistema no se está reaprovechando.
- **Se frena por calor**: si la frecuencia baja con la carga, los tiempos del final del examen serán peores que los del principio.

No se sube nada de M3Kang: los problemas se leen de la placa, y si no están se usan cinco inventados.
