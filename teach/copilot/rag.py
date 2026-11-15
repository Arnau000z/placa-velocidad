"""A retrieval index in SQLite: one solved M3Kang problem per row."""
import json
import sqlite3
from array import array

from .embed import embed
from .llm import format_problem

SCHEMA = """
CREATE TABLE IF NOT EXISTS problems (
    key TEXT PRIMARY KEY,   -- id|language
    problem TEXT NOT NULL,  -- the full problem as JSON
    vec BLOB NOT NULL       -- float32 vector
)"""


DOC_FORMATS = ("plain", "value", "explained")


def doc_text(problem, doc_format="plain"):
    """The text that gets embedded for a stored (solved) problem.

    plain      the problem and its options, as the model sees it
    value      plus "Answer: <the correct option's text>" (the letter if the options are pictures)
    explained  plus the answer and "Solution: <explanation>", when the problem has one
    Search queries are always plain: an unsolved problem has no answer to add.
    """
    text = format_problem(problem)
    if doc_format == "plain":
        return text
    label = problem.get("label", "")
    value = str((problem.get("options") or {}).get(label, "")).strip()
    text += f"\nAnswer: {value or label}"
    if doc_format == "explained" and problem.get("explanation"):
        text += f"\nSolution: {problem['explanation']}"
    return text


def build(db_path, problems, batch=16, doc_format="plain"):
    db = sqlite3.connect(db_path)
    db.execute(SCHEMA)
    for i in range(0, len(problems), batch):
        chunk = problems[i:i + batch]
        vectors = embed([doc_text(p, doc_format) for p in chunk])
        db.executemany("INSERT OR REPLACE INTO problems VALUES (?, ?, ?)", [
            (f"{p['id']}|{p['language']}", json.dumps(p, ensure_ascii=False), array("f", v).tobytes())
            for p, v in zip(chunk, vectors)])
        db.commit()
        yield min(i + batch, len(problems))
    db.close()


class Index:
    """Loads every vector into memory once, so each search is a plain loop."""

    def __init__(self, db_path):
        db = sqlite3.connect(db_path)
        self.rows = []
        for key, problem, blob in db.execute("SELECT key, problem, vec FROM problems"):
            vec = array("f")
            vec.frombytes(blob)
            self.rows.append((key, json.loads(problem), vec))
        db.close()

    def search(self, problem, k=1, exclude_id=None):
        """Return up to k (score, problem) pairs, most similar first.

        exclude_id skips the same problem in other languages, so validation
        never retrieves its own translation.
        """
        query = embed([format_problem(problem)], query=True)[0]
        scored = []
        for _key, stored, vec in self.rows:
            if exclude_id and stored["id"] == exclude_id:
                continue
            scored.append((sum(a * b for a, b in zip(query, vec)), stored))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[:k]
