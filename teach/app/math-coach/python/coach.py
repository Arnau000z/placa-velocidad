"""Math coach: the hint ladder and the adaptive trainer, on the M3Kang problem map.

Standard library only, so the same code runs in the App Lab app (python/main.py), on the
board's Python, and in the measurement scripts on the laptop.

The map (data/bank.json, made by build_bank.py) holds every usable problem with its level,
topic, languages, optional written solution, and a bge-small embedding of its English text.
Nothing here needs the embedding server at run time: neighbours are dot products of the
stored vectors. Only rung 3 of the hint ladder calls the language model.
"""
import base64
import json
import os
import random
import re
import sqlite3
import threading
import time
import urllib.request
from array import array
from collections import Counter

try:  # App Lab's Python has numpy: all similarities in one matrix product (instant)
    import numpy as _np
except ImportError:  # the board's own python3 doesn't: pure Python, with a cache
    _np = None

LANGS = ("eng", "cat", "esp")
MAX_LEVEL = 7

# ---------------------------------------------------------------- topics
# name and method sentence per language; keyword rules on the English text, with a weight
TOPICS = {
    "logic": {
        "eng": ("Logic: who tells the truth", "Assume one statement is true, follow what it implies, and look for a contradiction."),
        "cat": ("Lògica: qui diu la veritat", "Suposa que una afirmació és certa, segueix-ne les conseqüències i busca una contradicció."),
        "esp": ("Lógica: quién dice la verdad", "Supón que una afirmación es cierta, sigue sus consecuencias y busca una contradicción."),
        "rule": (3, r"\b(liars?|lie|lies|lying|truth|truthful|knights?|knaves?|statements?)\b"),
    },
    "certainty": {
        "eng": ("Certainty and worst cases", "Think of the worst possible case first: how far can you go without getting what you want?"),
        "cat": ("Certesa i el pitjor cas", "Pensa primer en el pitjor cas possible: fins on pots arribar sense aconseguir el que vols?"),
        "esp": ("Certeza y el peor caso", "Piensa primero en el peor caso posible: ¿hasta dónde puedes llegar sin conseguir lo que quieres?"),
        "rule": (3, r"(to be sure|be certain|certain that|without looking|in the dark|guarantee|at random|probability)"),
    },
    "counting": {
        "eng": ("Counting and combinations", "List the cases in an organised way, or multiply the choices at each step, without counting any case twice."),
        "cat": ("Recompte i combinacions", "Fes una llista ordenada dels casos, o multiplica les opcions de cada pas, sense comptar cap cas dues vegades."),
        "esp": ("Conteo y combinaciones", "Haz una lista ordenada de los casos, o multiplica las opciones de cada paso, sin contar ningún caso dos veces."),
        "rule": (2, r"(how many (different )?(ways|routes|paths|arrangements|combinations|orders|possib\w+|towers|colou?rings)"
                    r"|\bin how many\b|\barrang\w+|\bcombinations?\b|\bchoose\b|\bpossible (routes|paths|orders)\b)"),
    },
    "ages": {
        "eng": ("Ages", "Name the ages with letters and remember that the difference between two people's ages never changes."),
        "cat": ("Edats", "Posa lletres a les edats i recorda que la diferència d'edat entre dues persones no canvia mai."),
        "esp": ("Edades", "Pon letras a las edades y recuerda que la diferencia de edad entre dos personas nunca cambia."),
        "rule": (2, r"\b(ages?|years old|older|younger|born|birthdays?)\b"),
    },
    "speed": {
        "eng": ("Speed and distance", "Use distance = speed × time; when two things move towards or after each other, add or subtract their speeds."),
        "cat": ("Velocitat i distància", "Fes servir distància = velocitat × temps; si dues coses s'acosten o se segueixen, suma o resta les velocitats."),
        "esp": ("Velocidad y distancia", "Usa distancia = velocidad × tiempo; si dos cosas se acercan o se persiguen, suma o resta sus velocidades."),
        "rule": (2, r"(km/h|m/s|\bspeeds?\b|\bfaster\b|\bslower\b|per hour|\btravel\w*\b)"),
    },
    "time": {
        "eng": ("Clocks, time and calendars", "Work in a single unit (minutes or days) and count step by step from a moment you know."),
        "cat": ("Rellotges, temps i calendaris", "Treballa amb una sola unitat (minuts o dies) i compta pas a pas des d'un moment que coneguis."),
        "esp": ("Relojes, tiempo y calendarios", "Trabaja con una sola unidad (minutos o días) y cuenta paso a paso desde un momento que conozcas."),
        "rule": (1, r"\b(clocks?|o'clock|minutes?|hours?|a\.m\.|p\.m\.|midnight|noon|calendar|mondays?|tuesdays?|wednesdays?"
                    r"|thursdays?|fridays?|saturdays?|sundays?|weeks?|months?|dates?)\b"),
    },
    "space": {
        "eng": ("Cubes, dice and solids", "Picture the solid layer by layer or face by face; on a normal die, opposite faces add up to 7."),
        "cat": ("Cubs, daus i cossos", "Imagina el cos capa per capa o cara per cara; en un dau normal, les cares oposades sumen 7."),
        "esp": ("Cubos, dados y cuerpos", "Imagina el cuerpo capa a capa o cara a cara; en un dado normal, las caras opuestas suman 7."),
        "rule": (2, r"\b(cubes?|cubic|dice|die|prisms?|pyramids?|faces|edges|vertices|solids?|box|boxes|towers?)\b"),
    },
    "plane": {
        "eng": ("Lengths, areas and angles", "Draw the figure, split it into simple shapes (squares, rectangles, triangles) and write every length you know on it."),
        "cat": ("Longituds, àrees i angles", "Dibuixa la figura, divideix-la en formes senzilles (quadrats, rectangles, triangles) i escriu-hi totes les longituds que coneguis."),
        "esp": ("Longitudes, áreas y ángulos", "Dibuja la figura, divídela en formas sencillas (cuadrados, rectángulos, triángulos) y escribe en ella todas las longitudes que conozcas."),
        "rule": (1, r"(\bareas?\b|perimeters?|triangles?|\bsquares?\b|rectangles?|circles?|\bangles?\b|polygons?|hexagons?|pentagons?"
                    r"|octagons?|radius|diameters?|diagonals?|cm²|m²|\bsegments?\b|parallelograms?|trapez\w*|°)"),
    },
    "numbers": {
        "eng": ("Digits and divisibility", "Look at the last digit, at even and odd, or at divisibility: one simple property often rules out most options."),
        "cat": ("Xifres i divisibilitat", "Fixa't en l'última xifra, en parells i senars o en la divisibilitat: sovint una propietat senzilla descarta gairebé totes les opcions."),
        "esp": ("Cifras y divisibilidad", "Fíjate en la última cifra, en pares e impares o en la divisibilidad: a menudo una propiedad sencilla descarta casi todas las opciones."),
        "rule": (1, r"\b(digits?|divisible|divisors?|multiples?|primes?|remainders?|even|odd|palindrom\w*|integers?|factors?|perfect squares?)\b"),
    },
    "patterns": {
        "eng": ("Sequences and patterns", "Write the first terms, find what repeats, and use the rule to jump straight to the position you need."),
        "cat": ("Successions i patrons", "Escriu els primers termes, troba què es repeteix i fes servir la regla per saltar directament a la posició que necessites."),
        "esp": ("Sucesiones y patrones", "Escribe los primeros términos, encuentra lo que se repite y usa la regla para saltar directamente a la posición que necesitas."),
        "rule": (1, r"\b(sequences?|patterns?|terms?|positions?|continues|next number|repeat\w*)\b"),
    },
    "proportions": {
        "eng": ("Fractions, percentages and averages", "Pick a convenient total (100, or a common multiple of the denominators) and work with concrete numbers."),
        "cat": ("Fraccions, percentatges i mitjanes", "Tria un total còmode (100, o un múltiple comú dels denominadors) i treballa amb nombres concrets."),
        "esp": ("Fracciones, porcentajes y medias", "Elige un total cómodo (100, o un múltiplo común de los denominadores) y trabaja con números concretos."),
        "rule": (1, r"(%|percent\w*|\bfractions?\b|\bhalf\b|\bthirds?\b|\bquarters?\b|\baverage\b|\bratio\b|\bproportion\w*"
                    r"|\bone-\w+ths?\b|\btwo-thirds\b|\bthree-\w+\b)"),
    },
    "arithmetic": {
        "eng": ("Arithmetic and word problems", "Turn the sentences into a short equation with a letter for the unknown, then check the options in it."),
        "cat": ("Aritmètica i problemes d'enunciat", "Converteix les frases en una equació curta amb una lletra per a la incògnita i comprova-hi les opcions."),
        "esp": ("Aritmética y problemas de enunciado", "Convierte las frases en una ecuación corta con una letra para la incógnita y comprueba en ella las opciones."),
        "rule": (0, r"$^"),
    },
}
TOPIC_ORDER = list(TOPICS)  # tie-break: earlier topics win


def classify_topic(english_text):
    """Topic key from keyword rules, or None when no rule matches (the caller decides)."""
    text = english_text.lower()
    scores = {t: v["rule"][0] * len(re.findall(v["rule"][1], text)) for t, v in TOPICS.items()}
    best = max(TOPIC_ORDER, key=lambda t: (scores[t], -TOPIC_ORDER.index(t)))
    return best if scores[best] > 0 else None


def topic_name(topic, lang):
    return TOPICS[topic][lang if lang in LANGS else "eng"][0]


# ---------------------------------------------------------------- the map
class Bank:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.meta = data["meta"]
        self.problems = data["problems"]
        for i, p in enumerate(self.problems):
            v = array("f")
            v.frombytes(base64.b64decode(p.pop("vec")))
            p["vec"] = v
            p["_i"] = i
        self.by_id = {p["id"]: p for p in self.problems}
        # Written solutions translated into Catalan and Spanish (tools/translate_explanations.py):
        # only translations that passed every automatic check are in this file.
        i18n = os.path.join(os.path.dirname(path), "explanations_i18n.json")
        self.translated = 0
        if os.path.exists(i18n):
            with open(i18n, encoding="utf-8") as f:
                for pid, langs in json.load(f)["translations"].items():
                    if pid in self.by_id and self.by_id[pid].get("explanation"):
                        self.by_id[pid]["explanation_i18n"] = langs
                        self.translated += 1
        if _np is not None:
            m = _np.array([_np.frombuffer(p["vec"].tobytes(), dtype=_np.float32) for p in self.problems])
            self._X = m
            self._sims = m @ m.T  # 810 x 810 cosine similarities (vectors are unit length)
        else:
            self._X, self._sims, self._cache = None, None, {}
        # Similarity above which two problems are the same problem (Kangaroo reuses problems
        # across levels). It depends on the model: the same pair scores 0.99 with bge-small
        # and 0.93 with bge-m3, and bge-m3 has copies with the same answer down to 0.89.
        self.near_copy = 0.88 if len(self.problems[0]["vec"]) >= 1024 else 0.95

    def sim(self, a, b):
        if self._sims is not None:
            return float(self._sims[a["_i"], b["_i"]])
        key = (a["_i"], b["_i"]) if a["_i"] < b["_i"] else (b["_i"], a["_i"])
        s = self._cache.get(key)
        if s is None:
            s = self._cache[key] = sum(x * y for x, y in zip(a["vec"], b["vec"]))
        return s

    def nearest(self, target, candidates, bonus=None):
        """The candidate most similar to target (vectors are unit length, so dot = cosine)."""
        best, best_score = None, -2.0
        for c in candidates:
            if c is target:
                continue
            score = self.sim(target, c) + (bonus(c) if bonus else 0.0)
            if score > best_score:
                best, best_score = c, score
        return best, best_score

    def view(self, p, lang, with_answer=False):
        """A problem as the page shows it: text and options in the student's language."""
        code = lang if lang in p["langs"] else "eng"
        shown = {"id": p["id"], "level": p["level"], "year": p["year"], "lang": code,
                 "text": p["langs"][code]["text"], "options": p["langs"][code]["options"]}
        if with_answer:
            translated = (p.get("explanation_i18n") or {}).get(lang)
            shown.update(label=p["label"], value=p["langs"][code]["options"][p["label"]],
                         explanation=translated or p.get("explanation"),
                         explanation_lang=lang if translated else "eng")
        return shown


# ---------------------------------------------------------------- semantic families (for the teacher)
STOPWORDS = {
    "eng": set("""a about above after again all also an and any are as at be because been before being below between both
        but by can could did do does each few for from had has have he her here him his how i if in into is it its itself
        just me more most my no nor not now of off on once only or other our out over own same she should so some such than
        that the their them then there these they this those through to too under until up very was we were what when where
        which while who whom why will with would you your yours one two three four five six seven eight nine ten first second
        third number numbers many much make made shown figure following answer options option get got write written each every
        must need want wants other another different same equal total given what which example cannot value result
        equals following""".split()),
    "cat": set("""a al als amb aquest aquesta aquests aquestes cada com de del dels el els en entre es és està estan ha han
        hi i la les li lo ma més na no o per perquè però pot quan quant quants quanta quantes que què qui se si sobre son
        són també te té tenen un una uns unes va van ser seu seva seus seves nombre nombres dos tres quatre cinc sis set
        vuit nou deu figura opció resposta mateix mateixa altre altra cada tots totes quin quina quins quines després
        exemple cadascun cadascuna poden poder valor següents següent principi""".split()),
    "esp": set("""a al con como cada de del el ella en entre es está están ha han hay la las le lo los más no o para pero
        por que qué quien se si sobre son su sus también tiene tienen un una unos unas va van ser número números dos tres
        cuatro cinco seis siete ocho nueve diez figura opción respuesta mismo misma otro otra cada todos todas cuántos
        cuántas cuánto cuál cuáles después ejemplo pueden poder valor siguientes siguiente principio""".split()),
}


def semantic_families(bank, k=24, iters=40, seed=0):
    """Groups the problems by meaning: spherical k-means on the bge-m3 vectors (numpy).
    Sets p['family'] on every problem and returns the number of families. Without numpy,
    the keyword topics stand in for the families."""
    if bank._X is None:
        names = sorted({p["topic"] for p in bank.problems})
        for p in bank.problems:
            p["family"] = names.index(p["topic"])
        return len(names)
    X = bank._X
    n = len(X)
    rng = _np.random.default_rng(seed)
    centers = [X[rng.integers(n)]]
    for _ in range(1, k):  # k-means++ start, with cosine distance
        d = 1 - _np.max(X @ _np.array(centers).T, axis=1)
        d = _np.clip(d, 0, None) ** 2
        centers.append(X[rng.choice(n, p=d / d.sum())])
    C = _np.array(centers)
    labels = None
    for _ in range(iters):
        new = _np.argmax(X @ C.T, axis=1)
        if labels is not None and (new == labels).all():
            break
        labels = new
        for j in range(k):
            members = X[labels == j]
            if len(members):
                c = members.mean(axis=0)
                C[j] = c / (_np.linalg.norm(c) or 1)
    for p, lab in zip(bank.problems, labels):
        p["family"] = int(lab)
    bank.family_centers = C
    return k


def family_names(bank, lang):
    """A short name per family: its most common topic and the words that set it apart, in `lang`."""
    import math
    by_family = {}
    for p in bank.problems:
        by_family.setdefault(p["family"], []).append(p)
    stop = STOPWORDS.get(lang, set()) | STOPWORDS["eng"]
    docs = {}
    df_all = Counter()
    for p in bank.problems:
        code = lang if lang in p["langs"] else "eng"
        words = {w for w in _words(p["langs"][code]["text"]) if len(w) >= 4 and not w.isdigit() and w not in stop}
        docs[p["id"]] = words
        df_all.update(words)
    total = len(bank.problems)
    names = {}
    for fam, members in by_family.items():
        df = Counter()
        for p in members:
            df.update(docs[p["id"]])
        scored = sorted(df, key=lambda w: -(df[w] / len(members)) * math.log(total / df_all[w]) if df[w] >= 2 else 0)
        topic = Counter(p["topic"] for p in members).most_common(1)[0][0]
        names[fam] = {"topic": topic_name(topic, lang), "words": scored[:3], "size": len(members)}
    return names


# ---------------------------------------------------------------- adaptive trainer
def first_problem(bank, level, seen, rng):
    pool = [p for p in bank.problems if p["level"] == level and p["id"] not in seen] or \
           [p for p in bank.problems if p["level"] == level]
    return rng.choice(pool)


def next_problem(bank, current, correct, seen):
    """Right answer: the nearest unseen neighbour one level up.
    Wrong answer: the nearest unseen neighbour on the same topic, one level down.
    Returns (problem, reason) with a short reason code for the page and the log."""
    unseen = [p for p in bank.problems if p["id"] not in seen and p["id"] != current["id"]
              and bank.sim(current, p) < bank.near_copy]  # not the same problem again from another level
    level = current["level"]
    if correct:
        target = min(level + 1, MAX_LEVEL)
        tries = [("up", lambda p: p["level"] == target),
                 ("same-level", lambda p: p["level"] == level)]
    else:
        target = max(level - 1, 0)
        tries = [("down-same-topic", lambda p: p["level"] == target and p["topic"] == current["topic"]),
                 ("same-level-same-topic", lambda p: p["level"] == level and p["topic"] == current["topic"]),
                 ("down", lambda p: p["level"] == target)]
    tries.append(("any", lambda p: True))
    for reason, keep in tries:
        candidates = [p for p in unseen if keep(p)]
        if candidates:
            return bank.nearest(current, candidates)[0], reason
    return bank.nearest(current, [p for p in bank.problems if p["id"] != current["id"]])[0], "repeat"


# ---------------------------------------------------------------- hint ladder
def gives_answer_away(bank, current, other):
    """Kangaroo reuses problems across levels: a lower-level copy, shown solved, would give
    the answer away. Excluded: near-copies (bank.near_copy) and any solved problem whose
    answer has the same value, even by chance (a student who sees 'answer 4' may copy it).
    Measured with bge-small: without the second rule 3.8% of rung-1 problems had the same value."""
    if other["value"].strip().lower() == current["value"].strip().lower():
        return True
    return bank.sim(current, other) >= bank.near_copy


def rung1_easier_problem(bank, current):
    """Rung 1: the nearest solved problem at a lower level (same level only at level 0),
    never a near-copy of this problem. Problems with a written solution get a small bonus,
    so the student can read how it's done."""
    if current["level"] > 0:
        candidates = [p for p in bank.problems if p["level"] < current["level"]]
    else:
        candidates = [p for p in bank.problems if p["level"] == 0]
    candidates = [p for p in candidates if not gives_answer_away(bank, current, p)]
    return bank.nearest(current, candidates, bonus=lambda p: 0.03 if p.get("explanation") else 0.0)


def rung2_topic(bank, current, k=5):
    """Rung 2: the topic shared by this problem and its k nearest neighbours, and its method."""
    ranked = sorted((p for p in bank.problems if p is not current), key=lambda p: -bank.sim(current, p))[:k]
    votes = Counter([current["topic"]] + [p["topic"] for p in ranked])
    return votes.most_common(1)[0][0], dict(votes)


# Inside App Lab's container the board is 'msgpack-rpc-router' (172.17.0.1), where
# board/llm_bridge.py relays to the model; outside it, the model is on 127.0.0.1.
LLM_CANDIDATES = [u for u in (os.environ.get("COACH_LLM"), "http://127.0.0.1:8081", "http://msgpack-rpc-router:8081",
                              "http://172.17.0.1:8081") if u]
_llm_url = None


def llm_url():
    """The first model server that answers /health (inside App Lab's container 127.0.0.1 may not be the board)."""
    global _llm_url
    if _llm_url:
        return _llm_url
    for url in LLM_CANDIDATES:
        try:
            with urllib.request.urlopen(url + "/health", timeout=2) as r:
                if json.loads(r.read()).get("status") == "ok":
                    _llm_url = url
                    return url
        except (OSError, ValueError):
            continue
    return None


HINT_SYSTEM = {
    "eng": "You are a maths tutor for school students. Give ONE short hint, a single sentence of at most 25 words, "
           "that helps the student start the problem. Never give the answer, never say which option is correct, "
           "and never compute the final result.",
    "cat": "Ets un tutor de matemàtiques per a alumnes d'escola. Dona UNA sola pista curta, una frase de 25 paraules com a màxim, "
           "que ajudi l'alumne a començar el problema. No donis mai la resposta, no diguis quina opció és correcta "
           "i no calculis el resultat final. Respon en català.",
    "esp": "Eres un tutor de matemáticas para alumnos de escuela. Da UNA sola pista corta, una frase de 25 palabras como máximo, "
           "que ayude al alumno a empezar el problema. No des nunca la respuesta, no digas qué opción es correcta "
           "y no calcules el resultado final. Responde en español.",
}
HINT_ASK = {"eng": "Hint:", "cat": "Pista:", "esp": "Pista:"}


def _numbers(text):
    return re.findall(r"\d+(?:[.,]\d+)?(?:/\d+)?", text)


def leak_reason(hint, problem, lang):
    """Why a hint gives the answer away, or None. Conservative on purpose: a hint that
    contains the correct option's value is rejected, as the challenge asks."""
    low = hint.lower().replace(" ", " ")
    label = problem["label"]
    for code in {lang if lang in problem["langs"] else "eng", "eng"}:
        value = problem["langs"][code]["options"][label].lower().strip()
        nums = _numbers(value)
        if len(nums) == 1:
            n = nums[0].replace(",", ".")
            for found in _numbers(low):
                if found.replace(",", ".") == n:
                    return f"contains the answer's value {nums[0]}"
        elif value and len(value) >= 2 and re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", low):
            return f"contains the answer's text '{value}'"
    words = r"(answer|option|letter|choice|resposta|opció|opcio|lletra|respuesta|opción|opcion|letra)"
    if re.search(words + r"[^.]{0,12}\b" + label.lower() + r"\b", low) or re.search(r"\(\s*" + label.lower() + r"\s*\)", low):
        return f"names the correct letter {label}"
    return None


def first_sentence(text):
    text = " ".join(text.strip().split())
    # the small model sometimes talks about the hint instead of giving it: drop that part
    text = re.sub(r"^(\**\s*)?((la |una |the |a )?(pista|hint)( [^:]{0,40})?:)\s*", "", text, flags=re.I).strip(" \"'«»“”*")
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    return match.group(1) if match else text


def _words(text):
    return re.findall(r"\w+", text.lower())


def useless_reason(hint, problem, lang):
    """Why a hint teaches nothing, or None: too short, or it mostly repeats the problem's
    own words (measured on the board: 'Sira has a paper triangle.' for a problem that
    starts exactly like that)."""
    words = _words(hint)
    if len(words) < 6:
        return "too short"
    text = problem["langs"][lang if lang in problem["langs"] else "eng"]["text"]
    stated = set(_words(text))
    new = [w for w in words if w not in stated]
    if len(new) / len(words) < 0.25:
        return "repeats the problem"
    return None


HINT_VERSION = 2  # bump when the checks change: older cached hints are generated again


def ask_hint(problem, lang, seed=42, temperature=0.0, url=None, timeout=60):
    """One hint from the model. Returns (hint, seconds, prompt_tokens)."""
    url = url or llm_url()
    if not url:
        raise OSError("model server unreachable")
    code = lang if lang in problem["langs"] else "eng"
    view = problem["langs"][code]
    user = view["text"] + "\n" + "\n".join(f"{k}) {v}" for k, v in view["options"].items()) + "\n" + HINT_ASK[code]
    payload = {"messages": [{"role": "system", "content": HINT_SYSTEM[code]}, {"role": "user", "content": user}],
               "max_tokens": 60, "temperature": temperature, "seed": seed, "cache_prompt": True,
               "grammar": "root ::= [^\\n]+"}
    start = time.perf_counter()
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    hint = first_sentence(out["choices"][0]["message"]["content"])
    return hint, time.perf_counter() - start, out.get("timings", {}).get("prompt_n", 0)


def rung3_model_hint(problem, lang, url=None):
    """Up to two tries (temperature 0, then 0.8). A hint that leaks the answer is never
    returned; one that teaches nothing (useless_reason) isn't either. Then the page shows the
    topic's method instead."""
    attempts = []
    for seed, temperature in ((42, 0.0), (43, 0.8)):
        hint, seconds, tokens = ask_hint(problem, lang, seed=seed, temperature=temperature, url=url)
        leak = leak_reason(hint, problem, lang)
        useless = None if leak else useless_reason(hint, problem, lang)
        attempts.append({"hint": hint, "seconds": round(seconds, 2), "prompt_tokens": tokens, "leak": leak,
                         "useless": useless})
        if not leak and not useless:
            return {"hint": hint, "attempts": attempts, "v": HINT_VERSION}
    return {"hint": None, "attempts": attempts, "v": HINT_VERSION}


# ---------------------------------------------------------------- points
# A right answer is worth 10 x (level + 1): level 0 = 10 points, level 7 = 80. Each hint used
# takes away a quarter (rungs 1-3); seeing the solution, or a wrong answer, gives 0. Never negative.
HINT_FACTOR = (1.0, 0.75, 0.5, 0.25)


def points_for(level, correct, hints, solution_shown):
    if not correct or solution_shown:
        return 0
    return round(10 * (level + 1) * HINT_FACTOR[min(int(hints), 3)])


# ---------------------------------------------------------------- student profiles (SQLite)
SCHEMA = """
CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, lang TEXT NOT NULL,
                                     created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS state (student_id INTEGER PRIMARY KEY, problem_id TEXT NOT NULL, rung INTEGER NOT NULL,
                                  solution_shown INTEGER NOT NULL, started REAL NOT NULL, reason TEXT);
CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, problem_id TEXT NOT NULL,
                                     level INTEGER NOT NULL, topic TEXT NOT NULL, answer TEXT NOT NULL,
                                     correct INTEGER NOT NULL, hints INTEGER NOT NULL, solution_shown INTEGER NOT NULL,
                                     seconds REAL NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS hints (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, problem_id TEXT NOT NULL,
                                  rung INTEGER NOT NULL, leaked INTEGER NOT NULL, seconds REAL NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS shown_solved (student_id INTEGER NOT NULL, problem_id TEXT NOT NULL,
                                         PRIMARY KEY (student_id, problem_id));
CREATE TABLE IF NOT EXISTS hint_cache (problem_id TEXT NOT NULL, lang TEXT NOT NULL, result TEXT NOT NULL,
                                       created REAL NOT NULL, PRIMARY KEY (problem_id, lang));
CREATE TABLE IF NOT EXISTS family_history (ts REAL NOT NULL, family INTEGER NOT NULL, label TEXT NOT NULL,
                                           n INTEGER NOT NULL, wrong INTEGER NOT NULL, students INTEGER NOT NULL);
"""


def practice_set(bank, family, failed, attempted, k=3):
    """Problems of the same family that the class hasn't tried, closest in meaning to the ones it
    failed, and not harder than the easiest one it failed: what the teacher can set next."""
    members = [p for p in bank.problems if p["family"] == family and p["id"] not in attempted]
    if not members:
        return []
    if failed:
        top = min(p["level"] for p in failed)
        easier = [p for p in members if p["level"] <= top] or members
        score = lambda p: max(bank.sim(p, f) for f in failed)  # noqa: E731
    else:
        easier, score = members, (lambda p: 0.0)
    return sorted(easier, key=lambda p: (-score(p), p["level"]))[:k]


class Profiles:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        # Older databases lack some columns: add them (and score the answers already given)
        cols = [r[1] for r in self.db.execute("PRAGMA table_info(attempts)")]
        if "points" not in cols:
            self.db.execute("ALTER TABLE attempts ADD COLUMN points INTEGER NOT NULL DEFAULT 0")
            for rid, level, correct, hints, sol in self.db.execute(
                    "SELECT id, level, correct, hints, solution_shown FROM attempts").fetchall():
                self.db.execute("UPDATE attempts SET points = ? WHERE id = ?", (points_for(level, correct, hints, sol), rid))
        if "lang" not in cols:  # the language the problem was shown in, for the error analysis
            self.db.execute("ALTER TABLE attempts ADD COLUMN lang TEXT NOT NULL DEFAULT ''")
            self.db.execute("UPDATE attempts SET lang = (SELECT lang FROM students WHERE students.id = attempts.student_id)")
        if "source" not in cols:  # practice, test, game or learn
            self.db.execute("ALTER TABLE attempts ADD COLUMN source TEXT NOT NULL DEFAULT 'practice'")
        if "class_id" not in [r[1] for r in self.db.execute("PRAGMA table_info(family_history)")]:
            self.db.execute("ALTER TABLE family_history ADD COLUMN class_id INTEGER")
        self.db.commit()

    def _q(self, sql, args=(), one=False):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows

    def student(self, name, lang):
        row = self._q("SELECT id FROM students WHERE name = ?", (name,), one=True)
        if row:
            self._q("UPDATE students SET lang = ? WHERE id = ?", (lang, row[0]))
            return row[0]
        self._q("INSERT INTO students (name, lang, created) VALUES (?, ?, ?)", (name, lang, time.time()))
        return self._q("SELECT id FROM students WHERE name = ?", (name,), one=True)[0]

    def lang(self, sid):
        row = self._q("SELECT lang FROM students WHERE id = ?", (sid,), one=True)
        return row[0] if row else "eng"

    def set_state(self, sid, problem_id, reason=None):
        self._q("INSERT OR REPLACE INTO state VALUES (?, ?, 0, 0, ?, ?)", (sid, problem_id, time.time(), reason))

    def state(self, sid):
        row = self._q("SELECT problem_id, rung, solution_shown, started, reason FROM state WHERE student_id = ?",
                      (sid,), one=True)
        return dict(zip(("problem_id", "rung", "solution_shown", "started", "reason"), row)) if row else None

    def restart_clock(self, sid):
        """The answer time counts from when the problem appears on screen, not from when it was chosen."""
        self._q("UPDATE state SET started = ? WHERE student_id = ?", (time.time(), sid))

    def climb(self, sid, rung):
        self._q("UPDATE state SET rung = MAX(rung, ?) WHERE student_id = ?", (rung, sid))

    def mark_solution(self, sid):
        self._q("UPDATE state SET solution_shown = 1, rung = 4 WHERE student_id = ?", (sid,))

    def seen(self, sid):
        """Problems the student answered, and the ones rung 1 showed already solved: the
        trainer must never serve a problem whose answer the student has seen."""
        answered = {r[0] for r in self._q("SELECT problem_id FROM attempts WHERE student_id = ?", (sid,))}
        shown = {r[0] for r in self._q("SELECT problem_id FROM shown_solved WHERE student_id = ?", (sid,))}
        return answered | shown

    def mark_shown_solved(self, sid, problem_id):
        self._q("INSERT OR IGNORE INTO shown_solved VALUES (?, ?)", (sid, problem_id))

    def record_attempt(self, sid, problem, answer, correct, hints, solution_shown, seconds, lang="", source="practice",
                       points=None):
        """Stores the answer and returns the points it earned (games score apart: they pass 0)."""
        if points is None:
            points = points_for(problem["level"], correct, hints, solution_shown)
        self._q("INSERT INTO attempts (student_id, problem_id, level, topic, answer, correct, hints, solution_shown,"
                " seconds, ts, points, lang, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, problem["id"], problem["level"], problem["topic"], answer, int(correct), hints,
                 int(solution_shown), seconds, time.time(), points, lang, source))
        return points

    def class_stats(self):
        """Everything the teacher view shows: the error analysis by level, topic and language,
        how the hint ladder is used, and how many model hints were blocked."""
        def grouped(column):
            return [{"key": k, "n": n, "correct": c} for k, n, c in self._q(
                f"SELECT {column}, COUNT(*), SUM(correct) FROM attempts GROUP BY {column} ORDER BY {column}")]
        total = self._q("SELECT COUNT(*), COALESCE(SUM(correct), 0), COALESCE(SUM(points), 0),"
                        " COALESCE(SUM(hints), 0), COALESCE(SUM(solution_shown), 0), COUNT(DISTINCT student_id)"
                        " FROM attempts", one=True)
        with_hints = self._q("SELECT hints > 0, COUNT(*), SUM(correct) FROM attempts GROUP BY hints > 0")
        rungs = [{"rung": r, "n": n, "mean_s": round(s or 0, 3), "leaked": int(l or 0)} for r, n, s, l in self._q(
            "SELECT rung, COUNT(*), AVG(seconds), SUM(leaked) FROM hints GROUP BY rung ORDER BY rung")]
        cached = self._q("SELECT COUNT(*), COALESCE(SUM(json_extract(result, '$.hint') IS NULL), 0) FROM hint_cache", one=True)
        return {"answers": total[0], "correct": total[1], "points": total[2], "hints": total[3],
                "solutions": total[4], "students": total[5],
                "by_level": grouped("level"), "by_topic": grouped("topic"), "by_lang": grouped("lang"),
                "with_hints": {("yes" if k else "no"): {"n": n, "correct": c} for k, n, c in with_hints},
                "rungs": rungs, "hints_cached": cached[0], "hints_withheld": cached[1]}

    # ------------------------------------------------------------ the teacher's analysis
    def weak_areas(self, bank, names, lang, min_n=2):
        """The semantic families the class fails most, with the most failed problem and a
        practice set. Error rate smoothed as (wrong + 1) / (answers + 2), so one wrong answer
        alone doesn't top the list; families with fewer than min_n answers go last."""
        fams = {}
        for pid, sid, ok in self._q("SELECT problem_id, student_id, correct FROM attempts"):
            p = bank.by_id.get(pid)
            if not p:
                continue
            f = fams.setdefault(p["family"], {"n": 0, "wrong": 0, "students": set(), "failers": set(),
                                              "failed": Counter(), "attempted": set()})
            f["n"] += 1
            f["attempted"].add(pid)
            f["students"].add(sid)
            if not ok:
                f["wrong"] += 1
                f["failers"].add(sid)
                f["failed"][pid] += 1
        last = self.last_snapshot()
        out = []
        for fam, f in fams.items():
            failed = [bank.by_id[x] for x in f["failed"]]
            example = bank.by_id[f["failed"].most_common(1)[0][0]] if f["failed"] else None
            prev = last.get(fam)
            out.append({
                "family": fam, "topic": names[fam]["topic"], "words": names[fam]["words"],
                "n": f["n"], "wrong": f["wrong"], "students": len(f["students"]), "failers": len(f["failers"]),
                "score": round((f["wrong"] + 1) / (f["n"] + 2), 3), "rate": round(f["wrong"] / f["n"], 3),
                "prev_rate": round(prev[1] / prev[0], 3) if prev and prev[0] else None,
                "example": bank.view(example, lang, with_answer=True) if example else None,
                "example_fails": f["failed"].most_common(1)[0][1] if f["failed"] else 0,
                "practice": [bank.view(p, lang) for p in practice_set(bank, fam, failed, f["attempted"])],
            })
        out.sort(key=lambda a: (a["n"] < min_n, -a["score"], -a["wrong"]))
        return out

    def hardest_problems(self, bank, names, lang, limit=10):
        """The problems the class fails most, and the wrong answer chosen most often: a shared
        wrong answer usually points at the same misconception."""
        per = {}
        for pid, ok, answer in self._q("SELECT problem_id, correct, answer FROM attempts"):
            d = per.setdefault(pid, {"n": 0, "wrong": 0, "answers": Counter()})
            d["n"] += 1
            if not ok:
                d["wrong"] += 1
                d["answers"][answer] += 1
        rows = []
        for pid, d in per.items():
            p = bank.by_id.get(pid)
            if not p or not d["wrong"]:
                continue
            view = bank.view(p, lang, with_answer=True)
            letter, count = d["answers"].most_common(1)[0]
            rows.append({"id": pid, "level": p["level"], "text": view["text"], "label": view["label"], "value": view["value"],
                         "n": d["n"], "wrong": d["wrong"], "common_wrong": letter,
                         "common_wrong_value": view["options"].get(letter, ""), "common_wrong_count": count,
                         "family": names[p["family"]]["words"], "topic": names[p["family"]]["topic"]})
        rows.sort(key=lambda r: (-r["wrong"], -r["wrong"] / r["n"]))
        return rows[:limit]

    def students_table(self, bank, names):
        rows = self._q("""SELECT s.id, s.name, COUNT(a.id), COALESCE(SUM(a.correct), 0), COALESCE(SUM(a.points), 0),
                                 COALESCE(SUM(a.hints), 0), MAX(a.ts), st.problem_id
                          FROM students s LEFT JOIN attempts a ON a.student_id = s.id
                          LEFT JOIN state st ON st.student_id = s.id GROUP BY s.id ORDER BY s.name""")
        per = {}
        for sid, pid, ok in self._q("SELECT student_id, problem_id, correct FROM attempts"):
            p = bank.by_id.get(pid)
            if p:
                c = per.setdefault(sid, {}).setdefault(p["family"], [0, 0])
                c[0] += ok
                c[1] += 1
        out = []
        for sid, name, n, ok, pts, hints, last, current in rows:
            weakest = None
            fam = per.get(sid, {})
            candidates = [(f, c) for f, c in fam.items() if c[1] >= 2 and c[0] < c[1]]
            if candidates:
                f, c = min(candidates, key=lambda fc: ((fc[1][0] + 1) / (fc[1][1] + 2), -fc[1][1]))
                weakest = {"topic": names[f]["topic"], "words": names[f]["words"], "ok": c[0], "n": c[1]}
            level = bank.by_id[current]["level"] if current in bank.by_id else None
            out.append({"sid": sid, "name": name, "answered": n, "correct": ok, "points": pts, "hints": hints,
                        "last": last, "level": level, "weakest": weakest})
        return out

    def timeline(self, minutes=60, bucket=5):
        now = time.time()
        buckets = [[0, 0] for _ in range(minutes // bucket)]
        for ts, ok in self._q("SELECT ts, correct FROM attempts WHERE ts > ?", (now - minutes * 60,)):
            i = min(len(buckets) - 1, int((ts - (now - minutes * 60)) // (bucket * 60)))
            buckets[i][0] += 1
            buckets[i][1] += ok
        return {"bucket_minutes": bucket, "buckets": buckets}

    def save_snapshot(self, areas, class_id=None):
        ts = time.time()
        with self.lock:
            self.db.executemany("INSERT INTO family_history (ts, family, label, n, wrong, students, class_id)"
                                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                                [(ts, a["family"], f"{a['topic']}: {', '.join(a['words'])}", a["n"], a["wrong"],
                                  a["students"], class_id) for a in areas])
            self.db.commit()
        return ts

    def last_snapshot(self, class_id=None):
        row = self._q("SELECT MAX(ts) FROM family_history WHERE class_id IS ?", (class_id,), one=True)
        if not row or row[0] is None:
            return {}
        return {fam: (n, wrong) for fam, n, wrong in
                self._q("SELECT family, n, wrong FROM family_history WHERE ts = ? AND class_id IS ?", (row[0], class_id))}

    def snapshots(self, class_id=None):
        return [{"ts": ts, "families": nfam, "answers": n} for ts, nfam, n in
                self._q("SELECT ts, COUNT(*), SUM(n) FROM family_history WHERE class_id IS ? GROUP BY ts"
                        " ORDER BY ts DESC LIMIT 10", (class_id,))]

    def cached_hint(self, problem_id, lang):
        """A model hint generated before for this problem and language (already leak-checked)."""
        row = self._q("SELECT result FROM hint_cache WHERE problem_id = ? AND lang = ?", (problem_id, lang), one=True)
        if not row:
            return None
        result = json.loads(row[0])
        return result if result.get("v") == HINT_VERSION else None  # made with older checks: make it again

    def cache_hint(self, problem_id, lang, result):
        self._q("INSERT OR REPLACE INTO hint_cache VALUES (?, ?, ?, ?)",
                (problem_id, lang, json.dumps(result, ensure_ascii=False), time.time()))

    def leaderboard(self, limit=20):
        """Students with at least one answer, by points; ties: more right answers, then who got there first."""
        rows = self._q("""
            SELECT s.id, s.name, SUM(a.points) AS pts, COUNT(a.id), SUM(a.correct),
                   MAX(CASE WHEN a.correct = 1 AND a.solution_shown = 0 THEN a.level END), MAX(a.ts) AS last
            FROM students s JOIN attempts a ON a.student_id = s.id
            GROUP BY s.id ORDER BY pts DESC, SUM(a.correct) DESC, last ASC LIMIT ?""", (limit,))
        return [{"rank": i + 1, "sid": r[0], "name": r[1], "points": r[2], "answered": r[3], "correct": r[4],
                 "best_level": r[5], "last": r[6]} for i, r in enumerate(rows)]

    def record_hint(self, sid, problem_id, rung, leaked, seconds):
        self._q("INSERT INTO hints (student_id, problem_id, rung, leaked, seconds, ts) VALUES (?, ?, ?, ?, ?, ?)",
                (sid, problem_id, rung, int(leaked), seconds, time.time()))

    def summary(self, sid):
        rows = self._q("SELECT level, topic, correct, hints, solution_shown, points FROM attempts WHERE student_id = ?"
                       " ORDER BY id", (sid,))
        by_topic, by_level = {}, {}
        for level, topic, correct, _h, _s, _p in rows:
            by_topic.setdefault(topic, [0, 0])
            by_level.setdefault(level, [0, 0])
            by_topic[topic][0] += correct
            by_topic[topic][1] += 1
            by_level[level][0] += correct
            by_level[level][1] += 1
        streak = best_streak = run = 0
        for r in rows:
            run = run + 1 if r[2] else 0
            best_streak = max(best_streak, run)
        for r in reversed(rows):
            if not r[2]:
                break
            streak += 1
        return {"answered": len(rows), "correct": sum(r[2] for r in rows), "points": sum(r[5] for r in rows),
                "streak": streak, "best_streak": best_streak,
                "hints": sum(r[3] for r in rows), "solutions": sum(r[4] for r in rows),
                "path": [[r[0], r[2]] for r in rows][-40:],
                "by_topic": by_topic, "by_level": by_level}


def make_rng(seed=None):
    return random.Random(seed)
