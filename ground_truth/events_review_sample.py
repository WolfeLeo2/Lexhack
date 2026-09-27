"""Draw a random sample of extracted events (step 6) for blind review -> events_review_sample.csv. Fixed seed.

  uv run python -m ground_truth.events_review_sample            # round 1 (seed 7): prompt v4
  uv run python -m ground_truth.events_review_sample --round 2  # round 2 (seed 11): fresh judgments, prompt v5
  uv run python -m ground_truth.events_review_sample --round 3  # round 3 (seed 13): fresh judgments, prompt v6

Excludes the answer-key judgments (the prompt was tuned on them), so the review measures precision on unseen data.
"""
import argparse
import csv
import random
from pathlib import Path

from pipeline.db import connect

HERE = Path(__file__).parent
N = 40
ROUNDS = {1: ("", 7), 2: ("_r2", 11), 3: ("_r3", 13)}   # round -> (file suffix, seed); round N = prompt v(N+3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=1, choices=ROUNDS)
    rnd = ap.parse_args().round
    suffix, seed = ROUNDS[rnd]
    key = {r["judgment_id"] for f in ("events.csv", "negatives.csv") for r in csv.DictReader(open(HERE / f, encoding="utf-8"))}
    for earlier in range(1, rnd):   # later rounds never reuse a judgment an earlier round reviewed
        key |= {r["judgment_id"] for r in csv.DictReader(open(HERE / f"events_review_sample{ROUNDS[earlier][0]}.csv",
                                                               encoding="utf-8"))}
    with connect() as conn:
        rows = conn.execute("""
            SELECT e.event_id, e.judgment_id, j.title, j.court, a.title || ' s.' || p.number || ' (' || coalesce(p.heading, '') || ')',
                   e.event_type, e.scope, coalesce(e.scope_text, ''), coalesce(e.subsection, ''), e.operative_quote,
                   coalesce(e.source_paragraph, ''), j.raw_path
            FROM citation_events e JOIN judgments j USING (judgment_id) JOIN provisions p USING (provision_id)
            JOIN acts a USING (act_id) WHERE e.method = 'extracted' ORDER BY e.event_id""").fetchall()
    rows = [r for r in rows if r[1] not in key]
    sample = sorted(random.Random(seed).sample(rows, min(N, len(rows))))
    cols = ["event_id", "judgment_id", "title", "court", "section", "event_type", "scope", "scope_text", "subsection",
            "operative_quote", "source_paragraph", "raw_path"]
    with open(HERE / f"events_review_sample{suffix}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(sample)
    print(f"{len(sample)} of {len(rows)} extracted events -> events_review_sample{suffix}.csv")


if __name__ == "__main__":
    main()
