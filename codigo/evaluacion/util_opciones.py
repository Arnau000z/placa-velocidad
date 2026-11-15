"""Utilidades compartidas: casar la salida de un programa o un texto con las opciones A-E."""
import math
import re

LETTERS = "ABCDE"


def parse_value(s):
    """Convierte '3/4', '2√3 cm²', '3,5 m', '45°', '12 %' en un número; None si no se puede."""
    t = str(s).strip().lower()
    if "!" in t or re.search(r"(?<![\d.])\d{7,}(?!\.)", t) or t.count("^") > 1 or t.count("**") > 1:
        return None  # enteros enormes no; decimales largos (0.3333333333) sí
    t = re.sub(r"[€$%°º]", " ", t)  # símbolos: en cualquier posición, con o sin espacio
    t = re.sub(r"\b(km|cm|mm|m|kg|g|l|ml|min|h|s|hores|horas|hours|minuts|minutos|minutes|anys|años|years|dies|días|days)"
               r"(²|³|\^2|\^3)?(\s*/\s*(h|s|min))?\b", " ", t)
    t = t.replace("²", "**2").replace("³", "**3").replace("^", "**").replace("×", "*").replace("·", "*").replace("x", "*")
    t = t.replace("−", "-").replace("–", "-").replace("π", "*pi").replace("√", "*sqrt")
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    t = re.sub(r"sqrt\s*(\d+(\.\d+)?)", r"sqrt(\1)", t)
    t = re.sub(r"^\*", "", t.strip())
    t = re.sub(r"\(\s*\*", "(", t)
    t = re.sub(r"\s+", "", t).lstrip("*")
    if not t or not re.fullmatch(r"[\d.+\-*/()pisqrt]+", t) or re.search(r"\*\*\d{3,}", t):
        return None
    try:
        return float(eval(t, {"__builtins__": {}}, {"pi": math.pi, "sqrt": math.sqrt}))
    except Exception:
        return None


def norm_text(s):
    return re.sub(r"[\s.,;:]", "", str(s).strip().lower())


def match_option(output, options):
    """Devuelve (letra o None, última línea de la salida)."""
    out = output.strip().splitlines()[-1].strip() if output.strip() else ""
    if not out:
        return None, out
    if len(out) == 1 and out.upper() in LETTERS:
        return out.upper(), out
    for k in LETTERS:
        if k in options and norm_text(options[k]) == norm_text(out):
            return k, out
    v = parse_value(out)
    if v is None:
        return None, out
    best, best_err = None, 1e-6
    for k in LETTERS:
        ov = parse_value(options.get(k, ""))
        if ov is None:
            continue
        err = abs(ov - v) / max(1.0, abs(ov))
        if err < best_err:
            best, best_err = k, err
    return best, out


def numeric_options(options):
    vals = {k: parse_value(v) for k, v in options.items()}
    return all(v is not None for v in vals.values()) and len(vals) == 5


def extract_code(text):
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"```(?:python)?\s*\n(.*)$", text, re.S)
    return m.group(1) if m else text


def extract_answer(text):
    m = re.findall(r"Answer:\s*\**\s*\(?([A-E])\b", text)
    return m[-1] if m else None
