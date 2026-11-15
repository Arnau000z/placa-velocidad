#!/usr/bin/env python3
"""Rungs 1 and 2 of the hint ladder on every problem of the map: time, and whether rung 1
gives the answer away (its solved problem has the same answer value as the problem asked).

    python3 app/math-coach/tools/measure_ladder.py [--split val]

Run it on the board too: the times there are the ones that count.
"""
import argparse
import os
import statistics
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import coach  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", default=os.path.join(HERE, "..", "python", "data", "bank.json"))
    ap.add_argument("--split", default="", help="val or train (default: every problem)")
    args = ap.parse_args()
    t0 = time.perf_counter()
    bank = coach.Bank(args.bank)
    load = time.perf_counter() - t0
    problems = [p for p in bank.problems if not args.split or p["split"] == args.split]
    t1, t2, same_value, same_topic, level_gap, with_solution = [], [], 0, 0, Counter(), 0
    for p in problems:
        s = time.perf_counter()
        q, _score = coach.rung1_easier_problem(bank, p)
        t1.append(time.perf_counter() - s)
        s = time.perf_counter()
        coach.rung2_topic(bank, p)
        t2.append(time.perf_counter() - s)
        same_value += q["value"].strip().lower() == p["value"].strip().lower()
        same_topic += q["topic"] == p["topic"]
        level_gap[p["level"] - q["level"]] += 1
        with_solution += bool(q.get("explanation"))
    n = len(problems)
    print(f"Map loaded in {load:.2f} s. Problems checked: {n} ({args.split or 'all'})")
    print(f"Rung 1 shows a problem with the SAME answer value: {same_value} ({100 * same_value / n:.1f}%)"
          "  <- answer given away (values like '2' can match by chance)")
    print(f"Rung 1 same topic (keyword rules): {same_topic} ({100 * same_topic / n:.0f}%)")
    print(f"Rung 1 level gap (asked - shown): {dict(sorted(level_gap.items()))}  (0 only at level 0)")
    print(f"Rung 1 with a written solution: {with_solution} ({100 * with_solution / n:.0f}%)")
    print(f"Rung 1 time: mean {1000 * statistics.mean(t1):.0f} ms, max {1000 * max(t1):.0f} ms")
    print(f"Rung 2 time: mean {1000 * statistics.mean(t2):.0f} ms, max {1000 * max(t2):.0f} ms")


if __name__ == "__main__":
    main()
