#!/usr/bin/env python3
"""How often does the model's hint (rung 3) give the answer away? Checked by code on the
validation set, with the same prompt and leak check as the app (coach.rung3_model_hint).

    python3 app/math-coach/tools/measure_hints.py --url http://127.0.0.1:8081 [--languages eng,cat,esp] [--limit 0]

Every val problem with five text options, in every language asked for. For each one:
attempt 1 (temperature 0); if it leaks, attempt 2 (temperature 0.8); if that leaks too,
the app shows no model hint (only the method). Reports leak rates, why they leaked, how
often the answer's value is also written in the problem itself (a hint can then repeat
it innocently: the check is conservative on purpose), and the time per hint.
Writes one row per problem to results/coach-hints-<time>.csv.
"""
import argparse
import csv
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import coach  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8081")
    ap.add_argument("--input", default=os.path.join(ROOT, "data", "val.jsonl"))
    ap.add_argument("--languages", default="eng,cat,esp")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    langs = args.languages.split(",")
    rows = [json.loads(line) for line in open(args.input, encoding="utf-8")]
    rows = [r for r in rows if len(r.get("options") or {}) == 5 and r["language"] in langs]
    if args.limit:
        rows = rows[:args.limit]
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    out_path = os.path.join(ROOT, "results", f"coach-hints-{time.strftime('%Y%m%d-%H%M%S')}.csv")
    stats = {"n": 0, "leak1": 0, "useless1": 0, "withheld": 0, "value_in_text": 0, "reasons": {}, "useless": {},
             "seconds": []}
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "language", "level", "attempt1_leak", "attempt2_leak", "shown", "seconds1", "prompt_tokens"])
        for i, r in enumerate(rows, 1):
            problem = {"label": r["label"], "langs": {r["language"]: {"text": r["text"], "options": r["options"]}}}
            if r["language"] != "eng":  # the leak check also looks at the English value when it exists
                problem["langs"]["eng"] = {"text": r["text"], "options": r["options"]}
            try:
                res = coach.rung3_model_hint(problem, r["language"], url=args.url)
            except OSError as error:
                print(f"[{i}] {r['id']} {r['language']}: model error {error}")
                continue
            a = res["attempts"]
            stats["n"] += 1
            stats["seconds"].append(a[0]["seconds"])
            if a[0]["leak"]:
                stats["leak1"] += 1
                kind = a[0]["leak"].split(" ")[0] + " " + a[0]["leak"].split(" ")[1]
                stats["reasons"][kind] = stats["reasons"].get(kind, 0) + 1
                value = r["options"][r["label"]]
                if value and value.lower() in r["text"].lower():
                    stats["value_in_text"] += 1
            elif a[0].get("useless"):
                stats["useless1"] += 1
                stats["useless"][a[0]["useless"]] = stats["useless"].get(a[0]["useless"], 0) + 1
            if res["hint"] is None:
                stats["withheld"] += 1
            w.writerow([r["id"], r["language"], r["level"], a[0]["leak"] or a[0].get("useless") or "",
                        (a[1]["leak"] or a[1].get("useless") or "") if len(a) > 1 else "",
                        int(res["hint"] is not None), a[0]["seconds"], a[0]["prompt_tokens"]])
            f.flush()
            first = ("LEAK " + a[0]["leak"]) if a[0]["leak"] else ("USELESS " + a[0]["useless"]) if a[0].get("useless") else "ok"
            print(f"[{i}/{len(rows)}] {r['id']} {r['language']}: {first}"
                  f"{' -> withheld' if res['hint'] is None else ''} ({a[0]['seconds']} s) {res['hint'] or ''}"[:200], flush=True)
    n = stats["n"]
    print("\n" + "=" * 60)
    print(f"Hints: {n} problems ({args.languages})")
    print(f"Leaked on attempt 1: {stats['leak1']} ({100 * stats['leak1'] / n:.1f}%)  why: {stats['reasons']}")
    print(f"  of which the answer's value is also in the problem text: {stats['value_in_text']}")
    print(f"Useless on attempt 1 (too short / repeats the problem): {stats['useless1']} ({100 * stats['useless1'] / n:.1f}%)"
          f"  {stats['useless']}")
    print(f"Withheld after 2 attempts (student sees only the method): {stats['withheld']} ({100 * stats['withheld'] / n:.1f}%)")
    print(f"Leaks shown to the student: 0 (every shown hint passed the check)")
    print(f"Time per hint (attempt 1): mean {statistics.mean(stats['seconds']):.2f} s, max {max(stats['seconds']):.2f} s")
    print(f"Details: {out_path}")


if __name__ == "__main__":
    main()
