#!/usr/bin/env python3
"""Simulated students on the adaptive trainer (no model involved).

    python3 app/math-coach/tools/simulate_students.py [--steps 40] [--runs 20]

Each student answers with a fixed rule, e.g. always right below level 2 and always wrong
from level 2 up. For every start level and several random first problems, the trainer
picks the next problem exactly as the app does (coach.next_problem). We report:

  settles at   the most common level over the last 20 steps, and the two levels it moves between
  expected     the boundary the rule implies (e.g. 1<->2 for 'right below 2')
  on-topic     after a wrong answer, how often the next problem keeps the same topic
  fallbacks    how often the trainer had to relax a rule (no unseen problem fitting it)
  ms/step      time to choose the next problem, on this machine
"""
import argparse
import os
import random
import statistics
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import coach  # noqa: E402

STUDENTS = {
    "right below 2": (lambda p, rng: p["level"] < 2, (1, 2)),
    "right below 4": (lambda p, rng: p["level"] < 4, (3, 4)),
    "right below 6": (lambda p, rng: p["level"] < 6, (5, 6)),
    "good at numbers only (L<5)": (lambda p, rng: p["topic"] in ("numbers", "arithmetic") and p["level"] < 5, None),
    "noisy, 50% at L3": (lambda p, rng: rng.random() < 1 / (1 + 2 ** (p["level"] - 3)), (2, 4)),
}


def run(bank, rule, start_level, steps, seed):
    rng = random.Random(seed)
    p = coach.first_problem(bank, start_level, set(), rng)
    seen, path, wrong_moves, reasons, times = {p["id"]}, [], [], Counter(), []
    for _ in range(steps):
        correct = rule(p, rng)
        t0 = time.perf_counter()
        nxt, reason = coach.next_problem(bank, p, correct, seen)
        times.append((time.perf_counter() - t0) * 1000)
        path.append((p["level"], p["topic"], correct))
        reasons[reason] += 1
        if not correct:
            wrong_moves.append(nxt["topic"] == p["topic"])
        seen.add(nxt["id"])
        p = nxt
    return path, wrong_moves, reasons, times


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", default=os.path.join(HERE, "..", "python", "data", "bank.json"))
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--runs", type=int, default=20, help="random first problems per start level")
    args = ap.parse_args()
    bank = coach.Bank(args.bank)
    print(f"{len(bank.problems)} problems, {args.steps} steps, {args.runs} runs x 8 start levels per student\n")
    print(f"{'student':<28} {'settles at':>10} {'between':>9} {'expected':>9} {'on-topic':>9} {'fallbacks':>10} {'ms/step':>8}")
    for name, (rule, expected) in STUDENTS.items():
        settle, pairs, on_topic, fallbacks, times, total_moves = Counter(), Counter(), [], 0, [], 0
        for start in range(coach.MAX_LEVEL + 1):
            for r in range(args.runs):
                path, wrong_moves, reasons, t = run(bank, rule, start, args.steps, seed=1000 * start + r)
                tail = [lvl for lvl, _t, _c in path[-20:]]
                settle[Counter(tail).most_common(1)[0][0]] += 1
                top2 = sorted(lvl for lvl, _n in Counter(tail).most_common(2))
                pairs[f"{top2[0]}<->{top2[-1]}"] += 1
                on_topic += wrong_moves
                fallbacks += sum(n for k, n in reasons.items() if k not in ("up", "down-same-topic", "start"))
                total_moves += sum(reasons.values())
                times += t
        mode = settle.most_common(1)[0][0]
        pair = pairs.most_common(1)[0][0]
        exp = f"{expected[0]}<->{expected[1]}" if expected else "-"
        topic_rate = f"{100 * sum(on_topic) / len(on_topic):.0f}%" if on_topic else "-"
        print(f"{name:<28} {mode:>10} {pair:>9} {exp:>9} {topic_rate:>9} {100 * fallbacks / total_moves:>9.0f}% "
              f"{statistics.mean(times):>8.1f}")
    print("\nsettles at: most common level over the last 20 steps (over all runs). between: the two levels it"
          " alternates on. on-topic: share of wrong answers followed by a problem on the same topic.")


if __name__ == "__main__":
    main()
