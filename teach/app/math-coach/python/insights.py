"""The teacher's AI assistant: what the class and each student need, computed on the board.

Three models, no cloud:
  1. Ability (item response theory, 3PL with a fixed 20% guessing rate, fitted online like Elo):
     P(right) = 0.2 + 0.8 / (1 + exp(-(ability - difficulty))). Every answer moves the student's
     ability and the problem's difficulty a little. A problem's difficulty starts from its
     Kangaroo level and becomes what THIS class finds. A right answer after hints counts in part.
  2. Meaning (bge-m3 embeddings): problems grouped in semantic families; the families a student
     or the class fails, and similar problems to practise (coach.practice_set).
  3. Rules on top of both: alerts (needs help, answers at random, depends on hints, ready to go
     up), shared misconceptions (the same wrong answer chosen by several students), and groups
     of students who struggle with the same family.
  4. Time (a log-normal response-time model): every answer's time is compared with the time
     expected for that problem (the class's typical log-time on it, or on its family when it has
     few answers). A student's speed is how much faster or slower than expected they usually
     are; with accuracy it gives a profile: thoughtful (slow, right), confident (fast, right),
     stuck (slow, wrong), impulsive (fast, wrong). Families and problems that take the longest
     come out of the same model.
The page turns the facts returned here into sentences in the teacher's language.
"""
import math
import statistics
import threading
import time
from collections import Counter, defaultdict

import coach

GUESS = 0.2
SLOPE = 0.7              # ability units per Kangaroo level
LOGIT_HALF = math.log(0.375 / 0.625)  # where 0.2 + 0.8 * sigmoid(x) = 0.5


def b_prior(level):
    return (level - 3.5) * SLOPE


def p_right(ability, difficulty):
    return GUESS + (1 - GUESS) / (1 + math.exp(-(ability - difficulty)))


def est_level(ability):
    """The level at which the student is right half of the time (0-7, one decimal)."""
    return round(min(7.0, max(0.0, (ability - LOGIT_HALF) / SLOPE + 3.5)), 1)


def credit(row):
    """1 for right alone, less with hints (rungs 1-3: 0.75, 0.5, 0.25), 0 after the solution or wrong."""
    if not row["correct"] or row["solution_shown"]:
        return 0.0
    return max(0.25, 1 - 0.25 * row["hints"])


ROW = ("id", "student_id", "problem_id", "level", "correct", "answer", "hints", "solution_shown", "seconds",
       "ts", "points", "lang", "source", "class_id")
MAX_SECONDS = 600  # longer pauses are not thinking time (the student left): capped


def timed(rows):
    return [r for r in rows if r["source"] != "learn" and r["seconds"] and r["seconds"] > 1]


def time_model(bank, rows):
    """Expected log-time per problem, and each answer's residual (log seconds - expected).
    Expected = mean log-time of the problem if it has >= 3 answers, else of its family, else of all."""
    logs = [(r, math.log(min(r["seconds"], MAX_SECONDS))) for r in timed(rows) if r["problem_id"] in bank.by_id]
    if not logs:
        return {}, {}, None
    by_p, by_f = defaultdict(list), defaultdict(list)
    for r, lt in logs:
        by_p[r["problem_id"]].append(lt)
        by_f[bank.by_id[r["problem_id"]]["family"]].append(lt)
    overall = statistics.mean(lt for _r, lt in logs)

    def expected(pid):
        if len(by_p[pid]) >= 3:
            return statistics.mean(by_p[pid])
        f = bank.by_id[pid]["family"]
        return statistics.mean(by_f[f]) if len(by_f[f]) >= 3 else overall

    residual = {r["id"]: lt - expected(r["problem_id"]) for r, lt in logs}
    return residual, {"by_problem": by_p, "by_family": by_f}, overall


def speed_profile(speed, accuracy, n):
    """speed: typical time / expected time (1 = as expected). Needs a few answers."""
    if n < 5 or speed is None:
        return None
    slow, right = speed > 1.25, accuracy >= 0.5
    if right:
        return "thoughtful" if slow else "confident"
    return "stuck" if slow else ("impulsive" if speed < 0.8 else "struggling")


class Insights:
    def __init__(self, bank, profiles):
        self.bank = bank
        self.p = profiles
        self._stamp = None
        self._lock = threading.Lock()
        self.ability, self.difficulty, self.history, self.n_problem, self.n_student = {}, {}, defaultdict(list), Counter(), Counter()
        self.right_student, self.preds = Counter(), []

    def rows(self, class_id=None):
        sql = ("SELECT a.id, a.student_id, a.problem_id, a.level, a.correct, a.answer, a.hints, a.solution_shown,"
               " a.seconds, a.ts, a.points, a.lang, a.source, s.class_id FROM attempts a JOIN students s ON s.id = a.student_id")
        args = ()
        if class_id is not None:
            sql += " WHERE s.class_id = ?"
            args = (class_id,)
        return [dict(zip(ROW, r)) for r in self.p._q(sql + " ORDER BY a.id", args)]

    # ------------------------------------------------------------ model 1: ability and difficulty
    def refresh(self):
        with self._lock:
            self._refresh()

    def _refresh(self):
        """Replays the answers in order. Incremental: only answers newer than the last replay,
        unless some were deleted (a student removed), then everything again."""
        stamp = self.p._q("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM attempts", one=True)
        if stamp == self._stamp:
            return
        last_id = self._stamp[1] if self._stamp else 0
        new = self.p._q("SELECT COUNT(*) FROM attempts WHERE id > ?", (last_id,), one=True)[0]
        if not self._stamp or self._stamp[0] + new != stamp[0]:
            last_id = 0
            self.ability, self.difficulty, self.history, self.n_problem = {}, {}, defaultdict(list), Counter()
            self.n_student, self.right_student, self.preds = Counter(), Counter(), []
        self._stamp = stamp
        ability, difficulty, history, n_p, n_s = self.ability, self.difficulty, self.history, self.n_problem, self.n_student
        sql = ("SELECT a.id, a.student_id, a.problem_id, a.level, a.correct, a.answer, a.hints, a.solution_shown,"
               " a.seconds, a.ts, a.points, a.lang, a.source, s.class_id FROM attempts a JOIN students s ON s.id = a.student_id"
               " WHERE a.id > ? ORDER BY a.id")
        for r in (dict(zip(ROW, x)) for x in self.p._q(sql, (last_id,))):
            if r["source"] == "learn" or r["problem_id"] not in self.bank.by_id:
                continue
            s, pid = r["student_id"], r["problem_id"]
            th = ability.get(s, 0.0)
            b = difficulty.get(pid, b_prior(r["level"]))
            p = p_right(th, b)
            # Prequential evaluation: the prediction is logged BEFORE the model learns from this answer,
            # with two simpler baselines (the problem's level only; the student's own running accuracy).
            if not r["hints"] and not r["solution_shown"]:
                self.preds.append((p, r["correct"], n_s[s], r["class_id"], p_right(0.0, b_prior(r["level"])),
                                   (self.right_student[s] + 1) / (n_s[s] + 2)))
            self.right_student[s] += r["correct"]
            err = credit(r) - p
            ability[s] = th + max(0.25, 1.2 / math.sqrt(1 + n_s[s])) * err
            difficulty[pid] = b - max(0.05, 0.5 / math.sqrt(1 + n_p[pid])) * err
            n_s[s] += 1
            n_p[pid] += 1
            history[s].append((r["ts"], round(ability[s], 3)))

    def student_level(self, sid):
        self.refresh()
        return est_level(self.ability.get(sid, 0.0)) if sid in self.ability else None

    def predicted(self, sid, problem):
        self.refresh()
        return p_right(self.ability.get(sid, 0.0), self.difficulty.get(problem["id"], b_prior(problem["level"])))

    # ------------------------------------------------------------ per student
    def student_report(self, sid, rows, names, lang, class_rows=None, residual=None):
        """Everything the assistant knows about one student, as facts."""
        self.refresh()
        if residual is None:
            residual, _groups, _overall = time_model(self.bank, class_rows if class_rows is not None else rows)
        mine = [r for r in rows if r["student_id"] == sid and r["source"] != "learn"]
        n = len(mine)
        ab = self.ability.get(sid, 0.0)
        hist = self.history.get(sid, [])
        trend = round(hist[-1][1] - hist[max(0, len(hist) - 11)][1], 2) if len(hist) >= 6 else 0.0
        fam = defaultdict(lambda: [0, 0])
        failed_by_fam = defaultdict(list)
        for r in mine:
            p = self.bank.by_id.get(r["problem_id"])
            if not p:
                continue
            fam[p["family"]][0] += r["correct"]
            fam[p["family"]][1] += 1
            if not r["correct"]:
                failed_by_fam[p["family"]].append(p)
        scored = [(f, c) for f, c in fam.items() if c[1] >= 2]
        weakest = min(scored, key=lambda fc: ((fc[1][0] + 1) / (fc[1][1] + 2), -fc[1][1])) if scored else None
        strongest = max(scored, key=lambda fc: ((fc[1][0] + 1) / (fc[1][1] + 2), fc[1][1])) if scored else None
        last10 = mine[-10:]
        acc10 = sum(r["correct"] for r in last10) / len(last10) if last10 else 0
        secs = [min(r["seconds"], MAX_SECONDS) for r in mine[-12:] if r["seconds"]]
        median_s = statistics.median(secs) if secs else None
        res = [residual[r["id"]] for r in mine if r["id"] in residual]
        speed = round(math.exp(statistics.mean(res)), 2) if len(res) >= 3 else None
        acc_all = sum(r["correct"] for r in mine) / n if n else 0
        slow_fam = defaultdict(list)
        for r in mine:
            if r["id"] in residual and r["problem_id"] in self.bank.by_id:
                slow_fam[self.bank.by_id[r["problem_id"]]["family"]].append(residual[r["id"]])
        slowest = max(((f, statistics.mean(v), len(v)) for f, v in slow_fam.items() if len(v) >= 2),
                      key=lambda x: x[1], default=None)
        hints = sum(min(r["hints"], 3) for r in mine) / n if n else 0
        alerts = []
        if n >= 5 and acc10 < 0.3:
            alerts.append({"code": "need_help", "acc": round(acc10, 2)})
        if n >= 6 and median_s is not None and median_s < 12 and acc10 <= 0.3:
            alerts.append({"code": "guessing", "seconds": round(median_s)})
        if n >= 5 and hints >= 1.8:
            alerts.append({"code": "hints", "per_answer": round(hints, 1)})
        if n >= 6 and acc10 >= 0.8:
            alerts.append({"code": "ready_up"})
        if trend >= 0.5:
            alerts.append({"code": "rising", "trend": trend})
        if trend <= -0.5:
            alerts.append({"code": "falling", "trend": trend})
        # shared misconceptions: the same wrong answer as other students on the same problem
        misconceptions = []
        if class_rows is not None:
            wrong = Counter((r["problem_id"], r["answer"]) for r in class_rows if not r["correct"] and r["source"] != "learn")
            seen = set()
            for r in mine:
                key = (r["problem_id"], r["answer"])
                if not r["correct"] and wrong[key] >= 2 and key not in seen:
                    seen.add(key)
                    p = self.bank.by_id[r["problem_id"]]
                    v = self.bank.view(p, lang, with_answer=True)
                    misconceptions.append({"id": p["id"], "level": p["level"], "text": v["text"], "chose": r["answer"],
                                           "chose_value": v["options"].get(r["answer"], ""), "others": wrong[key] - 1,
                                           "label": v["label"], "value": v["value"]})
        practice = []
        if weakest:
            attempted = {r["problem_id"] for r in mine}
            practice = [self.bank.view(p, lang) for p in
                        coach.practice_set(self.bank, weakest[0], failed_by_fam[weakest[0]], attempted, k=3)]

        def fam_fact(fc):
            return {"family": fc[0], "topic": names[fc[0]]["topic"], "words": names[fc[0]]["words"],
                    "ok": fc[1][0], "n": fc[1][1]} if fc else None

        return {"sid": sid, "answers": n, "correct": sum(r["correct"] for r in mine),
                "ability": round(ab, 2), "level": est_level(ab) if n else None, "trend": trend,
                "acc10": round(acc10, 2), "median_seconds": round(median_s) if median_s else None,
                "speed": speed, "profile": speed_profile(speed, acc_all, n),
                "slowest": {"family": slowest[0], "topic": names[slowest[0]]["topic"], "words": names[slowest[0]]["words"],
                            "factor": round(math.exp(slowest[1]), 1)} if slowest and slowest[1] > 0.2 else None,
                "hints_per_answer": round(hints, 1), "weakest": fam_fact(weakest),
                "strongest": fam_fact(strongest) if strongest and strongest != weakest else None,
                "alerts": alerts, "misconceptions": misconceptions[:3], "practice": practice,
                "history": [h[1] for h in hist[-30:]],
                "by_source": dict(Counter(r["source"] for r in mine)),
                "last": mine[-1]["ts"] if mine else None}

    # ------------------------------------------------------------ the class
    def class_report(self, class_id, student_ids, names, lang):
        self.refresh()
        rows = self.rows(class_id)
        scored = [r for r in rows if r["source"] != "learn"]
        residual, tgroups, _overall = time_model(self.bank, rows)
        reports = {sid: self.student_report(sid, rows, names, lang, class_rows=rows, residual=residual) for sid in student_ids}
        # time: the families and problems that take the class longest (median seconds)
        slow_families = []
        for fid, lts in (tgroups or {}).get("by_family", {}).items():
            if len(lts) >= 3:
                slow_families.append({"family": fid, "topic": names[fid]["topic"], "words": names[fid]["words"], "n": len(lts),
                                      "median_s": round(math.exp(statistics.median(lts)))})
        slow_families.sort(key=lambda x: -x["median_s"])
        slow_problems = []
        for pid, lts in (tgroups or {}).get("by_problem", {}).items():
            if len(lts) >= 2:
                p = self.bank.by_id[pid]
                slow_problems.append({"id": pid, "level": p["level"], "n": len(lts), "median_s": round(math.exp(statistics.median(lts))),
                                      "text": self.bank.view(p, lang)["text"][:140], "words": names[p["family"]]["words"]})
        slow_problems.sort(key=lambda x: -x["median_s"])
        times = [min(r["seconds"], MAX_SECONDS) for r in timed(scored)]
        profiles = Counter(rep["profile"] for rep in reports.values() if rep["profile"])
        levels = Counter(int(r["level"]) for r in reports.values() if r["level"] is not None)
        # semantic families the class fails
        fams = defaultdict(lambda: {"n": 0, "wrong": 0, "students": set(), "failers": set(), "failed": Counter(),
                                    "attempted": set()})
        for r in scored:
            p = self.bank.by_id.get(r["problem_id"])
            if not p:
                continue
            f = fams[p["family"]]
            f["n"] += 1
            f["attempted"].add(p["id"])
            f["students"].add(r["student_id"])
            if not r["correct"]:
                f["wrong"] += 1
                f["failers"].add(r["student_id"])
                f["failed"][p["id"]] += 1
        last = self.p.last_snapshot(class_id)
        weak = []
        for fid, f in fams.items():
            failed = [self.bank.by_id[x] for x in f["failed"]]
            example = self.bank.by_id[f["failed"].most_common(1)[0][0]] if f["failed"] else None
            prev = last.get(fid)
            weak.append({"family": fid, "topic": names[fid]["topic"], "words": names[fid]["words"], "n": f["n"],
                         "wrong": f["wrong"], "students": len(f["students"]), "failers": len(f["failers"]),
                         "rate": round(f["wrong"] / f["n"], 3), "score": round((f["wrong"] + 1) / (f["n"] + 2), 3),
                         "prev_rate": round(prev[1] / prev[0], 3) if prev and prev[0] else None,
                         "example": self.bank.view(example, lang, with_answer=True) if example else None,
                         "example_fails": f["failed"].most_common(1)[0][1] if f["failed"] else 0,
                         "practice": [self.bank.view(p, lang) for p in coach.practice_set(self.bank, fid, failed, f["attempted"])]})
        weak.sort(key=lambda a: (a["n"] < 3, -a["score"], -a["wrong"]))
        # most failed questions, with the shared wrong answer
        per = defaultdict(lambda: {"n": 0, "wrong": 0, "answers": Counter(), "who": set()})
        for r in scored:
            d = per[r["problem_id"]]
            d["n"] += 1
            if not r["correct"]:
                d["wrong"] += 1
                d["answers"][r["answer"]] += 1
                d["who"].add(r["student_id"])
        hardest = []
        for pid, d in per.items():
            p = self.bank.by_id.get(pid)
            if not p or not d["wrong"]:
                continue
            v = self.bank.view(p, lang, with_answer=True)
            letter, count = d["answers"].most_common(1)[0]
            hardest.append({"id": pid, "level": p["level"], "text": v["text"], "label": v["label"], "value": v["value"],
                            "n": d["n"], "wrong": d["wrong"], "common_wrong": letter,
                            "common_wrong_value": v["options"].get(letter, ""), "common_wrong_count": count,
                            "topic": names[p["family"]]["topic"], "words": names[p["family"]]["words"]})
        hardest.sort(key=lambda h: (-h["common_wrong_count"], -h["wrong"]))
        # problems this class finds harder (or easier) than their level says
        items = []
        for pid, b in self.difficulty.items():
            if per[pid]["n"] >= 3:
                p = self.bank.by_id[pid]
                items.append({"id": pid, "level": p["level"], "felt_level": round(min(7.5, max(-0.5, b / SLOPE + 3.5)), 1),
                              "n": per[pid]["n"], "text": self.bank.view(p, lang)["text"][:140]})
        harder = sorted([i for i in items if i["felt_level"] - i["level"] >= 1], key=lambda i: i["level"] - i["felt_level"])[:5]
        easier = sorted([i for i in items if i["level"] - i["felt_level"] >= 1], key=lambda i: i["felt_level"] - i["level"])[:5]
        # groups: students whose weakest family is the same
        groups = defaultdict(list)
        for sid, rep in reports.items():
            if rep["weakest"] and rep["weakest"]["ok"] < rep["weakest"]["n"]:
                groups[rep["weakest"]["family"]].append(sid)
        group_list = []
        for fid, sids in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            if len(sids) >= 2:
                failed = [self.bank.by_id[r["problem_id"]] for r in scored
                          if r["student_id"] in sids and not r["correct"] and self.bank.by_id.get(r["problem_id"], {}).get("family") == fid]
                done = {r["problem_id"] for r in scored if r["student_id"] in sids}
                group_list.append({"family": fid, "topic": names[fid]["topic"], "words": names[fid]["words"], "students": sids,
                                   "practice": [self.bank.view(p, lang) for p in coach.practice_set(self.bank, fid, failed, done)]})
        now = time.time()
        days = [0] * 7
        for r in scored:
            age = int((now - r["ts"]) // 86400)
            if 0 <= age < 7:
                days[6 - age] += 1
        return {"students": reports, "levels": dict(levels), "weak": weak[:12], "hardest": hardest[:10],
                "harder": harder, "easier": easier, "groups": group_list[:6], "days": days,
                "slow_families": slow_families[:8], "slow_problems": slow_problems[:6],
                "median_seconds": round(statistics.median(times)) if times else None, "profiles": dict(profiles),
                "answers": len(scored), "correct": sum(r["correct"] for r in scored),
                "today": sum(1 for r in scored if now - r["ts"] < 86400),
                "sources": dict(Counter(r["source"] for r in rows))}

    # ------------------------------------------------------------ is the model any good? (prequential evaluation)
    def evaluation(self, class_id=None, warm=3):
        """Each answer was predicted before the model saw it. Scores the model and two baselines on
        those predictions: AUC (ranking), Brier and log-loss (probabilities), accuracy, calibration."""
        self.refresh()
        preds = [x for x in self.preds if (class_id is None or x[3] == class_id) and x[2] >= warm]
        if len(preds) < 20:
            return {"n": len(preds), "enough": False}
        y = [x[1] for x in preds]
        out = {"n": len(preds), "enough": True, "warm": warm, "base_rate": round(sum(y) / len(y), 3)}
        for name, k in (("model", 0), ("level_only", 4), ("student_accuracy", 5)):
            p = [x[k] for x in preds]
            out[name] = {"auc": round(auc(p, y), 3), "brier": round(sum((a - b) ** 2 for a, b in zip(p, y)) / len(y), 4),
                         "logloss": round(-sum(math.log(min(max(a if b else 1 - a, 1e-6), 1)) for a, b in zip(p, y)) / len(y), 4),
                         "accuracy": round(sum((a >= 0.5) == bool(b) for a, b in zip(p, y)) / len(y), 3)}
        bins = defaultdict(list)
        for x in preds:
            bins[min(9, int(x[0] * 10))].append(x)
        out["calibration"] = [{"bin": b, "n": len(v), "predicted": round(sum(x[0] for x in v) / len(v), 3),
                               "observed": round(sum(x[1] for x in v) / len(v), 3)} for b, v in sorted(bins.items()) if len(v) >= 5]
        out["ece"] = round(sum(c["n"] * abs(c["predicted"] - c["observed"]) for c in out["calibration"]) / len(preds), 4)
        return out

    # ------------------------------------------------------------ the complete class analysis
    def analysis(self, class_id, student_ids, names, lang):
        """Skills map (difficulty-adjusted, per semantic family), AI teaching groups (k-means on the
        skills profiles, k by silhouette), question analysis (discrimination, distractors), success
        by level, and an explainable risk index."""
        self.refresh()
        rows = [r for r in self.rows(class_id) if r["source"] != "learn" and r["problem_id"] in self.bank.by_id]
        theta = {s: self.ability.get(s, 0.0) for s in student_ids}
        fam_of = {pid: self.bank.by_id[pid]["family"] for pid in {r["problem_id"] for r in rows}}

        # 1. skills map: observed minus expected right answers, per student and family, shrunk toward 0
        cell = defaultdict(lambda: [0, 0.0, 0])  # (student, family) -> [right, expected, n]
        for r in rows:
            p = p_right(theta.get(r["student_id"], 0.0), self.difficulty.get(r["problem_id"], b_prior(r["level"])))
            c = cell[(r["student_id"], fam_of[r["problem_id"]])]
            c[0] += r["correct"]
            c[1] += p
            c[2] += 1
        fam_n = Counter()
        for (s, f), c in cell.items():
            fam_n[f] += c[2]
        families = [f for f, n in fam_n.most_common() if n >= 4][:14]
        SHRINK = 2
        mastery = {s: {f: round((cell[(s, f)][0] - cell[(s, f)][1]) / (cell[(s, f)][2] + SHRINK), 3)
                       for f in families if cell.get((s, f), [0, 0, 0])[2]} for s in student_ids}
        fam_rel = {f: round(sum(cell[(s, f)][0] - cell[(s, f)][1] for s in student_ids if (s, f) in cell)
                            / (fam_n[f] + SHRINK), 3) for f in families}
        families.sort(key=lambda f: fam_rel[f])
        matrix = {"families": [{"family": f, "topic": names[f]["topic"], "words": names[f]["words"], "n": fam_n[f],
                                "relative": fam_rel[f]} for f in families],
                  "cells": {s: {f: {"rel": mastery[s][f], "n": cell[(s, f)][2], "right": cell[(s, f)][0]}
                                for f in mastery[s]} for s in student_ids}}

        # 2. AI teaching groups: k-means on the skills vectors of students with enough answers
        n_ans = Counter(r["student_id"] for r in rows)
        active = [s for s in student_ids if n_ans[s] >= 6]
        groups = {"k": 0, "silhouette": None, "groups": []}
        if len(active) >= 4 and len(families) >= 2:
            vecs = {s: [mastery[s].get(f, 0.0) for f in families] for s in active}
            best = None
            for k in range(2, min(4, len(active) - 1) + 1):
                lab = kmeans([vecs[s] for s in active], k)
                sil = silhouette([vecs[s] for s in active], lab)
                if best is None or sil > best[0]:
                    best = (sil, k, lab)
            sil, k, lab = best
            out = []
            for g in range(k):
                members = [s for s, l in zip(active, lab) if l == g]
                if not members:
                    continue
                centre = [sum(vecs[s][i] for s in members) / len(members) for i in range(len(families))]
                order = sorted(range(len(families)), key=lambda i: centre[i])
                fam = lambda i: {"family": families[i], "topic": names[families[i]]["topic"], "words": names[families[i]]["words"],  # noqa: E731
                                 "rel": round(centre[i], 3)}
                lv = [est_level(theta[s]) for s in members]
                out.append({"students": members, "level": round(sum(lv) / len(lv), 1),
                            "needs": [fam(i) for i in order[:2] if centre[i] < -0.02],
                            "strengths": [fam(i) for i in order[::-1][:2] if centre[i] > 0.02]})
            out.sort(key=lambda g: g["level"])
            groups = {"k": k, "silhouette": round(sil, 3), "groups": out, "students_used": len(active)}

        # 3. question analysis: discrimination (point-biserial with ability) and distractors
        per = defaultdict(list)
        for r in rows:
            per[r["problem_id"]].append(r)
        items = []
        for pid, rs in per.items():
            if len(rs) < 4:
                continue
            ys = [r["correct"] for r in rs]
            ths = [theta.get(r["student_id"], 0.0) for r in rs]
            disc = pearson(ys, ths) if len(rs) >= 5 else None  # with 4 answers a correlation is noise
            right_th = [t for t, y in zip(ths, ys) if y]
            distract = []
            for letter, k in Counter(r["answer"] for r in rs if not r["correct"]).most_common():
                if k >= 2:
                    pick_th = [theta.get(r["student_id"], 0.0) for r in rs if r["answer"] == letter and not r["correct"]]
                    distract.append({"letter": letter, "n": k, "level": est_level(sum(pick_th) / len(pick_th)),
                                     "stronger_than_right": bool(right_th) and sum(pick_th) / len(pick_th) > sum(right_th) / len(right_th)})
            p = self.bank.by_id[pid]
            v = self.bank.view(p, lang, with_answer=True)
            flags = []
            if disc is not None and disc < -0.1 and len(rs) >= 5:
                flags.append("negative")
            if any(d["stronger_than_right"] for d in distract) and len(rs) >= 5:
                flags.append("trap")
            if sum(ys) == len(ys) and len(rs) >= 5:
                flags.append("too_easy")
            if sum(ys) == 0 and len(rs) >= 5:
                flags.append("too_hard")
            items.append({"id": pid, "level": p["level"], "n": len(rs), "p_value": round(sum(ys) / len(ys), 2),
                          "discrimination": None if disc is None else round(disc, 2), "distractors": distract, "flags": flags,
                          "text": v["text"][:160], "label": v["label"], "value": v["value"],
                          "options": v["options"], "topic": names[p["family"]]["topic"]})
        good = [i for i in items if i["discrimination"] is not None]
        items_summary = {"analysed": len(items), "mean_discrimination": round(sum(i["discrimination"] for i in good) / len(good), 2) if good else None,
                         "flagged": sum(1 for i in items if i["flags"])}
        items.sort(key=lambda i: (not i["flags"], i["discrimination"] if i["discrimination"] is not None else 9))

        # 4. success by level and 5. explainable risk index
        students = {}
        now = time.time()
        residual, _groups, _overall = time_model(self.bank, rows)
        reports = {s: self.student_report(s, rows, names, lang, residual=residual) for s in student_ids}
        for s in student_ids:
            rep = reports[s]
            curve = [round(p_right(theta[s], b_prior(lv)), 2) for lv in range(8)]
            factors = []
            codes = {a["code"] for a in rep["alerts"]}
            if "need_help" in codes:
                factors.append({"code": "low_accuracy", "points": 35, "value": rep["acc10"]})
            if "falling" in codes:
                factors.append({"code": "falling", "points": 25, "value": rep["trend"]})
            if "guessing" in codes:
                factors.append({"code": "guessing", "points": 20, "value": rep["median_seconds"]})
            if "hints" in codes:
                factors.append({"code": "hints", "points": 10, "value": rep["hints_per_answer"]})
            if rep["profile"] == "stuck":
                factors.append({"code": "stuck", "points": 10, "value": rep["speed"]})
            if rep["last"] and now - rep["last"] > 3 * 86400:
                factors.append({"code": "inactive", "points": 15, "value": int((now - rep["last"]) // 86400)})
            if not rep["answers"]:
                factors.append({"code": "never", "points": 20, "value": 0})
            students[s] = {"curve": curve, "risk": min(100, sum(f["points"] for f in factors)), "factors": factors,
                           "level": rep["level"], "answers": rep["answers"]}
        return {"matrix": matrix, "groups": groups, "items": items[:40], "items_summary": items_summary, "students": students}


def auc(scores, labels):
    """Area under the ROC curve by ranks (ties get the average rank)."""
    pairs = sorted(zip(scores, labels))
    pos = sum(labels)
    neg = len(labels) - pos
    if not pos or not neg:
        return 0.5
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        rank_sum += avg * sum(1 for k in range(i, j + 1) if pairs[k][1])
        i = j + 1
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def kmeans(vectors, k, iters=50, seed=0):
    """Plain k-means (k-means++ start, fixed seed: the same class gives the same groups)."""
    import random
    rng = random.Random(seed)
    d2 = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b))  # noqa: E731
    centres = [vectors[rng.randrange(len(vectors))]]
    while len(centres) < k:
        dist = [min(d2(v, c) for c in centres) for v in vectors]
        total = sum(dist)
        if not total:
            centres.append(vectors[rng.randrange(len(vectors))])
            continue
        r, acc = rng.random() * total, 0.0
        for v, d in zip(vectors, dist):
            acc += d
            if acc >= r:
                centres.append(v)
                break
    labels = [0] * len(vectors)
    for _ in range(iters):
        new = [min(range(k), key=lambda c: d2(v, centres[c])) for v in vectors]
        if new == labels and _:
            break
        labels = new
        for c in range(k):
            members = [v for v, l in zip(vectors, labels) if l == c]
            if members:
                centres[c] = [sum(col) / len(members) for col in zip(*members)]
    return labels


def silhouette(vectors, labels):
    """Mean silhouette (-1..1): how much closer each student is to their own group than to the next one."""
    dist = lambda a, b: math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))  # noqa: E731
    scores = []
    for i, v in enumerate(vectors):
        own = [dist(v, w) for j, w in enumerate(vectors) if labels[j] == labels[i] and j != i]
        if not own:
            scores.append(0.0)
            continue
        a = sum(own) / len(own)
        b = min((sum(dist(v, w) for j, w in enumerate(vectors) if labels[j] == c) /
                 sum(1 for j in range(len(vectors)) if labels[j] == c)) for c in set(labels) if c != labels[i])
        scores.append((b - a) / max(a, b) if max(a, b) else 0.0)
    return sum(scores) / len(scores)
