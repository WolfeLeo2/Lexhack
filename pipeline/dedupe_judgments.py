"""Mark judgments that Kenya Law published more than once (e.g. Kahinga, Petition 618 of 2010, under three IDs).

  uv run python -m pipeline.dedupe_judgments [--dry-run]

Candidates share court, case number and decision date; they are marked only if their texts also match (word 5-gram
overlap >= MIN_OVERLAP), because some case numbers are garbage ('? 40 of ??'). One copy stays canonical (the longest
text); the others get judgments.duplicate_of = that copy. Nothing is deleted: the API skips events from duplicates and
counts citations once per real judgment. Idempotent; re-run after loading new judgments.
"""
import argparse
import json
import re

from crawler.config import data_dir

from .db import connect

MIN_OVERLAP = 0.7   # copies score >= 0.78, different rulings under one number <= 0.52 (2026-09-27)


def shingles(path):
    try:
        text = json.loads((data_dir() / path).read_text(encoding="utf-8"))["text"] or ""
    except (OSError, ValueError, TypeError):
        return set(), 0
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i:i + 5]) for i in range(len(words) - 4)}, len(words)


def overlap(a, b):
    return len(a & b) / max(1, min(len(a), len(b)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        conn.execute("SET lock_timeout = '20s'")   # the table is shared: never queue forever behind another session
        conn.execute("ALTER TABLE judgments ADD COLUMN IF NOT EXISTS duplicate_of TEXT REFERENCES judgments(judgment_id)")
        conn.commit()
        groups = conn.execute("""
            SELECT array_agg(judgment_id ORDER BY judgment_id), array_agg(coalesce(raw_path, '') ORDER BY judgment_id)
            FROM judgments WHERE coalesce(case_number, '') <> '' AND decision_date IS NOT NULL
            GROUP BY court, lower(regexp_replace(case_number, '\\s+', ' ', 'g')), decision_date
            HAVING count(*) > 1""").fetchall()
        marks, kept_apart = {}, 0
        for ids, paths in groups:
            docs = {j: shingles(p) for j, p in zip(ids, paths) if p}
            canon = max(docs, key=lambda j: (docs[j][1], j), default=None)
            for j in ids:
                if j == canon:
                    continue
                if j in docs and canon and overlap(docs[j][0], docs[canon][0]) >= MIN_OVERLAP:
                    marks[j] = canon
                else:
                    kept_apart += 1   # same metadata, different text: two real judgments
        print(f"{len(groups)} candidate groups: {len(marks)} duplicates marked, {kept_apart} kept apart (text differs)")
        if args.dry_run:
            return
        conn.execute("UPDATE judgments SET duplicate_of = NULL WHERE duplicate_of IS NOT NULL AND NOT (judgment_id = ANY(%s))",
                     (list(marks),))
        conn.cursor().executemany("UPDATE judgments SET duplicate_of = %s WHERE judgment_id = %s",
                                  [(c, j) for j, c in marks.items()])
        conn.commit()


if __name__ == "__main__":
    main()
