#!/usr/bin/env python3
"""Smoke test of the whole platform API, in process (no server, no board):

    python3 app/math-coach/tools/smoke_platform.py [--db /tmp/smoke.db]

Teacher login, a class with students, student login with PIN (and a wrong PIN), practice with
the hint ladder (rungs 1-2), a test with review, a lesson, a game room with 3 players played to
the end, the teacher's overview and student report, a teacher test with results.
Every call must answer without an "error" key unless the test expects one.
"""
import argparse
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--db", default=os.path.join(tempfile.mkdtemp(), "smoke.db"))
args = ap.parse_args()
os.environ["COACH_DB"] = args.db
os.environ.setdefault("COACH_LLM", "http://127.0.0.1:9")  # no model: rung 3 isn't tested here
os.environ["COACH_LED_PRINT"] = "0"
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import main as app  # noqa: E402

app.REVEAL_SECONDS = 1000  # the host skips the wait with room_next
fails = []


def call(fn, expect_error=False, **kw):
    t = time.perf_counter()
    out = getattr(app, "api_" + fn)(**kw)
    ms = (time.perf_counter() - t) * 1000
    bad = isinstance(out, dict) and "error" in out
    ok = bad == expect_error
    print(f"{'ok ' if ok else 'BAD'} {fn:16s} {ms:7.1f} ms  {json.dumps(out, ensure_ascii=False, default=str)[:150]}")
    if not ok:
        fails.append((fn, out))
    return out


info = call("info")
tt = call("teacher_login", pin=app.TEACHER_PIN)["token"]
call("teacher_login", expect_error=True, pin="nope")
cid = call("t_class", tt=tt, action="create", name="5è A")["id"]
pins = {}
for name in ("Anna", "Biel", "Carla"):
    r = call("t_student_edit", tt=tt, action="add", class_id=cid, name=name)
    pins[r["sid"]] = r["pin"]
call("t_student_edit", expect_error=True, tt=tt, action="add", class_id=cid, name="Anna")
classes = call("classes")["classes"]
sids = list(pins)
call("login", expect_error=True, sid=sids[0], pin="99999")
tok = {sid: call("login", sid=sid, pin=pins[sid])["token"] for sid in sids}
a, b, c = (tok[s] for s in sids)

call("me", token=a)
call("me", expect_error=True, token="nope")
call("settings", token=a, avatar="🐼", lang="esp")

# practice
p = call("practice", token=a, level=2)["problem"]
call("shown", token=a)
call("hint", token=a)
call("hint", token=a)
r = call("answer", token=a, letter=p["options"] and "A")
for _ in range(6):
    r = call("answer", token=a, letter="B")
call("practice", token=b, level=4)
for _ in range(5):
    call("answer", token=b, letter="C")
call("solution", token=a)
call("leaderboard", token=a)

# test
t = call("test_start", token=a, level=3, n=4)
q = t["question"]
while q:
    r = call("test_answer", token=a, session=t["session"], letter="A")
    q = r["question"]
call("test_answer", expect_error=True, token=a, session=t["session"], letter="A")
call("test_review", token=a, session=t["session"])

# lessons
ls = call("lessons", token=a, level=2)["lessons"]
call("lesson", token=a, pid=ls[0]["id"])
call("lesson_done", token=a, pid=ls[0]["id"], guessed=1)

# game with 3 players
room = call("room_create", token=a, rounds=3, seconds=20)
code = room["code"]
call("room_join", token=b, code=code)
call("room_join", token=c, code=code.lower())
call("me", token=c)  # the open room shows in the hub
call("room_start", expect_error=True, token=b, code=code)
call("room_start", token=a, code=code)
for rnd in range(3):
    for i, tk in enumerate((a, b, c)):
        call("room_answer", token=tk, code=code, letter="ABC"[i])
    s = call("room_state", token=a, code=code)
    assert s["phase"] == "reveal", s["phase"]
    s = call("room_next", token=a, code=code)
    s = call("room_state", token=b, code=code)
print("final phase:", s["phase"], [(p["name"], p["score"]) for p in s["players"]])
if s["phase"] != "end":
    fails.append(("game", s["phase"]))

# teacher
test = call("t_test_create", tt=tt, class_id=cid, title="Prova de fraccions", level=2, n=3)
tid = test["id"]
st = call("test_start", token=b, test_id=tid)
q = st["question"]
while q:
    q = call("test_answer", token=b, session=st["session"], letter="D")["question"]
call("me", token=b)
call("t_test", tt=tt, test_id=tid)
call("t_test", tt=tt, test_id=tid, action="close")
call("test_start", expect_error=True, token=c, test_id=tid)
ov = call("t_overview", tt=tt, class_id=cid, lang="cat")
print("overview keys:", sorted(ov))
call("t_student", tt=tt, sid=sids[0], lang="esp")
an = call("t_analysis", tt=tt, class_id=cid, lang="eng")
print("analysis keys:", sorted(an))
call("t_model", tt=tt, class_id=cid)
call("t_analysis", expect_error=True, tt="nope", class_id=cid)
call("t_snapshot", tt=tt, class_id=cid)
call("t_student_edit", tt=tt, action="pin", sid=sids[2])
call("t_class", expect_error=True, tt=tt, action="delete", class_id=cid)
call("logout", token=c)
call("me", expect_error=True, token=c)
json.dumps(ov, ensure_ascii=False)  # must serialise
print(f"\n{len(fails)} failures" + ("" if not fails else ": " + "; ".join(f"{n}: {o}" for n, o in fails)))
sys.exit(1 if fails else 0)
