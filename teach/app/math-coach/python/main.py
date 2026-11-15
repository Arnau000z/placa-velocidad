"""Math Coach (App Lab app): a classroom platform for Kangaroo problems, on the Arduino UNO Q.

Students pick their name in their class and type their PIN. Then they can practise (adaptive
trainer + hint ladder), take tests (their own or the teacher's), play live games with friends
in a room (same problem for everyone, points for right and fast answers), and learn step by
step from solved problems. The teacher sees the class through an AI assistant (insights.py):
ability model, semantic families of mistakes, shared misconceptions, response times, alerts.

Logic: coach.py (map, trainer, ladder, profiles), school.py (classes, PINs, tests, games, lessons),
insights.py (the teacher's AI). This file is the API. On the board App Lab serves it (web_ui
brick, port 7000) and draws the LED matrix; on a laptop dev_server.py serves the same API.
"""
import heapq
import itertools
import json
import math
import os
import random
import re
import secrets
import statistics
import threading
import time
from collections import Counter, defaultdict

try:  # on the board (App Lab): the web_ui brick and the LED matrix
    import numpy as np
    from arduino.app_bricks.web_ui import WebUI
    from arduino.app_utils import App, Bridge, Frame
    ON_BOARD = True
except ImportError:  # on the laptop: dev_server.py serves the same API, and the matrix is drawn in the terminal
    ON_BOARD = False

import coach
import insights as ai
from school import AVATARS, School

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("COACH_DATA", os.path.join(HERE, "data"))
bank = coach.Bank(os.path.join(DATA, "bank.json"))
profiles = coach.Profiles(os.environ.get("COACH_DB", os.path.join(DATA, "profiles.db")))
school = School(profiles)
coach.semantic_families(bank)
family_names = {lang: coach.family_names(bank, lang) for lang in coach.LANGS}
assistant = ai.Insights(bank, profiles)
rng = random.Random()

PIN_FILE = os.path.join(DATA, "teacher_pin.txt")
if not os.path.exists(PIN_FILE):
    with open(PIN_FILE, "w") as f:
        f.write(f"{secrets.randbelow(10000):04d}\n")
with open(PIN_FILE) as f:
    TEACHER_PIN = f.read().strip()

AUTH = {"error": "auth"}
LANG = lambda lang: lang if lang in coach.LANGS else "cat"  # noqa: E731

# ---------------------------------------------------------------- LED matrix (8 x 13), shared by everyone
DIGITS = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
}
MARKS = {
    "tick": ["......", ".....#", "....##", "#..##.", "####..", ".##...", "......"],
    "cross": ["#....#", ".#..#.", "..##..", "..##..", ".#..#.", "#....#", "......"],
    "ask": [".###..", "#...#.", "...#..", "..#...", "..#...", "......", "..#..."],
    "wait": ["......", "......", "......", "#.#.#.", "......", "......", "......"],
}
led_lock = threading.Lock()
last_frame = {"grid": [[0] * 13 for _ in range(8)], "mark": "ask", "level": 0}


def show(mark, level):
    level = max(0, min(7, int(level)))
    grid = [[0] * 13 for _ in range(8)]
    for r, line in enumerate(MARKS[mark]):
        for c, px in enumerate(line):
            if px == "#":
                grid[r][c] = 7
    for r, line in enumerate(DIGITS[str(level)]):
        for c, px in enumerate(line):
            if px == "#":
                grid[r][8 + c] = 4
    last_frame.update(grid=grid, mark=mark, level=level)
    if not ON_BOARD:
        if os.environ.get("COACH_LED_PRINT", "1") == "1":
            art = "\n".join("   " + "".join("██" if v == 7 else "▒▒" if v else "··" for v in row) for row in grid)
            print(f"LED matrix: {mark} level {level}\n{art}", flush=True)
        return
    try:
        with led_lock:
            Bridge.call("draw", Frame(np.array(grid, dtype=np.uint8)).to_board_bytes())
    except Exception as error:  # the page must keep working even if the sketch isn't ready
        print("LED matrix:", error, flush=True)


# ---------------------------------------------------------------- sessions: student and teacher tokens
ONLINE = 60
tokens = {}          # token -> {"sid", "last"}
teacher_tokens = {}  # token -> last
tok_lock = threading.Lock()


def me(token):
    with tok_lock:
        t = tokens.get(token)
        if not t:
            return None
        t["last"] = time.time()
        return t["sid"]


def teacher(tt):
    with tok_lock:
        if tt in teacher_tokens:
            teacher_tokens[tt] = time.time()
            return True
    return False


def online_sids():
    now = time.time()
    return {t["sid"] for t in list(tokens.values()) if now - t["last"] < ONLINE}


# ---------------------------------------------------------------- the model: one worker, a priority queue, a cache
WAITED, PREFETCH = 0, 1
hint_heap, hint_cv, hint_seq = [], threading.Condition(), itertools.count()
hint_errors, working, waiting = {}, {"key": None}, {}


def lang_of(problem, lang):
    return lang if lang in problem["langs"] else "eng"


def request_hint(pid, lang, priority):
    with hint_cv:
        seq = next(hint_seq)
        heapq.heappush(hint_heap, (priority, seq, pid, lang))
        hint_cv.notify()
    return seq


def hint_worker():
    while True:
        with hint_cv:
            while not hint_heap:
                hint_cv.wait()
            priority, _seq, pid, lang = heapq.heappop(hint_heap)
            working["key"] = (pid, lang)
        try:
            if profiles.cached_hint(pid, lang) is None:
                if priority == WAITED:
                    show("wait", bank.by_id[pid]["level"])
                profiles.cache_hint(pid, lang, coach.rung3_model_hint(bank.by_id[pid], lang))
                hint_errors.pop((pid, lang), None)
        except Exception as error:  # noqa: BLE001 - the worker must survive anything
            hint_errors[(pid, lang)] = str(error)
        finally:
            working["key"] = None


threading.Thread(target=hint_worker, daemon=True).start()


def ahead_of(job):
    with hint_cv:
        n = sum(1 for prio, seq, pid, lang in hint_heap if prio == WAITED and seq < job["seq"] and (pid, lang) != job["key"])
        busy_other = working["key"] is not None and working["key"] != job["key"]
    return n + int(busy_other)


# ---------------------------------------------------------------- helpers
def student_lang(sid):
    return profiles.lang(sid)


def current(sid):
    state = profiles.state(sid)
    return (bank.by_id[state["problem_id"]], state) if state and state["problem_id"] in bank.by_id else (None, None)


def problem_view(sid, problem, state):
    view = bank.view(problem, student_lang(sid))
    view.update(rung=state["rung"], solution_shown=bool(state["solution_shown"]), reason=state.get("reason"),
                worth=coach.points_for(problem["level"], True, 0, False), topic_key=problem["topic"])
    return view


def pick_problems(level, n, seen=(), family=None, exclude=()):
    """n problems at `level` (neighbour levels if short), unseen first, one family at a time for variety."""
    pool = [p for p in bank.problems if p["level"] == level and (family is None or p["family"] == family)]
    for d in (1, -1, 2, -2):
        if len(pool) >= n * 2:
            break
        pool += [p for p in bank.problems if p["level"] == level + d and (family is None or p["family"] == family)]
    pool = [p for p in pool if p["id"] not in exclude]
    rng.shuffle(pool)
    pool.sort(key=lambda p: p["id"] in seen)
    by_fam = defaultdict(list)
    for p in pool:
        by_fam[p["family"]].append(p)
    order = list(by_fam)
    rng.shuffle(order)
    picked = []
    while len(picked) < n and any(by_fam.values()):
        for f in order:
            if by_fam[f] and len(picked) < n:
                picked.append(by_fam[f].pop(0))
    return picked


def badges(sid):
    rows = profiles._q("SELECT correct, hints, level, source, problem_id FROM attempts WHERE student_id = ? ORDER BY id", (sid,))
    best = run = 0
    for r in rows:
        run = run + 1 if r[0] else 0
        best = max(best, run)
    right = [r for r in rows if r[0]]
    fams = {bank.by_id[r[4]]["family"] for r in right if r[4] in bank.by_id}
    tests = school.sessions_of(sid, 50)
    have = {
        "first": len(rows) >= 1, "ten_right": len(right) >= 10, "streak5": best >= 5,
        "no_hints": sum(1 for r in right if r[1] == 0) >= 5, "level3": any(r[2] >= 3 for r in right),
        "level5": any(r[2] >= 5 for r in right), "explorer": len(fams) >= 5,
        "tester": any(t["n"] and t["correct"] / t["n"] >= 0.8 for t in tests), "winner": school.wins(sid) >= 1,
        "learner": len(school.lessons_done(sid)) >= 5,
    }
    return [{"code": k, "earned": v} for k, v in have.items()]


def stats(sid):
    s = profiles.summary(sid)
    s["est_level"] = assistant.student_level(sid)
    s["wins"] = school.wins(sid)
    s["lessons"] = len(school.lessons_done(sid))
    problem, _state = current(sid)
    s["level"] = problem["level"] if problem else None
    lang = student_lang(sid)
    s["by_topic"] = {coach.topic_name(t, lang): v for t, v in s["by_topic"].items()}
    return s


# ---------------------------------------------------------------- login, hub
def api_info():
    levels = Counter(p["level"] for p in bank.problems)
    return {"problems": len(bank.problems), "levels": dict(levels), "llm": coach.llm_url() is not None,
            "embedding": bank.meta.get("embedding"), "avatars": AVATARS, "lessons": sum(1 for p in bank.problems if p.get("explanation")),
            "points": {lvl: coach.points_for(lvl, True, 0, False) for lvl in range(coach.MAX_LEVEL + 1)}}


def api_classes():
    on = online_sids()
    out = school.classes()
    for c in out:
        for s in c["students"]:
            s["online"] = s["id"] in on
    return {"classes": out}


def api_login(sid: int, pin: str):
    ok, locked = school.check_pin(sid, pin)
    if not ok:
        return {"error": "pin", "locked": locked}
    token = secrets.token_hex(16)
    with tok_lock:
        tokens[token] = {"sid": sid, "last": time.time()}
    return {"token": token, "student": school.student(sid)}


def api_logout(token: str):
    with tok_lock:
        tokens.pop(token, None)
    return {"ok": True}


def api_me(token: str):
    sid = me(token)
    if sid is None:
        return AUTH
    st = school.student(sid)
    done = school.done_tests(sid)
    tests = [t for t in school.tests_of_class(st["class_id"], active_only=True) if t["id"] not in done]
    return {"student": st, "stats": stats(sid), "badges": badges(sid), "tests": tests,
            "rooms": open_rooms(st["class_id"]), "recent_tests": school.sessions_of(sid, 5)}


def api_settings(token: str, avatar: str = "", lang: str = ""):
    sid = me(token)
    if sid is None:
        return AUTH
    if avatar:
        school.set_avatar(sid, avatar)
    if lang in coach.LANGS:
        school.set_lang(sid, lang)
    return {"student": school.student(sid)}


def api_leaderboard(token: str = "", class_id: int = 0):
    sid = me(token) if token else None
    cid = school.student(sid)["class_id"] if sid else class_id
    ids = set(school.students_of(cid))
    on = online_sids()
    rows = [r for r in profiles.leaderboard(limit=200) if r["sid"] in ids]
    for i, r in enumerate(rows):
        st = school.student(r["sid"])
        r.update(rank=i + 1, online=r["sid"] in on, me=r["sid"] == sid, avatar=st["avatar"] if st else "", wins=school.wins(r["sid"]))
        r.pop("last", None)
    return {"rows": rows[:30], "online": len(on & ids)}


# ---------------------------------------------------------------- practice: adaptive trainer + hint ladder
def api_practice(token: str, level: int = -1, restart: int = 0):
    sid = me(token)
    if sid is None:
        return AUTH
    problem, state = current(sid)
    if problem is None or restart:
        if level < 0:
            est = assistant.student_level(sid)
            level = int(est) if est is not None else 0
        problem = coach.first_problem(bank, max(0, min(7, level)), profiles.seen(sid), rng)
        profiles.set_state(sid, problem["id"], "start")
        problem, state = current(sid)
    profiles.restart_clock(sid)
    show("ask", problem["level"])
    return {"problem": problem_view(sid, problem, profiles.state(sid)), "stats": stats(sid)}


def api_answer(token: str, letter: str):
    sid = me(token)
    if sid is None:
        return AUTH
    problem, state = current(sid)
    if problem is None or letter not in ("A", "B", "C", "D", "E"):
        return {"error": "no problem or bad letter"}
    lang = student_lang(sid)
    correct = letter == problem["label"]
    solution_shown = bool(state["solution_shown"])
    hints = min(state["rung"], 3)
    seconds = round(time.time() - state["started"], 1)
    points = profiles.record_attempt(sid, problem, letter, correct, hints, solution_shown, seconds, lang_of(problem, lang))
    show("tick" if correct else "cross", problem["level"])
    waiting.pop(sid, None)
    nxt, reason = coach.next_problem(bank, problem, correct and not solution_shown, profiles.seen(sid))
    profiles.set_state(sid, nxt["id"], reason)
    view = bank.view(problem, lang, with_answer=True)
    nxt_problem, nxt_state = current(sid)
    return {"correct": correct, "label": problem["label"], "value": view["value"], "points": points, "hints": hints,
            "seconds": seconds, "explanation": view["explanation"], "explanation_lang": view["explanation_lang"],
            "has_lesson": bool(problem.get("explanation")), "problem_id": problem["id"],
            "next": problem_view(sid, nxt_problem, nxt_state), "next_reason": reason, "stats": stats(sid),
            "badges": badges(sid)}


def api_shown(token: str):
    sid = me(token)
    if sid is None:
        return AUTH
    problem, _state = current(sid)
    if problem:
        profiles.restart_clock(sid)
        show("ask", problem["level"])
    return {"ok": True}


def api_hint(token: str):
    sid = me(token)
    if sid is None:
        return AUTH
    problem, state = current(sid)
    if problem is None:
        return {"error": "no problem"}
    lang = student_lang(sid)
    code = lang_of(problem, lang)
    rung = state["rung"] + 1
    start = time.perf_counter()
    if rung == 1:
        easier, score = coach.rung1_easier_problem(bank, problem)
        profiles.mark_shown_solved(sid, easier["id"])
        profiles.climb(sid, 1)
        profiles.record_hint(sid, problem["id"], 1, False, time.perf_counter() - start)
        if profiles.cached_hint(problem["id"], code) is None:
            request_hint(problem["id"], code, PREFETCH)
        return {"rung": 1, "similarity": round(score, 3), "problem": bank.view(easier, lang, with_answer=True),
                "topic": coach.topic_name(easier["topic"], lang)}
    if rung == 2:
        topic, _votes = coach.rung2_topic(bank, problem)
        profiles.climb(sid, 2)
        profiles.record_hint(sid, problem["id"], 2, False, time.perf_counter() - start)
        return {"rung": 2, "topic": coach.topic_name(topic, lang), "method": coach.TOPICS[topic][lang][1]}
    if rung == 3:
        key = (problem["id"], code)
        cached = profiles.cached_hint(*key) is not None
        hint_errors.pop(key, None)
        waiting[sid] = {"key": key, "seq": -1 if cached else request_hint(problem["id"], code, WAITED),
                        "started": time.time(), "recorded": False, "was_cached": cached}
        profiles.climb(sid, 3)
        return {"rung": 3, "pending": not cached}
    return {"rung": state["rung"], "done": True}


def api_hint_status(token: str):
    sid = me(token)
    if sid is None:
        return AUTH
    job = waiting.get(sid)
    if not job:
        return {"pending": False, "result": None}
    pid, code = job["key"]
    result = profiles.cached_hint(pid, code)
    waited = round(time.time() - job["started"], 1)
    if result is None:
        if job["key"] in hint_errors:
            return {"pending": False, "result": {"hint": None, "error": hint_errors[job["key"]], "seconds": waited}}
        return {"pending": True, "ahead": ahead_of(job), "waited": waited}
    result = dict(result, seconds=waited, cached=job["was_cached"])
    if result.get("hint") is None:
        topic, _votes = coach.rung2_topic(bank, bank.by_id[pid])
        result["fallback"] = coach.TOPICS[topic][student_lang(sid)][1]
    if not job["recorded"]:
        job["recorded"] = True
        leaked = any(a["leak"] for a in result.get("attempts", []))
        profiles.record_hint(sid, pid, 3, leaked and not job["was_cached"], waited)
    return {"pending": False, "result": result, "waited": waited}


def api_solution(token: str):
    sid = me(token)
    if sid is None:
        return AUTH
    problem, _state = current(sid)
    if problem is None:
        return {"error": "no problem"}
    profiles.mark_solution(sid)
    profiles.record_hint(sid, problem["id"], 4, False, 0.0)
    view = bank.view(problem, student_lang(sid), with_answer=True)
    return {"rung": 4, "label": view["label"], "value": view["value"], "explanation": view["explanation"],
            "explanation_lang": view["explanation_lang"],
            "has_lesson": bool(problem.get("explanation")), "problem_id": problem["id"]}


# ---------------------------------------------------------------- tests (no hints; own or set by the teacher)
def test_question(sess, sid):
    i = len(sess["answers"])
    p = bank.by_id[sess["problem_ids"][i]]
    view = bank.view(p, student_lang(sid))
    view.update(index=i, total=len(sess["problem_ids"]))
    return view


def api_test_start(token: str, level: int = -1, n: int = 10, test_id: int = 0):
    sid = me(token)
    if sid is None:
        return AUTH
    minutes = 0
    if test_id:
        t = school.test(test_id)
        if not t or not t["active"] or t["class_id"] != school.student(sid)["class_id"]:
            return {"error": "test"}
        ids, level, minutes = t["problem_ids"], t["level"], t["minutes"]
    else:
        if level < 0:
            est = assistant.student_level(sid)
            level = int(est) if est is not None else 0
        ids = [p["id"] for p in pick_problems(max(0, min(7, level)), max(3, min(20, n)), profiles.seen(sid))]
    sess_id = school.new_session(sid, test_id or None, level, ids)
    sess = school.session(sess_id)
    test_clock[sess_id] = time.time()
    show("ask", level)
    return {"session": sess_id, "question": test_question(sess, sid), "minutes": minutes, "level": level}


test_clock = {}  # session -> when its current question appeared


def api_test_answer(token: str, session: int, letter: str):
    sid = me(token)
    if sid is None:
        return AUTH
    sess = school.session(session)
    if not sess or sess["student_id"] != sid or sess["finished"] or letter not in "ABCDE" or len(letter) != 1:
        return {"error": "session"}
    p = bank.by_id[sess["problem_ids"][len(sess["answers"])]]
    correct = letter == p["label"]
    seconds = round(time.time() - test_clock.get(session, time.time()), 1)
    points = profiles.record_attempt(sid, p, letter, correct, 0, False, seconds, lang_of(p, student_lang(sid)), source="test")
    sess["answers"].append({"id": p["id"], "answer": letter, "correct": correct, "seconds": seconds})
    sess["correct"] += int(correct)
    sess["points"] += points
    show("tick" if correct else "cross", p["level"])
    done = len(sess["answers"]) == len(sess["problem_ids"])
    if done:
        sess["finished"] = time.time()
    school.save_session(sess)
    test_clock[session] = time.time()
    return {"correct": correct, "done": done, "question": None if done else test_question(sess, sid),
            "score": sess["correct"], "answered": len(sess["answers"])}


def api_test_review(token: str, session: int):
    sid = me(token)
    if sid is None:
        return AUTH
    sess = school.session(session)
    if not sess or sess["student_id"] != sid:
        return {"error": "session"}
    lang = student_lang(sid)
    names = family_names[lang]
    items, fams = [], defaultdict(lambda: [0, 0])
    for a in sess["answers"]:
        p = bank.by_id[a["id"]]
        v = bank.view(p, lang, with_answer=True)
        fams[p["family"]][0] += a["correct"]
        fams[p["family"]][1] += 1
        items.append({"text": v["text"], "options": v["options"], "answer": a["answer"], "label": v["label"],
                      "value": v["value"], "correct": a["correct"], "seconds": a["seconds"], "explanation": v["explanation"],
                      "explanation_lang": v["explanation_lang"],
                      "has_lesson": bool(p.get("explanation")), "id": p["id"], "level": p["level"]})
    weak = [{"topic": names[f]["topic"], "words": names[f]["words"], "ok": c[0], "n": c[1]}
            for f, c in sorted(fams.items(), key=lambda fc: fc[1][0] / fc[1][1]) if c[0] < c[1]]
    secs = [a["seconds"] for a in sess["answers"]]
    return {"items": items, "correct": sess["correct"], "n": len(sess["problem_ids"]), "points": sess["points"],
            "level": sess["level"], "weak": weak[:3], "median_seconds": statistics.median(secs) if secs else None,
            "est_level": assistant.student_level(sid)}


# ---------------------------------------------------------------- learn step by step
def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú0-9(])", " ".join(text.split()))
    return [s.strip() for s in parts if len(s.strip()) > 2]


def api_lessons(token: str, level: int = -1):
    sid = me(token)
    if sid is None:
        return AUTH
    lang = student_lang(sid)
    done = school.lessons_done(sid)
    names = family_names[lang]
    out = []
    for p in bank.problems:
        if p.get("explanation") and (level < 0 or p["level"] == level):
            v = bank.view(p, lang)
            out.append({"id": p["id"], "level": p["level"], "topic": coach.topic_name(p["topic"], lang), "topic_key": p["topic"],
                        "words": names[p["family"]]["words"], "text": v["text"][:160], "done": p["id"] in done,
                        "guessed": done.get(p["id"], False)})
    return {"lessons": out, "done": len(done)}


def api_lesson(token: str, pid: str):
    sid = me(token)
    if sid is None:
        return AUTH
    p = bank.by_id.get(pid)
    if not p or not p.get("explanation"):
        return {"error": "lesson"}
    lang = student_lang(sid)
    v = bank.view(p, lang, with_answer=True)
    sents = sentences(v["text"])
    question = next((s for s in reversed(sents) if "?" in s), sents[-1] if sents else v["text"])
    numbers = list(dict.fromkeys(re.findall(r"\d+(?:[.,]\d+)?", v["text"])))[:10]
    expl = (p.get("explanation_i18n") or {}).get(lang) or p["explanation"]
    return {"id": p["id"], "level": p["level"], "text": v["text"], "options": v["options"], "label": v["label"],
            "value": v["value"], "question": question, "numbers": numbers,
            "topic": coach.topic_name(p["topic"], lang), "method": coach.TOPICS[p["topic"]][lang][1],
            "steps": sentences(expl), "steps_lang": lang if (p.get("explanation_i18n") or {}).get(lang) else "eng",
            "words": family_names[lang][p["family"]]["words"]}


def api_lesson_done(token: str, pid: str, guessed: int = 0):
    sid = me(token)
    if sid is None:
        return AUTH
    if pid in bank.by_id:
        school.lesson_done(sid, pid, bool(guessed))
    return {"ok": True, "badges": badges(sid)}


# ---------------------------------------------------------------- live games ("rooms")
REVEAL_SECONDS = 7
rooms = {}
rooms_lock = threading.Lock()


def new_code():
    while True:
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))
        if code not in rooms:
            return code


def open_rooms(cid):
    with rooms_lock:
        return [{"code": r["code"], "host": r["players"][r["host"]]["name"], "players": len(r["players"]),
                 "rounds": r["rounds"], "level": r["level"]} for r in rooms.values()
                if r["class_id"] == cid and r["phase"] == "lobby" and time.time() - r["created"] < 3600]


def player_entry(sid):
    st = school.student(sid)
    return {"sid": sid, "name": st["name"], "avatar": st["avatar"], "score": 0, "correct": 0, "answers": {}}


def advance(room):
    """The room's clock: moves from question to reveal to the next question, or to the end."""
    now = time.time()
    if room["phase"] == "question":
        everyone = all(room["round"] in p["answers"] for p in room["players"].values())
        if everyone or now >= room["round_started"] + room["seconds"]:
            room["phase"], room["reveal_started"] = "reveal", now
            problem = bank.by_id[room["problems"][room["round"]]]
            right = 0
            for p in room["players"].values():
                a = p["answers"].get(room["round"])
                if a and a["correct"]:
                    right += 1
                if a:
                    profiles.record_attempt(p["sid"], problem, a["letter"], a["correct"], 0, False, a["seconds"],
                                            lang_of(problem, student_lang(p["sid"])), source="game", points=0)
            show("tick" if right * 2 >= len(room["players"]) else "cross", problem["level"])
    elif room["phase"] == "reveal" and now >= room["reveal_started"] + REVEAL_SECONDS:
        if room["round"] + 1 >= room["rounds"]:
            room["phase"] = "end"
            ranking = sorted(room["players"].values(), key=lambda p: -p["score"])
            winner = ranking[0]["sid"] if ranking and ranking[0]["score"] > 0 else None
            school.save_game(room["class_id"], room["code"], room["created"], room["rounds"],
                             [{"sid": p["sid"], "name": p["name"], "score": p["score"], "correct": p["correct"]} for p in ranking],
                             winner)
        else:
            room["round"] += 1
            room["phase"], room["round_started"] = "question", now
            for p in room["players"].values():
                p["last_points"] = 0
            show("ask", bank.by_id[room["problems"][room["round"]]]["level"])


def room_view(room, sid):
    advance(room)
    lang = student_lang(sid)
    out = {"code": room["code"], "phase": room["phase"], "host": room["host"] == sid, "host_sid": room["host"], "round": room["round"],
           "rounds": room["rounds"], "seconds": room["seconds"], "level": room["level"],
           "players": sorted(({"sid": p["sid"], "name": p["name"], "avatar": p["avatar"], "score": p["score"],
                               "correct": p["correct"], "answered": room["round"] in p["answers"], "me": p["sid"] == sid,
                               "last": p.get("last_points", 0)} for p in room["players"].values()), key=lambda x: -x["score"])}
    if room["phase"] in ("question", "reveal"):
        problem = bank.by_id[room["problems"][room["round"]]]
        v = bank.view(problem, lang, with_answer=room["phase"] == "reveal")
        out["problem"] = {k: v[k] for k in ("text", "options", "level") if k in v}
        out["left"] = max(0, round(room["round_started"] + room["seconds"] - time.time(), 1))
        mine = room["players"].get(sid, {}).get("answers", {}).get(room["round"])
        out["my_answer"] = mine["letter"] if mine else None
        if room["phase"] == "reveal":
            out["problem"].update(label=v["label"], value=v["value"])
            out["next_in"] = max(0, round(room["reveal_started"] + REVEAL_SECONDS - time.time(), 1))
            out["round_answers"] = {p["sid"]: (p["answers"].get(room["round"]) or {}).get("letter") for p in room["players"].values()}
    return out


def api_room_create(token: str, rounds: int = 6, seconds: int = 60, level: int = -1):
    sid = me(token)
    if sid is None:
        return AUTH
    st = school.student(sid)
    with rooms_lock:
        code = new_code()
        rooms[code] = {"code": code, "host": sid, "class_id": st["class_id"], "players": {sid: player_entry(sid)},
                       "rounds": max(3, min(12, rounds)), "seconds": max(20, min(180, seconds)), "level": level,
                       "phase": "lobby", "round": 0, "problems": [], "created": time.time()}
        return room_view(rooms[code], sid)


def api_room_join(token: str, code: str):
    sid = me(token)
    if sid is None:
        return AUTH
    with rooms_lock:
        room = rooms.get(code.upper().strip())
        if not room:
            return {"error": "room"}
        if sid not in room["players"]:
            if room["phase"] != "lobby":
                return {"error": "started"}
            room["players"][sid] = player_entry(sid)
        return room_view(room, sid)


def api_room_leave(token: str, code: str):
    sid = me(token)
    with rooms_lock:
        room = rooms.get(code)
        if room and sid in room["players"] and room["phase"] == "lobby":
            del room["players"][sid]
            if not room["players"]:
                del rooms[code]
            elif room["host"] == sid:
                room["host"] = next(iter(room["players"]))
    return {"ok": True}


def api_room_start(token: str, code: str):
    sid = me(token)
    with rooms_lock:
        room = rooms.get(code)
        if not room or room["host"] != sid or room["phase"] != "lobby":
            return {"error": "room"}
        level = room["level"]
        if level < 0:  # auto: the players' average estimated level
            ests = [assistant.student_level(s) for s in room["players"]]
            ests = [e for e in ests if e is not None]
            level = round(statistics.mean(ests)) if ests else 2
        room["level"] = max(0, min(7, level))
        seen = set()
        for s in room["players"]:
            seen |= profiles.seen(s)
        room["problems"] = [p["id"] for p in pick_problems(room["level"], room["rounds"], seen)]
        room["rounds"] = len(room["problems"])
        room["phase"], room["round"], room["round_started"] = "question", 0, time.time()
        show("ask", room["level"])
        return room_view(room, sid)


def api_room_state(token: str, code: str):
    sid = me(token)
    if sid is None:
        return AUTH
    with rooms_lock:
        room = rooms.get(code)
        if not room or sid not in room["players"]:
            return {"error": "room"}
        return room_view(room, sid)


def api_room_answer(token: str, code: str, letter: str):
    sid = me(token)
    with rooms_lock:
        room = rooms.get(code)
        if not room or sid not in room["players"] or room["phase"] != "question" or letter not in "ABCDE":
            return {"error": "room"}
        player = room["players"][sid]
        if room["round"] not in player["answers"]:
            problem = bank.by_id[room["problems"][room["round"]]]
            elapsed = time.time() - room["round_started"]
            correct = letter == problem["label"]
            points = 100 + round(100 * max(0.0, 1 - elapsed / room["seconds"])) if correct else 0
            player["answers"][room["round"]] = {"letter": letter, "correct": correct, "seconds": round(elapsed, 1)}
            player["score"] += points
            player["correct"] += int(correct)
            player["last_points"] = points
        return room_view(room, sid)


def api_room_next(token: str, code: str):
    """The host can skip the waiting at the end of a round."""
    sid = me(token)
    with rooms_lock:
        room = rooms.get(code)
        if room and room["host"] == sid and room["phase"] == "reveal":
            room["reveal_started"] = 0
            return room_view(room, sid)
    return {"error": "room"}


# ---------------------------------------------------------------- the teacher
def api_teacher_login(pin: str):
    if not secrets.compare_digest(str(pin).strip(), TEACHER_PIN):
        return {"error": "pin"}
    tt = secrets.token_hex(16)
    with tok_lock:
        teacher_tokens[tt] = time.time()
    return {"token": tt, "classes": school.classes()}


def api_t_overview(tt: str, class_id: int, lang: str = "cat"):
    if not teacher(tt):
        return AUTH
    lang = LANG(lang)
    ids = school.students_of(class_id)
    rep = assistant.class_report(class_id, ids, family_names[lang], lang)
    on = online_sids()
    roster = {s["id"]: s for c in school.classes() if c["id"] == class_id for s in c["students"]}
    for sid, r in rep["students"].items():
        st = roster.get(sid, {})
        r.update(name=st.get("name", "?"), avatar=st.get("avatar", ""), online=sid in on, has_pin=st.get("has_pin", False))
    rep["online"] = len(on & set(ids))
    rep["tests"] = [dict(t, results=len(school.test_results(t["id"]))) for t in school.tests_of_class(class_id)]
    rep["games"] = school.games_of_class(class_id, 10)
    rep["snapshots"] = profiles.snapshots(class_id)
    rep["families"] = sorted(({"family": f, "topic": v["topic"], "words": v["words"], "size": v["size"]}
                              for f, v in family_names[lang].items()), key=lambda x: (x["topic"], x["words"]))
    rep["model"] ={"llm": coach.llm_url() is not None, "busy": working["key"] is not None,
                    "embedding": bank.meta.get("embedding"), "families": len(family_names[lang])}
    return rep


def api_t_student(tt: str, sid: int, lang: str = "cat"):
    if not teacher(tt):
        return AUTH
    lang = LANG(lang)
    st = school.student(sid)
    if not st:
        return {"error": "student"}
    rows = assistant.rows(st["class_id"])
    rep = assistant.student_report(sid, rows, family_names[lang], lang, class_rows=rows)
    recent = []
    for r in [r for r in rows if r["student_id"] == sid][-15:][::-1]:
        p = bank.by_id.get(r["problem_id"])
        if p:
            recent.append({"level": p["level"], "text": bank.view(p, lang)["text"][:110], "correct": r["correct"],
                           "seconds": r["seconds"], "source": r["source"], "hints": r["hints"], "ts": r["ts"]})
    an = assistant.analysis(st["class_id"], school.students_of(st["class_id"]), family_names[lang], lang)
    cells = an["matrix"]["cells"].get(sid, {})
    skills = [dict(f, rel=c["rel"], right=c["right"], n=c["n"]) for f in an["matrix"]["families"] if (c := cells.get(f["family"]))]
    return {"student": st, "report": rep, "recent": recent, "tests": school.sessions_of(sid, 10), "badges": badges(sid),
            "stats": stats(sid), "analysis": an["students"].get(sid), "skills": skills}


def family_coherence():
    """How well the semantic families group the problems: mean bge-m3 cosine between problems of the
    same family against problems of different families (computed once, numpy on the board)."""
    if bank._sims is None:
        return None
    labels = ai_np.array([p["family"] for p in bank.problems])
    same = labels[:, None] == labels[None, :]
    off = ~ai_np.eye(len(labels), dtype=bool)
    return {"within": round(float(bank._sims[same & off].mean()), 3), "between": round(float(bank._sims[~same].mean()), 3),
            "families": int(labels.max() + 1), "problems": len(labels)}


try:
    import numpy as ai_np
    COHERENCE = family_coherence()
except ImportError:
    COHERENCE = None


def translations_meta():
    path = os.path.join(DATA, "explanations_i18n.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)["meta"]


def api_t_analysis(tt: str, class_id: int, lang: str = "cat"):
    """The complete class analysis: skills map, AI teaching groups, question analysis, risk, success by level."""
    if not teacher(tt):
        return AUTH
    lang = LANG(lang)
    an = assistant.analysis(class_id, school.students_of(class_id), family_names[lang], lang)
    roster = {s["id"]: s for c in school.classes() if c["id"] == class_id for s in c["students"]}
    an["roster"] = {sid: {"name": s["name"], "avatar": s["avatar"]} for sid, s in roster.items()}
    return an


def api_t_model(tt: str, class_id: int = 0):
    """Is the AI any good? Evidence for each model, measured on this board's data."""
    if not teacher(tt):
        return AUTH
    hints = profiles._q("SELECT COUNT(*), COALESCE(SUM(json_extract(result, '$.hint') IS NULL), 0) FROM hint_cache", one=True)
    leaks = profiles._q("SELECT COUNT(*), COALESCE(SUM(leaked), 0) FROM hints WHERE rung = 3", one=True)
    timed = profiles._q("SELECT COUNT(*) FROM attempts WHERE seconds > 1 AND source != 'learn'", one=True)[0]
    return {"class": assistant.evaluation(class_id) if class_id else None, "all": assistant.evaluation(),
            "families": COHERENCE, "hints": {"generated": hints[0], "withheld": hints[1], "shown": leaks[0], "leaked_shown": leaks[1]},
            "translations": translations_meta(), "timed_answers": timed,
            "answers": profiles._q("SELECT COUNT(*) FROM attempts", one=True)[0],
            "embedding": bank.meta.get("embedding"), "llm": coach.llm_url() is not None,
            "explanations": sum(1 for p in bank.problems if p.get("explanation")), "translated": bank.translated}


def api_t_class(tt: str, action: str, class_id: int = 0, name: str = ""):
    if not teacher(tt):
        return AUTH
    if action == "create":
        return {"id": school.create_class(name or "Classe"), "classes": school.classes()}
    if action == "rename":
        school.rename_class(class_id, name)
    if action == "delete" and not school.delete_class(class_id):
        return {"error": "not_empty"}
    return {"classes": school.classes()}


def api_t_student_edit(tt: str, action: str, class_id: int = 0, sid: int = 0, name: str = ""):
    """add (returns the new PIN once), pin (a new PIN), rename, delete."""
    if not teacher(tt):
        return AUTH
    if action == "add":
        new_sid, pin = school.add_student(class_id, name)
        if new_sid is None:
            return {"error": "name"}
        return {"sid": new_sid, "pin": pin, "classes": school.classes()}
    if action == "pin":
        return {"sid": sid, "pin": school.set_pin(sid), "classes": school.classes()}
    if action == "rename":
        school.rename_student(sid, name)
    if action == "delete":
        school.delete_student(sid)
    return {"classes": school.classes()}


def api_t_test_create(tt: str, class_id: int, title: str, level: int, n: int = 10, family: int = -1, minutes: int = 0):
    if not teacher(tt):
        return AUTH
    fam = family if family >= 0 else None
    ids = [p["id"] for p in pick_problems(max(0, min(7, level)), max(3, min(20, n)), family=fam)]
    tid = school.create_test(class_id, title, level, len(ids), fam, ids, max(0, minutes))
    return {"id": tid, "tests": school.tests_of_class(class_id)}


def api_t_test(tt: str, test_id: int, action: str = "results", lang: str = "cat"):
    if not teacher(tt):
        return AUTH
    t = school.test(test_id)
    if not t:
        return {"error": "test"}
    if action in ("open", "close"):
        school.set_test_active(test_id, action == "open")
        t = school.test(test_id)
    lang = LANG(lang)
    per_q = []
    for pid in t["problem_ids"]:
        rows = profiles._q("SELECT a.correct FROM attempts a JOIN test_sessions s ON s.student_id = a.student_id"
                           " WHERE a.problem_id = ? AND a.source = 'test' AND s.test_id = ?", (pid, test_id))
        p = bank.by_id[pid]
        per_q.append({"id": pid, "level": p["level"], "text": bank.view(p, lang)["text"][:120],
                      "n": len(rows), "correct": sum(r[0] for r in rows)})
    return {"test": t, "results": school.test_results(test_id), "questions": per_q}


def api_t_snapshot(tt: str, class_id: int, lang: str = "cat"):
    if not teacher(tt):
        return AUTH
    lang = LANG(lang)
    rep = assistant.class_report(class_id, school.students_of(class_id), family_names[lang], lang)
    profiles.save_snapshot(rep["weak"], class_id)
    return {"snapshots": profiles.snapshots(class_id)}


def api_led():
    return last_frame


ROUTES = {
    "/api/info": api_info, "/api/classes": api_classes, "/api/login": api_login, "/api/logout": api_logout,
    "/api/me": api_me, "/api/settings": api_settings, "/api/leaderboard": api_leaderboard,
    "/api/practice": api_practice, "/api/answer": api_answer, "/api/shown": api_shown, "/api/hint": api_hint,
    "/api/hint_status": api_hint_status, "/api/solution": api_solution,
    "/api/test_start": api_test_start, "/api/test_answer": api_test_answer, "/api/test_review": api_test_review,
    "/api/lessons": api_lessons, "/api/lesson": api_lesson, "/api/lesson_done": api_lesson_done,
    "/api/room_create": api_room_create, "/api/room_join": api_room_join, "/api/room_leave": api_room_leave,
    "/api/room_start": api_room_start, "/api/room_state": api_room_state, "/api/room_answer": api_room_answer,
    "/api/room_next": api_room_next,
    "/api/teacher_login": api_teacher_login, "/api/t_overview": api_t_overview, "/api/t_student": api_t_student,
    "/api/t_class": api_t_class, "/api/t_student_edit": api_t_student_edit, "/api/t_test_create": api_t_test_create,
    "/api/t_test": api_t_test, "/api/t_snapshot": api_t_snapshot, "/api/led": api_led,
    "/api/t_analysis": api_t_analysis, "/api/t_model": api_t_model,
}

print(f"Math coach ({'board' if ON_BOARD else 'laptop, development'}): {len(bank.problems)} problems, "
      f"map {bank.meta.get('embedding')}, {len(family_names['eng'])} semantic families, "
      f"{sum(len(c['students']) for c in school.classes())} students in {len(school.classes())} classes, "
      f"model server: {coach.llm_url() or 'unreachable'}", flush=True)
print(f"Teacher PIN: {TEACHER_PIN} ({PIN_FILE})", flush=True)

if __name__ == "__main__" and ON_BOARD:  # App Lab runs this file as a script
    ui = WebUI()
    for path, function in ROUTES.items():
        ui.expose_api("GET", path, function)
    show("ask", 0)
    App.run()
