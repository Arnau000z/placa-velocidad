#!/usr/bin/env python3
"""Several students at once against the running app: does it hold, and how long does each step take?

    python3 app/math-coach/tools/multi_user_test.py --url http://127.0.0.1:7000 --teacher-pin 1234 --students 4 --problems 4

With the teacher PIN it creates a class 'test-auto' with students 'test-N' (each gets a PIN and
logs in like a student). Each student (a thread) starts at a different level, asks for rungs 1
and 2, asks for rung 3 on its first problem (all at the same time, so they queue for the model),
and answers. Then it checks a wrong PIN is refused, prints the class ranking, and deletes the
test class and its students (--keep to leave them).
"""
import argparse
import json
import random
import statistics
import threading
import time
import urllib.parse
import urllib.request

lock = threading.Lock()
times = {"login": [], "practice": [], "rung1": [], "rung2": [], "rung3": [], "answer": [], "leaderboard": []}
errors = []


def call(base, path, **params):
    url = f"{base}/api/{path}?{urllib.parse.urlencode(params)}"
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=300) as r:
        data = json.loads(r.read())
    return data, time.perf_counter() - t0


def record(kind, seconds):
    with lock:
        times[kind].append(seconds)


def make_class(base, pin, n):
    """A test class with n students: [(sid, pin)]. Returns (teacher token, class id, students)."""
    r, _ = call(base, "teacher_login", pin=pin)
    if r.get("error"):
        raise SystemExit("wrong teacher PIN")
    tt = r["token"]
    r, _ = call(base, "t_class", tt=tt, action="create", name="test-auto")
    cid = r["id"]
    students = []
    for k in range(1, n + 1):
        s, _ = call(base, "t_student_edit", tt=tt, action="add", class_id=cid, name=f"test-{k}")
        students.append((s["sid"], s["pin"]))
    return tt, cid, students


def remove_class(base, tt, cid, students):
    for sid, _pin in students:
        call(base, "t_student_edit", tt=tt, action="delete", sid=sid)
    call(base, "t_class", tt=tt, action="delete", class_id=cid)


def student(base, n, sid, pin, problems, barrier):
    rng = random.Random(n)
    try:
        r, t = call(base, "login", sid=sid, pin=pin)
        record("login", t)
        tok = r["token"]
        call(base, "settings", token=tok, lang=("cat", "esp", "eng")[n % 3])
        r, t = call(base, "practice", token=tok, level=n % 8, restart=1)
        record("practice", t)
        for i in range(problems):
            for kind in ("rung1", "rung2"):
                _r, t = call(base, "hint", token=tok)
                record(kind, t)
            if i == 0:
                barrier.wait()  # everyone asks the model at the same moment
                t0 = time.perf_counter()
                call(base, "hint", token=tok)
                max_ahead = 0
                while True:
                    s, _ = call(base, "hint_status", token=tok)
                    max_ahead = max(max_ahead, s.get("ahead", 0))
                    if not s["pending"]:
                        break
                    time.sleep(0.5)
                record("rung3", time.perf_counter() - t0)
                with lock:
                    print(f"  test-{n}: rung 3 after {time.perf_counter() - t0:.1f} s (waited behind {max_ahead})", flush=True)
            r, t = call(base, "answer", token=tok, letter=rng.choice("ABCDE"))
            record("answer", t)
            if r.get("error"):
                raise RuntimeError(r)
            call(base, "shown", token=tok)
            _r, t = call(base, "leaderboard", token=tok)
            record("leaderboard", t)
    except Exception as error:  # noqa: BLE001
        with lock:
            errors.append(f"test-{n}: {error}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:7000")
    ap.add_argument("--teacher-pin", required=True)
    ap.add_argument("--students", type=int, default=4)
    ap.add_argument("--problems", type=int, default=4)
    ap.add_argument("--keep", action="store_true", help="keep the test class and students")
    args = ap.parse_args()
    tt, cid, students = make_class(args.url, args.teacher_pin, args.students)
    barrier = threading.Barrier(args.students)
    print(f"{args.students} students at once, {args.problems} problems each (rung 3 on the first one, all together)")
    threads = [threading.Thread(target=student, args=(args.url, n, sid, pin, args.problems, barrier))
               for n, (sid, pin) in enumerate(students, 1)]
    t0 = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    print(f"\nAll done in {time.perf_counter() - t0:.1f} s. Errors: {errors or 'none'}")
    wrong = str((int(students[0][1]) + 1) % 10000).zfill(4)
    r, _ = call(args.url, "login", sid=students[0][0], pin=wrong)
    print("Wrong PIN:", "refused (ok)" if r.get("error") == "pin" else f"ACCEPTED (problem): {r}")
    print("\n== time per call with everyone working at once")
    for k, v in times.items():
        if v:
            unit, f = ("s", 1) if k == "rung3" else ("ms", 1000)
            print(f"  {k:<11} n={len(v):<3} mean {statistics.mean(v) * f:8.1f} {unit}   max {max(v) * f:8.1f} {unit}")
    lb, _ = call(args.url, "leaderboard", class_id=cid)
    print(f"\n== ranking of the test class ({lb['online']} online)")
    for row in lb["rows"]:
        print(f"  {row['rank']:>2}. {row['name']:<12} {row['points']:>4} points  {row['correct']}/{row['answered']} right"
              f"  best level {row['best_level']}")
    if not args.keep:
        remove_class(args.url, tt, cid, students)
        print("\nTest class removed.")


if __name__ == "__main__":
    main()
