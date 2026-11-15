#!/usr/bin/env python3
"""Write three variants of data/train.jsonl and data/val.jsonl into data/variants/.

    python3 make_variants.py

  <split>_plain.jsonl      the problems as they are
  <split>_value.jsonl      plus "answer_value": the text of the correct option
                           (the letter when the options are pictures)
  <split>_explained.jsonl  plus "answer_value" and "explanation": how to get the result

Explanations live in data/explanations/*.jsonl, one {"id": ..., "explanation": ...} per line.
One explanation per problem id serves every language of that problem (the maths is the same).
A problem without an explanation yet keeps only "answer_value" in the explained variant.
"""
import glob
import json
import os

DATA = "data"
OUT = os.path.join(DATA, "variants")


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    explanations = {}
    for path in sorted(glob.glob(os.path.join(DATA, "explanations", "*.jsonl"))):
        for row in load_jsonl(path):
            explanations[row["id"]] = row["explanation"].strip()

    os.makedirs(OUT, exist_ok=True)
    for split in ("train", "val"):
        rows = load_jsonl(os.path.join(DATA, f"{split}.jsonl"))
        value_rows, explained_rows = [], []
        for r in rows:
            value = str((r.get("options") or {}).get(r["label"], "")).strip() or r["label"]
            v = {**r, "answer_value": value}
            value_rows.append(v)
            e = dict(v)
            if r["id"] in explanations:
                e["explanation"] = explanations[r["id"]]
            explained_rows.append(e)
        write_jsonl(os.path.join(OUT, f"{split}_plain.jsonl"), rows)
        write_jsonl(os.path.join(OUT, f"{split}_value.jsonl"), value_rows)
        write_jsonl(os.path.join(OUT, f"{split}_explained.jsonl"), explained_rows)
        ids = {r["id"] for r in rows}
        done = sum(1 for i in ids if i in explanations)
        rows_done = sum(1 for r in explained_rows if "explanation" in r)
        print(f"{split}: {len(rows)} rows, {len(ids)} problems, explained {done}/{len(ids)} problems "
              f"({rows_done}/{len(rows)} rows)")


if __name__ == "__main__":
    main()
