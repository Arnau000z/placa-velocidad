#!/usr/bin/env python3
"""A demo class for showing the platform: students with different profiles who practised, took
tests, played games and did lessons over the last 7 days. Writes a NEW database, never the class's:

    python3 app/math-coach/tools/seed_demo.py --db app/math-coach/python/data/profiles-demo.db [--force]

Every student's PIN is 1234. The students are simulated with the same model the teacher's
assistant uses (3PL: P(right) = 0.2 + 0.8 * sigmoid(ability - difficulty)), plus behaviours to
detect: a guesser (fast and wrong), a stuck student (slow and wrong), one who relies on hints, one
rising and one falling, three who share a weak family, an attractive wrong answer per problem
(so misconceptions are shared), and one student who never logged in. Response times are
log-normal around a per-level, per-family base time.
"""
import argparse
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--db", required=True)
ap.add_argument("--force", action="store_true", help="replace the file if it exists")
ap.add_argument("--seed", type=int, default=7)
args = ap.parse_args()
if os.path.basename(args.db) == "profiles.db":
    sys.exit("Refusing to write the class's real database (profiles.db).")
if os.path.exists(args.db):
    if not args.force:
        sys.exit(f"{args.db} exists; use --force to replace it.")
    os.remove(args.db)
os.environ["COACH_DB"] = args.db
os.environ["COACH_LLM"] = "http://127.0.0.1:9"  # no model needed
os.environ["COACH_LED_PRINT"] = "0"
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import coach  # noqa: E402
import insights as ai  # noqa: E402
import main as app  # noqa: E402

R = random.Random(args.seed)
bank, profiles, school = app.bank, app.profiles, app.school
DAY = 86400
now = time.time()
today0 = now - 7 * 3600  # each simulated day starts 7 hours before this time of day, so today's activity is in the past

# ---------------------------------------------------------------- the class
for c in school.classes():
    if not c["students"]:
        school.delete_class(c["id"])
cid = school.create_class("5è A")
cid2 = school.create_class("6è B")
logic_fams = [f for f, n in app.family_names["eng"].items() if n["topic"].lower().startswith("logic")]
weak_fam = logic_fams[0] if logic_fams else 0
# name, avatar, level at day 0, level at day 6, speed (time factor), hint use, behaviour, weak family penalty
STUDENTS = [
    ("Anna", "🦊", 5.6, 5.9, 0.75, 0.05, "", 0), ("Biel", "🐢", 4.2, 4.4, 1.7, 0.1, "", 0),
    ("Carla", "🐼", 2.4, 2.5, 1.0, 0.15, "", 1.6), ("Dani", "🐯", 2.0, 1.8, 0.3, 0.0, "guess", 0),
    ("Emma", "🦄", 3.4, 3.6, 1.1, 0.75, "", 0), ("Ferran", "🐨", 2.2, 2.0, 2.1, 0.2, "stuck", 0),
    ("Gina", "🐸", 1.8, 4.6, 1.0, 0.1, "", 0), ("Hugo", "🦁", 4.8, 2.6, 0.9, 0.1, "", 0),
    ("Iris", "🦋", 4.6, 4.9, 0.7, 0.05, "", 0), ("Jan", "🐵", 3.3, 3.4, 1.0, 0.15, "", 0),
    ("Laia", "🐬", 4.0, 4.2, 0.95, 0.1, "", 0), ("Marc", "🦉", 3.4, 3.5, 1.2, 0.1, "", 1.8),
    ("Nora", "🐙", 3.8, 3.9, 1.0, 0.1, "", 1.7), ("Pau", "🐧", None, None, 1, 0, "idle", 0),
    ("Queralt", "🐝", 6.4, 6.7, 0.8, 0.0, "", 0), ("Roc", "🐳", 2.8, 2.9, 1.3, 0.25, "", 0),
]
sids = {}
for name, av, *_ in STUDENTS:
    sid, _pin = school.add_student(cid, name)
    school.set_pin(sid, "1234")
    school.set_avatar(sid, av)
    sids[name] = sid
for name, av in (("Àlex", "🦒"), ("Berta", "🐞"), ("Cesc", "🐹"), ("Dàlia", "🦜")):
    sid, _pin = school.add_student(cid2, name)
    school.set_pin(sid, "1234")
    school.set_avatar(sid, av)
    sids[name] = sid

fam_time = {f: R.uniform(0.75, 1.6) for f in app.family_names["eng"]}
attractive = {p["id"]: R.choice([k for k in "ABCDE" if k != p["label"]]) for p in bank.problems}


def level_on(st, day):
    _n, _a, l0, l1, *_ = st
    return l0 + (l1 - l0) * day / 6


def answer(st, p, day, hints=0):
    """(letter, correct, seconds) for student st on problem p."""
    name, _a, _l0, _l1, speed, _h, beh, pen = st
    lv = level_on(st, day)
    theta = ai.b_prior(lv) + ai.LOGIT_HALF
    b = ai.b_prior(p["level"]) + (pen if p["family"] == weak_fam else 0)
    pr = ai.p_right(theta + 0.5 * hints, b)
    if beh == "guess":
        pr = 0.2 if R.random() < 0.8 else pr
    correct = R.random() < pr
    if correct:
        letter = p["label"]
    else:
        letter = attractive[p["id"]] if R.random() < 0.6 else R.choice([k for k in "ABCDE" if k != p["label"]])
    base = (28 + 11 * p["level"]) * fam_time[p["family"]] * speed
    if beh == "guess":
        base = R.uniform(5, 11)
    if beh == "stuck" and not correct:
        base *= 1.5
    seconds = round(min(900, math.exp(math.log(base) + R.gauss(0, 0.35))), 1)
    return letter, correct, seconds


def stamp(ts):
    profiles._q("UPDATE attempts SET ts = ? WHERE id = (SELECT MAX(id) FROM attempts)", (ts,))


def practice(st, sid, day, n, t):
    seen = profiles.seen(sid)
    lv = max(0, min(7, round(level_on(st, day))))
    p = coach.first_problem(bank, lv, seen, R)
    for _ in range(n):
        hints = R.choice([1, 2, 2, 3]) if R.random() < st[5] else 0
        letter, ok, secs = answer(st, p, day, hints)
        profiles.record_attempt(sid, p, letter, ok, hints, False, secs, "cat")
        t += secs + R.uniform(8, 25)
        stamp(t)
        for r in range(1, hints + 1):
            profiles.record_hint(sid, p["id"], r, False, 0.05)
        nxt, reason = coach.next_problem(bank, p, ok, profiles.seen(sid))
        p = nxt
    profiles.set_state(sid, p["id"], reason)
    return t


def take_test(st, sid, day, ids, test_id, t0):
    sess = school.new_session(sid, test_id, bank.by_id[ids[0]]["level"], ids)
    s = school.session(sess)
    t = t0
    for pid in ids:
        p = bank.by_id[pid]
        letter, ok, secs = answer(st, p, day)
        pts = profiles.record_attempt(sid, p, letter, ok, 0, False, secs, "cat", source="test")
        t += secs + 2
        stamp(t)
        s["answers"].append({"id": pid, "answer": letter, "correct": ok, "seconds": secs})
        s["correct"] += int(ok)
        s["points"] += pts
    s["finished"] = t
    school.save_session(s)
    profiles._q("UPDATE test_sessions SET started = ? WHERE id = ?", (t0, sess))


def game(names, day, level, rounds=6, seconds=60):
    t = today0 - (6 - day) * DAY + 5 * 3600
    ids = [p["id"] for p in app.pick_problems(level, rounds)]
    score = {n: [0, 0] for n in names}
    for pid in ids:
        p = bank.by_id[pid]
        for n in names:
            st = next(s for s in STUDENTS if s[0] == n)
            letter, ok, secs = answer(st, p, day)
            secs = min(secs, seconds)
            profiles.record_attempt(sids[n], p, letter, ok, 0, False, secs, "cat", source="game", points=0)
            stamp(t + secs)
            if ok:
                score[n][0] += 100 + round(100 * max(0.0, 1 - secs / seconds))
                score[n][1] += 1
        t += seconds + 7
    ranking = sorted(names, key=lambda n: -score[n][0])
    players = [{"sid": sids[n], "name": n, "score": score[n][0], "correct": score[n][1]} for n in ranking]
    code = "".join(R.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))
    school.save_game(cid, code, t - rounds * (seconds + 7), rounds, players, players[0]["sid"] if players[0]["score"] else None)
    profiles._q("UPDATE games SET finished = ? WHERE id = (SELECT MAX(id) FROM games)", (t,))


test_ids = [p["id"] for p in app.pick_problems(3, 8, family=weak_fam)]
teacher_test = None
for day in range(7):
    day0 = today0 - (6 - day) * DAY
    for st in STUDENTS:
        if st[6] == "idle" or R.random() < 0.25:
            continue
        sid = sids[st[0]]
        t = day0 + R.uniform(0, 5 * 3600)
        t = practice(st, sid, day, R.randint(5, 12), t)
        if day in (1, 4) and R.random() < 0.5:
            lv = max(0, min(7, round(level_on(st, day))))
            take_test(st, sid, day, [p["id"] for p in app.pick_problems(lv, 6, profiles.seen(sid))], None, t + 300)
    if day == 2:
        game(["Anna", "Biel", "Gina", "Jan"], day, 3)
    if day == 5:
        game(["Iris", "Laia", "Hugo", "Marc", "Nora"], day, 4)
        teacher_test = school.create_test(cid, "Prova de lògica", 3, len(test_ids), weak_fam, test_ids, 20)
        profiles._q("UPDATE tests SET created = ? WHERE id = ?", (day0, teacher_test))
        for st in STUDENTS:
            if st[6] != "idle" and st[0] not in ("Dani", "Roc", "Gina"):
                take_test(st, sids[st[0]], day, test_ids, teacher_test, day0 + 6 * 3600 + R.uniform(0, 1800))
    if day == 6:
        game(["Queralt", "Anna", "Iris"], day, 5, rounds=5)
    if day == 3:  # a snapshot of the weak families, to compare with later
        rep = app.assistant.class_report(cid, school.students_of(cid), app.family_names["cat"], "cat")
        ts = profiles.save_snapshot(rep["weak"], cid)
        profiles._q("UPDATE family_history SET ts = ? WHERE ts = ?", (day0 + 10 * 3600, ts))

# the second class: a little activity
for name in ("Àlex", "Berta", "Cesc"):
    st = (name, "", 3.0 + R.uniform(-1, 1), 3.2, 1.0, 0.1, "", 0)
    practice(st, sids[name], 6, R.randint(4, 8), today0 + R.uniform(0, 3600))

# lessons
for name, k in (("Carla", 4), ("Marc", 6), ("Ferran", 3), ("Gina", 7), ("Emma", 2), ("Nora", 5)):
    for p in R.sample([p for p in bank.problems if p.get("explanation") and p["level"] <= 4], k):
        school.lesson_done(sids[name], p["id"], R.random() < 0.5)

school.create_test(cid, "Repàs de fraccions", 2, 8, None, [p["id"] for p in app.pick_problems(2, 8)], 0)
n = profiles._q("SELECT COUNT(*) FROM attempts", one=True)[0]
print(f"Demo database: {args.db}\n  classes: 5è A ({len(STUDENTS)} students), 6è B (4)\n  answers: {n}; every PIN: 1234; teacher PIN: {app.TEACHER_PIN}")
