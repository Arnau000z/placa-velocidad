"""The school: classes, students with a PIN, tests set by the teacher, test sessions, games
and the lessons each student has done. SQLite, standard library only.

Students log in by picking their name in their class and typing a 4-digit PIN. PINs are
stored as PBKDF2 hashes with a salt, never in clear; after 5 wrong tries the student is
locked for 60 seconds.
"""
import hashlib
import json
import secrets
import time

AVATARS = ["🦊", "🐼", "🐨", "🦁", "🐯", "🐸", "🐵", "🦉", "🐧", "🐙", "🦄", "🐢", "🐬", "🐝", "🦋", "🐞", "🐳",
           "🦒", "🦓", "🐘", "🦔", "🐿️", "🦜", "🐹"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tests (id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, title TEXT NOT NULL,
    level INTEGER NOT NULL, n INTEGER NOT NULL, family INTEGER, problem_ids TEXT NOT NULL, minutes INTEGER NOT NULL,
    created REAL NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS test_sessions (id INTEGER PRIMARY KEY, test_id INTEGER, student_id INTEGER NOT NULL,
    level INTEGER NOT NULL, problem_ids TEXT NOT NULL, answers TEXT NOT NULL DEFAULT '[]', started REAL NOT NULL,
    finished REAL, correct INTEGER NOT NULL DEFAULT 0, points INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY, class_id INTEGER, code TEXT NOT NULL, created REAL NOT NULL,
    finished REAL NOT NULL, rounds INTEGER NOT NULL, players TEXT NOT NULL, winner INTEGER);
CREATE TABLE IF NOT EXISTS learn_done (student_id INTEGER NOT NULL, problem_id TEXT NOT NULL, ts REAL NOT NULL,
    guessed_right INTEGER NOT NULL, PRIMARY KEY (student_id, problem_id));
"""


def _hash(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", str(pin).encode(), bytes.fromhex(salt), 20000).hex()


class School:
    def __init__(self, profiles):
        self.p = profiles
        self.db = profiles.db
        self.lock = profiles.lock
        self.fails = {}  # sid -> (count, locked_until)
        with self.lock:
            self.db.executescript(SCHEMA)
            cols = [r[1] for r in self.db.execute("PRAGMA table_info(students)")]
            if "class_id" not in cols:  # students from before classes: move them to a first class
                if not self.db.execute("SELECT COUNT(*) FROM classes").fetchone()[0]:
                    self.db.execute("INSERT INTO classes (name, created) VALUES ('Classe 1', ?)", (time.time(),))
                cid = self.db.execute("SELECT MIN(id) FROM classes").fetchone()[0]
                self.db.executescript("""
                    CREATE TABLE students_new (id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, name TEXT NOT NULL,
                        lang TEXT NOT NULL DEFAULT 'cat', created REAL NOT NULL, pin_hash TEXT, pin_salt TEXT,
                        avatar TEXT NOT NULL DEFAULT '🦘', UNIQUE (class_id, name));""")
                rows = self.db.execute("SELECT id, name, lang, created FROM students").fetchall()
                self.db.executemany("INSERT INTO students_new (id, class_id, name, lang, created, avatar) VALUES (?, ?, ?, ?, ?, ?)",
                                    [(i, cid, n, l, c, AVATARS[i % len(AVATARS)]) for i, n, l, c in rows])
                self.db.executescript("DROP TABLE students; ALTER TABLE students_new RENAME TO students;")
            self.db.commit()

    def _q(self, sql, args=(), one=False):
        return self.p._q(sql, args, one)

    # ------------------------------------------------------------ classes
    def classes(self):
        out = []
        for cid, name in self._q("SELECT id, name FROM classes ORDER BY name"):
            out.append({"id": cid, "name": name, "students": [
                {"id": sid, "name": n, "avatar": av, "has_pin": bool(h)} for sid, n, av, h in
                self._q("SELECT id, name, avatar, pin_hash FROM students WHERE class_id = ? ORDER BY name", (cid,))]})
        return out

    def create_class(self, name):
        self._q("INSERT INTO classes (name, created) VALUES (?, ?)", (name.strip()[:40] or "Classe", time.time()))
        return self._q("SELECT MAX(id) FROM classes", one=True)[0]

    def rename_class(self, cid, name):
        self._q("UPDATE classes SET name = ? WHERE id = ?", (name.strip()[:40], cid))

    def delete_class(self, cid):
        if self._q("SELECT COUNT(*) FROM students WHERE class_id = ?", (cid,), one=True)[0]:
            return False
        self._q("DELETE FROM classes WHERE id = ?", (cid,))
        return True

    # ------------------------------------------------------------ students
    def add_student(self, cid, name, lang="cat"):
        name = " ".join(name.split())[:24]
        if not name or self._q("SELECT 1 FROM students WHERE class_id = ? AND name = ?", (cid, name), one=True):
            return None, None
        self._q("INSERT INTO students (class_id, name, lang, created, avatar) VALUES (?, ?, ?, ?, ?)",
                (cid, name, lang, time.time(), secrets.choice(AVATARS)))
        sid = self._q("SELECT id FROM students WHERE class_id = ? AND name = ?", (cid, name), one=True)[0]
        return sid, self.set_pin(sid)

    def set_pin(self, sid, pin=None):
        pin = pin if pin is not None else f"{secrets.randbelow(10000):04d}"
        salt = secrets.token_hex(8)
        self._q("UPDATE students SET pin_hash = ?, pin_salt = ? WHERE id = ?", (_hash(pin, salt), salt, sid))
        return pin

    def check_pin(self, sid, pin):
        """(ok, seconds_locked)."""
        count, until = self.fails.get(sid, (0, 0))
        if time.time() < until:
            return False, round(until - time.time())
        row = self._q("SELECT pin_hash, pin_salt FROM students WHERE id = ?", (sid,), one=True)
        if not row or not row[0]:
            return False, 0
        if secrets.compare_digest(_hash(pin, row[1]), row[0]):
            self.fails.pop(sid, None)
            return True, 0
        count += 1
        self.fails[sid] = (0, time.time() + 60) if count >= 5 else (count, 0)
        return False, 60 if count >= 5 else 0

    def student(self, sid):
        row = self._q("SELECT id, class_id, name, lang, avatar FROM students WHERE id = ?", (sid,), one=True)
        return dict(zip(("id", "class_id", "name", "lang", "avatar"), row)) if row else None

    def set_avatar(self, sid, avatar):
        if avatar in AVATARS:
            self._q("UPDATE students SET avatar = ? WHERE id = ?", (avatar, sid))

    def set_lang(self, sid, lang):
        self._q("UPDATE students SET lang = ? WHERE id = ?", (lang, sid))

    def rename_student(self, sid, name):
        self._q("UPDATE students SET name = ? WHERE id = ?", (" ".join(name.split())[:24], sid))

    def delete_student(self, sid):
        for table in ("attempts", "hints", "shown_solved", "state", "test_sessions", "learn_done"):
            self._q(f"DELETE FROM {table} WHERE student_id = ?", (sid,))
        self._q("DELETE FROM students WHERE id = ?", (sid,))

    def students_of(self, cid):
        return [r[0] for r in self._q("SELECT id FROM students WHERE class_id = ?", (cid,))]

    # ------------------------------------------------------------ tests
    def create_test(self, cid, title, level, n, family, problem_ids, minutes):
        self._q("INSERT INTO tests (class_id, title, level, n, family, problem_ids, minutes, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, title.strip()[:60] or "Prova", level, n, family, json.dumps(problem_ids), minutes, time.time()))
        return self._q("SELECT MAX(id) FROM tests", one=True)[0]

    def tests_of_class(self, cid, active_only=False):
        rows = self._q("SELECT id, title, level, n, family, minutes, created, active FROM tests WHERE class_id = ?"
                       + (" AND active = 1" if active_only else "") + " ORDER BY created DESC", (cid,))
        return [dict(zip(("id", "title", "level", "n", "family", "minutes", "created", "active"), r)) for r in rows]

    def test(self, tid):
        row = self._q("SELECT id, class_id, title, level, n, family, problem_ids, minutes, active FROM tests WHERE id = ?", (tid,), one=True)
        if not row:
            return None
        d = dict(zip(("id", "class_id", "title", "level", "n", "family", "problem_ids", "minutes", "active"), row))
        d["problem_ids"] = json.loads(d["problem_ids"])
        return d

    def set_test_active(self, tid, active):
        self._q("UPDATE tests SET active = ? WHERE id = ?", (int(active), tid))

    def new_session(self, sid, test_id, level, problem_ids):
        self._q("INSERT INTO test_sessions (test_id, student_id, level, problem_ids, started) VALUES (?, ?, ?, ?, ?)",
                (test_id, sid, level, json.dumps(problem_ids), time.time()))
        return self._q("SELECT MAX(id) FROM test_sessions WHERE student_id = ?", (sid,), one=True)[0]

    def session(self, sess_id):
        row = self._q("SELECT id, test_id, student_id, level, problem_ids, answers, started, finished, correct, points"
                      " FROM test_sessions WHERE id = ?", (sess_id,), one=True)
        if not row:
            return None
        d = dict(zip(("id", "test_id", "student_id", "level", "problem_ids", "answers", "started", "finished", "correct", "points"), row))
        d["problem_ids"], d["answers"] = json.loads(d["problem_ids"]), json.loads(d["answers"])
        return d

    def save_session(self, s):
        self._q("UPDATE test_sessions SET answers = ?, finished = ?, correct = ?, points = ? WHERE id = ?",
                (json.dumps(s["answers"]), s["finished"], s["correct"], s["points"], s["id"]))

    def sessions_of(self, sid, limit=20):
        rows = self._q("SELECT id, test_id, level, problem_ids, correct, points, started, finished FROM test_sessions"
                       " WHERE student_id = ? AND finished IS NOT NULL ORDER BY id DESC LIMIT ?", (sid, limit))
        return [{"id": r[0], "test_id": r[1], "level": r[2], "n": len(json.loads(r[3])), "correct": r[4], "points": r[5],
                 "started": r[6], "finished": r[7]} for r in rows]

    def done_tests(self, sid):
        return {r[0] for r in self._q("SELECT DISTINCT test_id FROM test_sessions WHERE student_id = ? AND finished IS NOT NULL"
                                      " AND test_id IS NOT NULL", (sid,))}

    def test_results(self, tid):
        rows = self._q("""SELECT s.name, s.avatar, t.student_id, t.correct, t.points, t.started, t.finished, t.problem_ids
                          FROM test_sessions t JOIN students s ON s.id = t.student_id
                          WHERE t.test_id = ? AND t.finished IS NOT NULL ORDER BY t.correct DESC, t.finished - t.started""", (tid,))
        return [{"name": r[0], "avatar": r[1], "sid": r[2], "correct": r[3], "points": r[4],
                 "minutes": round((r[6] - r[5]) / 60, 1), "n": len(json.loads(r[7]))} for r in rows]

    # ------------------------------------------------------------ games
    def save_game(self, cid, code, created, rounds, players, winner):
        self._q("INSERT INTO games (class_id, code, created, finished, rounds, players, winner) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, code, created, time.time(), rounds, json.dumps(players, ensure_ascii=False), winner))

    def games_of_class(self, cid, limit=20):
        rows = self._q("SELECT id, code, created, rounds, players, winner FROM games WHERE class_id = ? ORDER BY id DESC LIMIT ?",
                       (cid, limit))
        return [{"id": r[0], "code": r[1], "created": r[2], "rounds": r[3], "players": json.loads(r[4]), "winner": r[5]}
                for r in rows]

    def wins(self, sid):
        return self._q("SELECT COUNT(*) FROM games WHERE winner = ?", (sid,), one=True)[0]

    # ------------------------------------------------------------ lessons
    def lesson_done(self, sid, pid, guessed_right):
        self._q("INSERT OR REPLACE INTO learn_done VALUES (?, ?, ?, ?)", (sid, pid, time.time(), int(guessed_right)))

    def lessons_done(self, sid):
        return {r[0]: bool(r[1]) for r in self._q("SELECT problem_id, guessed_right FROM learn_done WHERE student_id = ?", (sid,))}
