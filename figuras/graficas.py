"""Genera las gráficas de docs/ a partir de los resultados medidos (cifras copiadas de docs/resultados.md).

python figuras/graficas.py   → figuras/*.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

AQUI = Path(__file__).resolve().parent
SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_2 = "#52514e"
REJILLA = "#e4e3df"
SERIE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
NEUTRO = "#b9b8b2"

plt.rcParams.update({
    "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
    "font.size": 11, "text.color": TEXTO, "axes.labelcolor": TEXTO_2, "xtick.color": TEXTO_2, "ytick.color": TEXTO,
    "axes.edgecolor": REJILLA, "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
})


def titulo(ax, t, sub):
    ax.set_title(t, loc="left", fontsize=14, fontweight="bold", pad=26, color=TEXTO)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=10, color=TEXTO_2, va="bottom")


def barras_h(nombre, filas, t, sub, unidad="%", xmax=None, colores=None, nota=None):
    """Barras horizontales de una sola serie, de arriba abajo en el orden dado, con la cifra al final de cada barra."""
    alto = 0.55 * len(filas) + 1.6
    fig, ax = plt.subplots(figsize=(9, alto))
    etiquetas = [f[0] for f in filas][::-1]
    valores = [f[1] for f in filas][::-1]
    cols = (colores or [SERIE[0]] * len(filas))[::-1]
    ax.barh(etiquetas, valores, color=cols, height=0.62, edgecolor=SUPERFICIE, linewidth=2)
    tope = xmax or max(valores) * 1.18
    for i, v in enumerate(valores):
        txt = f"{v:g} {unidad}".strip() if unidad else f"{v:g}"
        ax.text(v + tope * 0.01, i, txt.replace(".", ","), va="center", fontsize=10.5, color=TEXTO)
    ax.set_xlim(0, tope)
    ax.xaxis.grid(True, color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    titulo(ax, t, sub)
    if nota:
        fig.text(0.01, 0.01, nota, fontsize=9, color=TEXTO_2)
    fig.tight_layout(rect=(0, 0.04 if nota else 0, 1, 1))
    fig.savefig(AQUI / f"{nombre}.png", dpi=160)
    plt.close(fig)


# 1. Progreso en el examen de prueba, simulado a la velocidad de la placa
barras_h("progreso", [
    ("Letra directa (1.7B, 1 token)", 24),
    ("predict.py + Qwen3-1.7B sin entrenar", 37),
    ("+ LoRA r32, dataset total", 51),
    ("+ LoRA r32, mezcla v2 (9.603 ejemplos)", 57),
    ("+ sopa de 2 LoRA v2", 58),
    ("+ datos dirigidos, sopa de 10 (final)", 70),
], "Del azar al 70 %", "Examen de prueba de la organización (100 filas), simulado a 4,6 / 2,7 tok/s", xmax=80,
    colores=[NEUTRO, SERIE[0], SERIE[0], SERIE[0], SERIE[0], SERIE[0]],
    nota="La letra directa no depende de la velocidad (1 token). Azar = 20 %.")

# 2. Rejilla de variantes de prompt (349 problemas de texto de val, 1.7B Q8, sin límite de tiempo)
rejilla = [("verifica_opciones", 50.7), ("k1_valor", 49.0), ("valor", 48.7), ("k1", 47.3), ("tipo", 45.3),
           ("ingles", 44.7), ("razona_primero", 44.1), ("k0", 43.6), ("base", 43.0), ("json", 37.8)]
barras_h("rejilla_variantes", rejilla, "Formas de preguntar al mismo modelo",
         "Qwen3-1.7B Q8 · 349 problemas de texto de val (M3Kang) · sin límite de tiempo", xmax=60,
         colores=[NEUTRO if n == "base" else SERIE[0] for n, _ in rejilla],
         nota="Gris: la variante de referencia. Con 349 problemas el ruido es de unos ±5 puntos.")

# 3. Comparativa de modelos con el sistema completo (T100: 50 con figura + 50 de texto)
barras_h("modelos_t100", [
    ("Qwen3-1.7B Q8", 45), ("Qwen3.5-2B Q8", 41), ("Qwen2.5-Math-1.5B Q8", 36), ("Qwen3.5-0.8B Q8", 33),
    ("Letra directa (baseline del reto)", 23),
], "Qué modelo sabe más", "Sistema completo (código + razonamiento) en 100 problemas de val · sin límite de tiempo",
    xmax=60, colores=[SERIE[0]] * 4 + [NEUTRO])

# 4. Mapa de errores del modelo líder
barras_h("errores_lider", [
    ("Planteamiento equivocado", 75), ("Error de código o de cálculo", 17), ("Programa largo sin terminar", 10),
    ("No conoce el método", 1),
], "Por qué falla el modelo líder", "103 problemas fallados por 17b_lora32_v2 en la simulación de placa, clasificados uno a uno",
    unidad="", xmax=90)

# 5. Candidatos en la simulación de placa: dos medidas en %
cands = [("1.7B LoRA r32\n(dataset total)", 51, 86), ("Qwen3.5-2B LoRA r32\n(dataset total)", 53, 80),
         ("GRPO sobre\nLoRA r32", 50, 81), ("1.7B LoRA r32 v2\nlr 2e-4", 54, 88), ("1.7B LoRA r32 v2\n(líder)", 57, 89)]
fig, ax = plt.subplots(figsize=(10, 4.8))
x = range(len(cands))
demo = [c[1] for c in cands]
val = [round(c[2] / 246 * 100, 1) for c in cands]
w = 0.36
b1 = ax.bar([i - w / 2 for i in x], demo, w, color=SERIE[0], label="Examen de prueba (100 filas)", edgecolor=SUPERFICIE, linewidth=2)
b2 = ax.bar([i + w / 2 for i in x], val, w, color=SERIE[1], label="Val M3Kang, texto eng+cat (246 filas)", edgecolor=SUPERFICIE, linewidth=2)
for bars, vals in ((b1, demo), (b2, val)):
    for r, v in zip(bars, vals):
        ax.text(r.get_x() + r.get_width() / 2, v + 0.8, f"{v:g}".replace(".", ","), ha="center", fontsize=9.5, color=TEXTO)
ax.set_xticks(list(x))
ax.set_xticklabels([c[0] for c in cands], fontsize=9.5)
ax.set_ylim(0, 70)
ax.set_ylabel("aciertos (%)")
ax.yaxis.grid(True, color=REJILLA, linewidth=0.8)
ax.set_axisbelow(True)
ax.tick_params(axis="x", length=0)
ax.legend(frameon=False, loc="upper left", fontsize=9.5)
titulo(ax, "Candidatos para la placa", "predict.py final simulado a 4,6 / 2,7 tok/s · val sin la vía de duplicados")
fig.tight_layout()
fig.savefig(AQUI / "candidatos.png", dpi=160)
plt.close(fig)

# 6. Anatomía de un problema en la placa (estimación con las velocidades medidas)
tramos = [("Leer el enunciado\n~70 tokens a 4,6 tok/s", 15, SERIE[0]), ("Letra + programa\n~50 tokens a 2,7 tok/s", 19, SERIE[1]),
          ("Ejecutar\ny casar", 3, SERIE[2]), ("Margen para reintentar", 19, "#e9e8e4"), ("Reserva", 4, NEUTRO)]
fig, ax = plt.subplots(figsize=(10, 2.9))
izq = 0
for nombre, s, col in tramos:
    ax.barh([0], [s], left=izq, color=col, height=0.5, edgecolor=SUPERFICIE, linewidth=2)
    ax.text(izq + s / 2, 0, f"{s} s", ha="center", va="center", fontsize=10.5, color=TEXTO, fontweight="bold")
    ax.text(izq + s / 2, -0.42, nombre, ha="center", va="top", fontsize=9, color=TEXTO_2)
    izq += s
ax.axvline(56, color=TEXTO_2, linewidth=1, linestyle=(0, (3, 3)))
ax.text(56, 0.36, "límite útil 56 s", ha="center", fontsize=9, color=TEXTO_2)
ax.set_xlim(0, 60)
ax.set_ylim(-1.15, 0.6)
ax.set_yticks([])
ax.set_xticks(range(0, 61, 10))
ax.set_xlabel("segundos")
titulo(ax, "Un problema en 60 segundos", "Reparto típico en la UNO Q con el prompt de sistema en caché (media simulada: 34 s)")
fig.tight_layout()
fig.savefig(AQUI / "presupuesto_tiempo.png", dpi=160)
plt.close(fig)
print("hecho:", sorted(p.name for p in AQUI.glob("*.png")))
