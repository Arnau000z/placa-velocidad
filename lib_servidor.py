"""Piezas comunes: arrancar y parar un llama-server con los mismos ajustes que el servicio del reto (math-llm),
leer la configuración de config.sh desde el entorno, cargar problemas y el predict.py del equipo."""
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
BIN = os.environ.get("BIN", os.path.join(HOME, "llama.cpp", "build", "bin"))
MODELOS = os.environ.get("MODELOS", os.path.join(HOME, "models"))
DATOS = os.environ.get("DATOS", os.path.join(HOME, "datathon-UPC-maths-qualcomm-arduino-unoq", "data"))
HILOS = int(os.environ.get("HILOS", "4"))
PUERTO = int(os.environ.get("PUERTO", "8090"))
PRINCIPAL = os.environ.get("PRINCIPAL", "Qwen_Qwen3-1.7B-Q8_0.gguf")
RES = os.environ.get("RES") or os.path.join(REPO, "resultados", "suelto")
os.makedirs(RES, exist_ok=True)

# Problemas de reserva por si en la placa no está val.jsonl (inventados, sin datos de M3Kang)
RESERVA = [
    {"id": "r1", "language": "eng", "text": "Anna has 36 stickers. She gives 9 stickers to each of her 3 friends and then buys 12 more. How many stickers does she have now?",
     "options": {"A": "21", "B": "15", "C": "27", "D": "39", "E": "18"}, "label": "A"},
    {"id": "r2", "language": "eng", "text": "A necklace repeats the pattern red, blue, blue, green without stopping. How many of the first 30 beads are green?",
     "options": {"A": "6", "B": "7", "C": "8", "D": "5", "E": "9"}, "label": "B"},
    {"id": "r3", "language": "cat", "text": "En una classe hi ha 28 alumnes. El nombre de nenes és 4 més que el de nens. Quantes nenes hi ha a la classe?",
     "options": {"A": "12", "B": "14", "C": "16", "D": "18", "E": "20"}, "label": "C"},
    {"id": "r4", "language": "eng", "text": "How many two-digit numbers have digits whose sum is 9?",
     "options": {"A": "8", "B": "9", "C": "10", "D": "7", "E": "11"}, "label": "B"},
    {"id": "r5", "language": "eng", "text": "A snail climbs 3 cm up a wall each day and slides back 1 cm each night. The wall is 11 cm high. On which day does the snail reach the top?",
     "options": {"A": "4", "B": "5", "C": "6", "D": "3", "E": "7"}, "label": "B"},
]


def ruta_modelo(nombre):
    return nombre if os.path.isabs(nombre) or nombre.startswith("./") else os.path.join(MODELOS, nombre)


def flags(modelo, puerto=PUERTO, hilos=HILOS, ctx=4096):
    f = ["-m", modelo, "--host", "127.0.0.1", "--port", str(puerto), "--threads", str(hilos), "--ctx-size", str(ctx),
         "--parallel", "1", "--cache-ram", "0", "--ctx-checkpoints", "2", "--jinja", "--reasoning", "off", "--reasoning-budget", "0"]
    return f + os.environ.get("EXTRA_FLAGS", "").split()


def get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def post(url, payload, timeout=600):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def mem_libre_mb():
    try:
        for l in open("/proc/meminfo"):
            if l.startswith("MemAvailable:"):
                return int(l.split()[1]) // 1024
    except OSError:
        return None


def rss_mb(pid):
    try:
        for l in open(f"/proc/{pid}/status"):
            if l.startswith("VmRSS:"):
                return int(l.split()[1]) // 1024
    except OSError:
        return None


class Servidor:
    """with Servidor(modelo, log) as s: ... -> s.url, s.carga_s, s.rss_mb, s.system_info"""

    def __init__(self, modelo, log_path, puerto=PUERTO):
        self.modelo, self.log_path, self.puerto = modelo, log_path, puerto
        self.url = f"http://127.0.0.1:{puerto}"
        self.proc = None

    def __enter__(self):
        exe = os.path.join(BIN, "llama-server")
        if not os.path.exists(exe) and os.path.exists(exe + ".exe"):
            exe += ".exe"
        self.log = open(self.log_path, "w", encoding="utf-8", errors="replace")
        t0 = time.time()
        self.proc = subprocess.Popen([exe] + flags(self.modelo, self.puerto), stdout=self.log, stderr=subprocess.STDOUT)
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server se ha cerrado al arrancar; mira {self.log_path}:\n" + self.cola())
            try:
                if get(self.url + "/health")[0] == 200:
                    break
            except Exception:
                pass
            if time.time() - t0 > 900:
                self.__exit__(None, None, None)
                raise RuntimeError("llama-server no responde tras 15 min")
            time.sleep(1)
        self.carga_s = time.time() - t0
        self.rss_mb = rss_mb(self.proc.pid)
        self.mem_libre_mb = mem_libre_mb()
        self.system_info = next((l.strip() for l in open(self.log_path, encoding="utf-8", errors="replace") if "system_info" in l), "")
        return self

    def cola(self, n=15):
        try:
            return "".join(open(self.log_path, encoding="utf-8", errors="replace").readlines()[-n:])
        except OSError:
            return ""

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.close()


def cargar_predict(ruta=None):
    """El predict.py del equipo: el de PREDICT, o el de equipo/ en este repo."""
    ruta = ruta or os.environ.get("PREDICT") or os.path.join(REPO, "equipo", "predict.py")
    if not os.path.exists(ruta):
        return None, ruta
    spec = importlib.util.spec_from_file_location("predict_equipo", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, ruta


def cargar_problemas(ruta, n):
    """n problemas repartidos por todo el fichero (mezcla niveles e idiomas); los de reserva si no hay fichero."""
    try:
        todos = [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]
    except OSError:
        todos = []
    if not todos:
        print(f"  (no encuentro {ruta}: uso {len(RESERVA)} problemas de reserva)", file=sys.stderr)
        return RESERVA[:n], "reserva"
    paso = max(1, len(todos) // n)
    return todos[::paso][:n], ruta
