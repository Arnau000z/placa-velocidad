# Instrucciones para Claude (y otros asistentes) en este repositorio

Proyecto del equipo Impostors para el reto de Qualcomm «Math on the Edge» (Datathon FME 2026): un copiloto de matemáticas que corre entero en una **Arduino UNO Q 4 GB**. Dos partes que comparten placa y modelo:
- **Reason:** [`equipo/predict.py`](equipo/predict.py) con el modelo `sopa_z10-Q8_0.gguf` (Qwen3-1.7B + LoRA), servido por el servicio oficial `math-llm` en `127.0.0.1:8081`.
- **Teach:** la app de App Lab Math Coach ([`teach/`](teach/README.md)), en el puerto 7000, que usa el mismo modelo para la pista 3.

Responde al usuario en su idioma (el equipo trabaja en castellano y catalán).

## Si te piden ejecutar el examen (o cualquier evaluación) en la placa: hazlo así, siempre

1. **Comprueba que el modelo está listo** antes de nada:
   ```bash
   systemctl is-active math-llm                 # → active
   curl -s 127.0.0.1:8081/health; echo          # → {"status":"ok"}
   grep -o '\-m [^ ]*' /etc/systemd/system/math-llm.service   # → .../sopa_z10-Q8_0.gguf
   ```
   Si la placa acaba de arrancar, espera: el modelo tarda ~20 s en cargarse.
2. **Para todo lo que use el modelo o la CPU.** El servidor atiende **una sola petición a la vez** (`--parallel 1`):
   ```bash
   arduino-app-cli app stop ~/ArduinoApps/math-coach
   pgrep -af "predict.py|eval.py"               # no debe haber otro en marcha
   ```
   No lances nunca dos `predict.py` o `eval.py` a la vez, ni dejes a alumnos usando Math Coach durante el examen.
3. **(Recomendado) Calienta y comprueba** con los 5 problemas de ejemplo (~2 min; deben salir C, B, C, C, B):
   ```bash
   cd ~/datathon-UPC-maths-qualcomm-arduino-unoq
   python3 predict.py --input data/sample_problems.jsonl --output results/calentar.csv
   ```
4. **Ejecuta el examen de una sola vez**, desde el repo del reto:
   ```bash
   cd ~/datathon-UPC-maths-qualcomm-arduino-unoq
   python3 predict.py --input examen.jsonl --output results/examen_final.csv
   ```
   No lo partas en trozos. `predict.py` hace el **calentamiento él solo** antes del primer problema: espera a `/health` hasta 5 min y lanza una petición de calentamiento (hasta 4 min) que **no cuenta** para ningún problema. La primera lectura en frío del prompt de sistema tarda 71-78 s; después cada problema solo lee sus ~70 tokens nuevos.
5. **Revisa el CSV:** columnas `id, language, answer, seconds, status`, una letra A-E por problema y todos los `seconds` por debajo de 60 (en nuestras pruebas, máximo 53,8 s).
6. Después del examen, si hace falta, vuelve a arrancar Math Coach (ver [README](README.md#teach-math-coach-la-plataforma-de-clase-en-la-placa)).

**Entrada:** JSONL con las opciones ya en texto (formato de `data/sample_problems.jsonl` del reto). Si llega el parquet del reto con las opciones solo en la imagen, conviértelo antes **en un PC**, no en la placa, con `laptop/prepare_m3kang.py` del repo del reto (OCR):
```bash
python -X utf8 laptop/prepare_m3kang.py --parquet examen.parquet --languages eng,cat,esp --val-fraction 0 --out data/final
```
El resultado es `data/final/train.jsonl`; debe decir «Options read from the image: N/N».

## Lo que NO debes hacer

- **No cambies el modelo ni los parámetros del servicio** (contexto 4.096, 4 hilos, `--parallel 1`, `--cache-ram 0`, `--ctx-checkpoints 2`). El presupuesto de tiempo de `predict.py` está medido con ellos. No uses versiones de 4 bits: en esta CPU (Cortex-A53 sin `dotprod`) no van más rápido y aciertan menos.
- **No modifiques `predict.py` ni `config.env`** del repo del reto sin que el equipo lo pida explícitamente: es la versión congelada y verificada. Los originales del reto están en `predict_oficial.py` y `config.env.orig`.
- **No subas datos de M3Kang** a ningún sitio (licencia solo de investigación): ni `train.jsonl`, `val.jsonl`, imágenes, `index.db`, `bank.json` ni soluciones escritas. Revisa `git status` antes de cada `push`.
- **No escribas contraseñas por el usuario.** Los pasos con `sudo` (reinstalar servicios, apagar la placa) los teclea una persona.
- **No desenchufes la placa en caliente:** se apaga con `sudo poweroff`.

## Si algo falla

- El modelo no arranca: `journalctl -u math-llm -n 30`.
- Reinstalar los servicios con la configuración actual (pide `sudo`): `bash ~/datathon-UPC-maths-qualcomm-arduino-unoq/board/04_install_services.sh`.
- Plan B, volver al modelo oficial del reto: `cd ~/placa-velocidad && ./instalar_en_placa.sh --deshacer`. Volver al modelo del equipo: `./instalar_en_placa.sh`.
- El modelo se descarga de la release [`modelo-final`](https://github.com/Arnau000z/placa-velocidad/releases): `sopa_z10-Q8_0.gguf`, md5 `c1ba1d47e8f818378e27be6a7c1a01b2`.

## Dónde está cada cosa

- [`README.md`](README.md): qué hace, cómo responde al reto, resultados, análisis de errores y la lista completa para el mejor resultado.
- [`instalar_en_placa.sh`](instalar_en_placa.sh): instala el modelo y `predict.py` en una placa con los pasos 0-10 del reto y lo prueba.
- [`teach/`](teach/README.md): Math Coach. Qué modelo usa y cuándo: [`teach/docs/quan-s-utilitzen-els-models.md`](teach/docs/quan-s-utilitzen-els-models.md).
- [`docs/`](docs/): historia, sistema, modelos, datos, resultados y lo que no funcionó.
