#!/usr/bin/env python3
"""Build the problem map for the math-coach app: every usable M3Kang problem with its
languages, level, topic, solution and embedding.

    python3 app/math-coach/build_bank.py            (from the repository folder)

Reads data/train.jsonl, data/val.jsonl and data/explanations/*.jsonl, embeds the English
version of each problem with the embedding server in config.env, and writes
app/math-coach/python/data/bank.json. Standard library only. M3Kang is research-only: the
output folder is in .gitignore.

The app uses bge-m3 (multilingual, 1024 dimensions). It only needs the vectors, so bge-m3
runs once on the laptop and never on the board:
    EMBED_PORT=8084 EMBED_QUERY_PREFIX="" EMBED_MAX_CHARS=6000 EMBED_NAME=bge-m3 python3 app/math-coach/build_bank.py
With the defaults of config.env it uses bge-small (384 dimensions) on port 8082.

Which problems: those with five text options and no figure needed (text_only), because the
page shows text only. Use --with-figures to include the others once their images exist.
"""
import argparse
import base64
import glob
import json
import os
import re
import sys
import time
from array import array
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app", "math-coach", "python"))

from copilot.embed import embed  # noqa: E402
from copilot.llm import format_problem  # noqa: E402
from coach import TOPICS, classify_topic  # noqa: E402

OUT = os.path.join(ROOT, "app", "math-coach", "python", "data", "bank.json")


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def clean(text):
    """Drop the competition's question number ('14. ') and squeeze spaces."""
    text = re.sub(r"^\s*\d{1,2}\s*\.\s*", "", text.strip())
    return re.sub(r"[ \t]+", " ", text).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--with-figures", action="store_true", help="also keep problems that need a figure")
    p.add_argument("--out", default=OUT)
    args = p.parse_args()

    rows = []
    for split in ("train", "val"):
        for r in load_jsonl(os.path.join(ROOT, "data", f"{split}.jsonl")):
            r["split"] = split
            rows.append(r)
    explanations = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "explanations", "*.jsonl"))):
        for r in load_jsonl(path):
            explanations[r["id"]] = r["explanation"].strip()

    by_id = {}
    for r in rows:
        by_id.setdefault(r["id"], {})[r["language"]] = r
    problems = []
    for pid, langs in by_id.items():
        eng = langs.get("eng")
        if not eng or len(eng.get("options") or {}) != 5:
            continue
        if not args.with_figures and not eng.get("text_only"):
            continue
        entry = {"id": pid, "level": eng["level"], "year": eng["year"], "split": eng["split"],
                 "label": eng["label"], "text_only": bool(eng.get("text_only")),
                 "explanation": explanations.get(pid), "langs": {}}
        for code, r in langs.items():
            if len(r.get("options") or {}) == 5:
                entry["langs"][code] = {"text": clean(r["text"]),
                                        "options": {k: str(v).strip() for k, v in sorted(r["options"].items())}}
        entry["value"] = entry["langs"]["eng"]["options"][eng["label"]]
        entry["_eng"] = eng
        problems.append(entry)
    problems.sort(key=lambda e: (e["level"], e["id"]))
    print(f"{len(problems)} problems kept out of {len(by_id)}")

    start = time.perf_counter()
    vectors = []
    for i in range(0, len(problems), 16):
        chunk = problems[i:i + 16]
        vectors += embed([format_problem(e["_eng"]) for e in chunk])
        print(f"\r  embedded {min(i + 16, len(problems))}/{len(problems)}", end="", flush=True)
    print(f"  ({time.perf_counter() - start:.0f} s)")
    for e, v in zip(problems, vectors):
        e["vec"] = base64.b64encode(array("f", v).tobytes()).decode()
        e["_vec"] = v

    # Topic: keyword rules on the English text. Problems with no keyword are mostly word
    # problems solved with an equation, so they go to "arithmetic" (copying the neighbours'
    # topic was tried first: it spread these problems over unrelated topics).
    for e in problems:
        e["topic"] = classify_topic(e["langs"]["eng"]["text"] + " " + " ".join(e["langs"]["eng"]["options"].values()))
        if not e["topic"]:
            e["topic"], e["topic_from"] = "arithmetic", "default"
    for e in problems:
        e.pop("_eng")
        e.pop("_vec")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    bank = {"meta": {"built": time.strftime("%Y-%m-%d %H:%M"),
                     "embedding": os.environ.get("EMBED_NAME", "bge-small-en-v1.5") + " (English text)",
                     "dimensions": len(vectors[0]), "count": len(problems), "with_figures": args.with_figures},
            "problems": problems}
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(bank, f, ensure_ascii=False)
    print(f"Wrote {args.out} ({os.path.getsize(args.out) / 1e6:.1f} MB), embedding {bank['meta']['embedding']}, "
          f"{bank['meta']['dimensions']} dimensions")
    print("Problems per level:", dict(sorted(Counter(e["level"] for e in problems).items())))
    topics = Counter(e["topic"] for e in problems)
    print("Topics:", ", ".join(f"{TOPICS[t]['eng'][0]} {n}" for t, n in topics.most_common()))
    print("No keyword (default topic arithmetic):", sum(1 for e in problems if e.get("topic_from")))
    print("With a written solution:", sum(1 for e in problems if e["explanation"]))
    print("Languages:", dict(Counter(code for e in problems for code in e["langs"])))


if __name__ == "__main__":
    main()
