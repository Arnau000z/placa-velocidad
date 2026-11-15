#!/usr/bin/env python3
"""Translates the written solutions (English) into Catalan and Spanish, and accepts a translation
only if it passes automatic checks. Runs on the laptop, once; the board only reads the result.

    python3 app/math-coach/tools/translate_explanations.py [--limit N]

Needs two llama-servers on the laptop:
  - SalamandraTA-7B-instruct v3 (BSC, a translation model; llama-windows/start-salamandra.ps1), port 8085,
    with the prompt from its model card: "Translate the following text from English into Catalan.\\nEnglish: ... \\nCatalan:"
  - bge-m3 (multilingual embeddings; start-embed-m3.ps1), port 8084, to check the meaning.

Checks on every translation (all must pass):
  numbers   the same numbers as the English (2,5 and 2.5 count as the same)
  symbols   the same =, →, √, %, /, <, >, × (a "x" between numbers is repaired back to ×)
  language  more function words of the target language than of the other two
  length    between 0.6 and 1.9 times the English length
  meaning   bge-m3 cosine between the English and the translation above the 99th percentile of the cosines
            between English solutions and unrelated translations (5 per solution), and at least --min-cosine (0.70)
If a translation fails, it is retried sentence by sentence; if it still fails, that problem keeps
its English solution (the page says so). Output, in python/data/ (git-ignored, M3Kang is research-only):
  explanations_i18n.json   accepted translations + metadata (model, checks, pass rates); coach.Bank merges it
  translation_report.json  every attempt with its scores and failed checks
  translation_review.csv   30 random items for a person to judge (fill in ok_cat / ok_esp with 1 or 0)
"""
import argparse
import csv
import json
import math
import os
import random
import re
import sys
import time
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "python", "data")
NAMES = {"cat": "Catalan", "esp": "Spanish"}
FUNCTION_WORDS = {  # words that tell the three languages apart (none shared; single letters are ignored)
    "eng": set("the and is of to in that it with for are so each there this from then has have was were which".split()),
    "cat": set("és amb per dels els les són hi així aquest aquesta això allà doncs també seu seva seus fa fan cal només hem més "
               "perquè quan tots totes mateix mateixa aleshores llavors queden".split()),
    "esp": set("con por los las son hay así este esta eso allí entonces también su sus hace hacen solo hemos más porque "  # not "es": Catalan uses it too
               "cuando todos todas mismo misma quedan".split()),
}
SYMBOLS = ["=", "→", "√", "%", "/", "<", ">", "×"]


def post(url, payload, timeout=180):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def translate(text, lang, args):
    name = NAMES[lang]
    prompt = f"Translate the following text from English into {name}.\nEnglish: {text} \n{name}:"
    out = post(f"{args.mt}/v1/chat/completions", {"messages": [{"role": "user", "content": prompt}],
                                                  "temperature": 0.1, "max_tokens": 600})
    return out["choices"][0]["message"]["content"].strip()


def embed(texts, args):
    out = post(f"{args.embed}/v1/embeddings", {"input": texts})
    vecs = [d["embedding"] for d in sorted(out["data"], key=lambda d: d["index"])]
    return [[x / (math.sqrt(sum(y * y for y in v)) or 1) for x in v] for v in vecs]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


ORDINALS = {  # ordinal words, so that "8th" -> "vuitè" / "octavo" keeps its number
    "cat": {"primer": 1, "primera": 1, "segon": 2, "segona": 2, "tercer": 3, "tercera": 3, "quart": 4, "quarta": 4, "cinquè": 5,
            "cinquena": 5, "sisè": 6, "sisena": 6, "setè": 7, "setena": 7, "vuitè": 8, "vuitena": 8, "novè": 9, "novena": 9,
            "desè": 10, "desena": 10, "onzè": 11, "onzena": 11, "dotzè": 12, "dotzena": 12},
    "esp": {"primero": 1, "primera": 1, "primer": 1, "segundo": 2, "segunda": 2, "tercero": 3, "tercera": 3, "tercer": 3,
            "cuarto": 4, "cuarta": 4, "quinto": 5, "quinta": 5, "sexto": 6, "sexta": 6, "séptimo": 7, "séptima": 7, "octavo": 8,
            "octava": 8, "noveno": 9, "novena": 9, "décimo": 10, "décima": 10, "undécimo": 11, "duodécimo": 12},
}


def numbers(text, lang=None, ordinals=()):
    """The numbers in a text. In a translation, an ordinal word counts as its number when the English
    had that number as an ordinal (8th)."""
    found = Counter(n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)*", text))
    if lang and ordinals:
        for w in re.findall(r"[a-zàèéíòóú]+", text.lower()):
            v = ORDINALS[lang].get(w)
            if v is not None and str(v) in ordinals:
                found[str(v)] += 1
    return found


def repair(src, out):
    """SalamandraTA sometimes writes × as x: put it back where the English had ×."""
    if src.count("×") > out.count("×"):
        out = re.sub(r"(?<=[\d)])\s*[xX]\s*(?=[\d(])", " × ", out)
    if src.count("×") > out.count("×") and not re.search(r"\b[xX]\b", src):  # the English has no variable x
        out = re.sub(r"(?<=\s)[xX](?=\s)", "×", out)
    return out


def symbol_counts(text):
    t = re.sub(r"(?<=\d)\s*·\s*(?=\d)", " × ", text)
    return {s: t.count(s) for s in SYMBOLS}


def language_scores(text):
    words = [w for w in re.findall(r"[a-zàèéíïòóúüçñ·]+", text.lower()) if len(w) >= 2]
    return {k: sum(w in v for w in words) for k, v in FUNCTION_WORDS.items()}, len(words)


def checks(src, out, lang):
    failed = []
    ordinals = set(re.findall(r"(\d+)(?:st|nd|rd|th)\b", src))
    if numbers(src) != numbers(out, lang, ordinals):
        failed.append("numbers")
    if symbol_counts(src) != symbol_counts(out):
        failed.append("symbols")
    scores, nwords = language_scores(out)
    if nwords >= 4 and sum(scores.values()) >= 2 and scores[lang] < max(v for k, v in scores.items() if k != lang):
        failed.append("language")
    ratio = len(out) / max(1, len(src))
    if not 0.6 <= ratio <= 1.9:
        failed.append("length")
    return failed, round(ratio, 2), scores


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", text) if s.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mt", default="http://127.0.0.1:8085")
    ap.add_argument("--embed", default="http://127.0.0.1:8084")
    ap.add_argument("--min-cosine", type=float, default=0.70, help="floor of the meaning threshold")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    with open(os.path.join(DATA, "bank.json"), encoding="utf-8") as f:
        problems = [p for p in json.load(f)["problems"] if p.get("explanation")]
    if args.limit:
        problems = problems[:args.limit]
    print(f"{len(problems)} written solutions to translate into {', '.join(NAMES.values())}", flush=True)
    t_start = time.time()
    report, accepted = [], {}
    for i, p in enumerate(problems, 1):
        src = " ".join(p["explanation"].split())
        for lang in NAMES:
            t0 = time.time()
            out = repair(src, translate(src, lang, args))
            mode = "whole"
            failed, ratio, scores = checks(src, out, lang)
            if failed:  # second try: sentence by sentence
                out2 = repair(src, " ".join(repair(s, translate(s, lang, args)) for s in sentences(src)))
                failed2, ratio2, scores2 = checks(src, out2, lang)
                if len(failed2) < len(failed):
                    out, failed, ratio, scores, mode = out2, failed2, ratio2, scores2, "sentences"
            e_src, e_out = embed([src, out], args)
            c = cos(e_src, e_out)
            row = {"id": p["id"], "lang": lang, "mode": mode, "src": src, "out": out, "cosine": round(c, 4), "length_ratio": ratio,
                   "function_words": scores, "failed": failed, "seconds": round(time.time() - t0, 2), "_vec": e_out, "_src_vec": e_src}
            report.append(row)
        if i % 10 == 0 or i == len(problems):
            ok = sum(1 for r in report if not r["failed"])
            print(f"  {i}/{len(problems)}  passed the form checks {ok}/{len(report)}  ({time.time() - t_start:.0f} s)", flush=True)
    # The meaning check needs a baseline: each English solution against 5 unrelated translations.
    # A translation must be closer to its English than 99% of unrelated pairs (and at least --min-cosine).
    rng = random.Random(args.seed)
    by_lang = {lang: [r for r in report if r["lang"] == lang] for lang in NAMES}
    unrelated = []
    for lang, rows in by_lang.items():
        for r in rows:
            for other in rng.sample([x for x in rows if x["id"] != r["id"]], min(5, len(rows) - 1)):
                unrelated.append(cos(r["_src_vec"], other["_vec"]))
    unrelated.sort()
    threshold = max(args.min_cosine, round(unrelated[int(0.99 * (len(unrelated) - 1))], 4))
    for r in report:
        r.pop("_vec"), r.pop("_src_vec")
        if r["cosine"] < threshold:
            r["failed"].append("meaning")
        if not r["failed"]:
            accepted.setdefault(r["id"], {})[r["lang"]] = r["out"]
    fails = Counter(f for r in report for f in r["failed"])
    cosines = sorted(r["cosine"] for r in report)
    stats = {
        "solutions": len(problems), "translations": len(report), "accepted": sum(1 for r in report if not r["failed"]),
        "accepted_by_lang": {lang: sum(1 for r in report if r["lang"] == lang and not r["failed"]) for lang in NAMES},
        "failed_checks": dict(fails), "retried_by_sentence": sum(1 for r in report if r["mode"] == "sentences"),
        "cosine_median": cosines[len(cosines) // 2], "cosine_p5": cosines[len(cosines) // 20],
        "cosine_unrelated_median": round(unrelated[len(unrelated) // 2], 4), "cosine_unrelated_p99": round(unrelated[int(0.99 * (len(unrelated) - 1))], 4),
        "cosine_unrelated_max": round(unrelated[-1], 4), "meaning_threshold": threshold, "seconds": round(time.time() - t_start),
    }
    meta = {"model": "SalamandraTA-7B-instruct v3 (BSC-LT), Q4_K_M GGUF, llama.cpp CUDA, temperature 0.1",
            "verifier": "bge-m3 cross-lingual cosine + numbers, symbols, language and length checks",
            "min_cosine_floor": args.min_cosine, "date": time.strftime("%Y-%m-%d"), "stats": stats}
    with open(os.path.join(DATA, "explanations_i18n.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "translations": accepted}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "translation_report.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "items": report}, f, ensure_ascii=False, indent=1)
    sample = rng.sample(sorted({r["id"] for r in report}), min(30, len(problems)))
    rows = {(r["id"], r["lang"]): r for r in report}
    with open(os.path.join(DATA, "translation_review.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "english", "catalan", "ok_cat", "spanish", "ok_esp"])
        for pid in sample:
            w.writerow([pid, rows[(pid, "cat")]["src"], rows[(pid, "cat")]["out"], "", rows[(pid, "esp")]["out"], ""])
    print("\n" + json.dumps(stats, indent=1))
    print("Wrote explanations_i18n.json, translation_report.json, translation_review.csv in", os.path.normpath(DATA))


if __name__ == "__main__":
    sys.exit(main())
