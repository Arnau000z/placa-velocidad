#!/usr/bin/env python3
"""End-to-end check of the running app, and the time of each step, measured where it runs.

    python3 app/math-coach/tools/time_rungs.py --url http://127.0.0.1:7000 --teacher-pin 1234 --problems 5 [--read-seconds 25]

With the teacher PIN it creates a class 'test-timing' with one student, who logs in with its PIN.
For each problem it asks rung 1, 2 and 3 (waiting for the model), then answers (always 'A') and
moves to the next problem. --read-seconds pauses after rung 2 like a student reading: the app
prefetches rung 3 from rung 1 on, so with a pause it should arrive (almost) at once. The test
class is deleted at the end (--keep to leave it).
"""
import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request


def call(base, path, **params):
    url = f"{base}/api/{path}?{urllib.parse.urlencode(params)}"
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=300) as r:
        data = json.loads(r.read())
    return data, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:7000")
    ap.add_argument("--teacher-pin", required=True)
    ap.add_argument("--problems", type=int, default=5)
    ap.add_argument("--lang", default="cat")
    ap.add_argument("--level", type=int, default=3)
    ap.add_argument("--read-seconds", type=float, default=0,
                    help="pause after rung 2, as a student reading the hints (rung 3 is prefetched meanwhile)")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    info, t = call(args.url, "info")
    print(f"info: {info['problems']} problems, map {info.get('embedding')}, model reachable: {info['llm']} ({t * 1000:.0f} ms)")
    r, _ = call(args.url, "teacher_login", pin=args.teacher_pin)
    if r.get("error"):
        raise SystemExit("wrong teacher PIN")
    tt = r["token"]
    cid = call(args.url, "t_class", tt=tt, action="create", name="test-timing")[0]["id"]
    s, _ = call(args.url, "t_student_edit", tt=tt, action="add", class_id=cid, name="timing-test")
    sid = s["sid"]
    tok = call(args.url, "login", sid=sid, pin=s["pin"])[0]["token"]
    call(args.url, "settings", token=tok, lang=args.lang)
    r, t = call(args.url, "practice", token=tok, level=args.level, restart=1)
    problem = r["problem"]
    print(f"start: sid {sid}, first problem {problem['id']} L{problem['level']} ({t * 1000:.0f} ms)")
    times = {"rung1": [], "rung2": [], "rung3": [], "answer": []}
    try:
        for i in range(args.problems):
            print(f"\n[{i + 1}] {problem['id']} L{problem['level']} (worth {problem.get('worth')}): {problem['text'][:80]}")
            r, t = call(args.url, "hint", token=tok)
            times["rung1"].append(t)
            shown_solved = r["problem"]["id"]
            print(f"  rung 1 ({t * 1000:.0f} ms): easier L{r['problem']['level']} {r['problem']['id']} sim {r['similarity']}")
            r, t = call(args.url, "hint", token=tok)
            times["rung2"].append(t)
            print(f"  rung 2 ({t * 1000:.0f} ms): {r['topic']}")
            if args.read_seconds:
                time.sleep(args.read_seconds)
            t0 = time.perf_counter()
            call(args.url, "hint", token=tok)
            while True:
                st, _ = call(args.url, "hint_status", token=tok)
                if not st["pending"]:
                    break
                time.sleep(0.3)
            t3 = time.perf_counter() - t0
            times["rung3"].append(t3)
            res = st["result"] or {}
            shown = res.get("hint") or f"(withheld) {res.get('error', '')}"
            print(f"  rung 3 ({t3:.1f} s{', from cache/prefetch' if t3 < 2 else ''}): {shown[:110]}")
            r, t = call(args.url, "answer", token=tok, letter="A")
            times["answer"].append(t)
            print(f"  answer A: {'right' if r['correct'] else 'wrong'} (was {r['label']}) +{r['points']} points -> next "
                  f"L{r['next']['level']} [{r['next_reason']}] ({t * 1000:.0f} ms)")
            if r["next"]["id"] == shown_solved:
                print("  WARNING: the next problem is the one rung 1 showed solved")
            problem = r["next"]
            call(args.url, "shown", token=tok)
    finally:
        if not args.keep:
            call(args.url, "t_student_edit", tt=tt, action="delete", sid=sid)
            call(args.url, "t_class", tt=tt, action="delete", class_id=cid)
    print("\n== time per call, as seen by the client")
    for k, v in times.items():
        if v:
            unit, f = ("s", 1) if k == "rung3" else ("ms", 1000)
            print(f"  {k:<7} mean {statistics.mean(v) * f:7.1f} {unit}   max {max(v) * f:7.1f} {unit}")


if __name__ == "__main__":
    main()
