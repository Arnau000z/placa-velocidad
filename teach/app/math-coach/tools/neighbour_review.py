#!/usr/bin/env python3
"""20 problems and the 'similar, easier problem' that rung 1 shows for each, to judge by hand.

    python3 app/math-coach/tools/neighbour_review.py [--n 20] [--seed 7]

Writes data/coach-neighbour-review.csv (data/ is git-ignored: it holds M3Kang text) with two
empty columns to fill in: easier (y/n) and same_topic (y/n). Then run it again with --score
to count the answers.
"""
import argparse
import csv
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import coach  # noqa: E402

OUT = os.path.join(ROOT, "data", "coach-neighbour-review.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", default=os.path.join(HERE, "..", "python", "data", "bank.json"))
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--score", action="store_true", help="count the y/n answers in the filled-in file")
    args = ap.parse_args()
    if args.score:
        rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
        for col in ("easier", "same_topic"):
            yes = sum(r[col].strip().lower().startswith("y") for r in rows)
            done = sum(bool(r[col].strip()) for r in rows)
            print(f"{col}: {yes}/{done} yes")
        return
    bank = coach.Bank(args.bank)
    pool = [p for p in bank.problems if p["level"] >= 1]
    picks = random.Random(args.seed).sample(pool, args.n)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "level", "topic", "problem", "neighbour_id", "neighbour_level", "neighbour_topic",
                    "similarity", "neighbour_problem", "easier", "same_topic"])
        for p in picks:
            q, score = coach.rung1_easier_problem(bank, p)
            w.writerow([p["id"], p["level"], p["topic"], p["langs"]["eng"]["text"], q["id"], q["level"], q["topic"],
                        round(score, 3), q["langs"]["eng"]["text"], "", ""])
            print(f"L{p['level']} {p['topic']:<11} -> L{q['level']} {q['topic']:<11} sim {score:.2f}  {p['id']} -> {q['id']}")
    same = sum(1 for p in picks if coach.rung1_easier_problem(bank, p)[0]["topic"] == p["topic"])
    print(f"\nSame topic by the keyword rules: {same}/{args.n} (judge it yourself: the rules are rough)")
    print(f"Fill in the last two columns of {OUT}, then run with --score")


if __name__ == "__main__":
    main()
