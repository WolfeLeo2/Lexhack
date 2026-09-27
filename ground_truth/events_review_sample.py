"""Draw a random sample of extracted events (step 6) for blind review -> events_review_sample.csv. Fixed seed.

  uv run python -m ground_truth.events_review_sample

Excludes the answer-key judgments (the prompt was tuned on them), so the review measures precision on unseen data.
"""
import csv
import random
from pathlib import Path

from pipeline.db import connect

HERE = Path(__file__).parent
SEED, N = 7, 40


def main():
    key = {r["judgment_id"] for f in ("events.csv", "negatives.csv") for r in csv.DictReader(open(HERE / f, encoding="utf-8"))}
    with connect() as conn:
        rows = conn.execute("""
            SELECT e.event_id, e.judgment_id, j.title, j.court, a.title || ' s.' || p.number || ' (' || coalesce(p.heading, '') || ')',
                   e.event_type, e.scope, coalesce(e.scope_text, ''), coalesce(e.subsection, ''), e.operative_quote,
                   coalesce(e.source_paragraph, ''), j.raw_path
            FROM citation_events e JOIN judgments j USING (judgment_id) JOIN provisions p USING (provision_id)
            JOIN acts a USING (act_id) WHERE e.method = 'extracted' ORDER BY e.event_id""").fetchall()
    rows = [r for r in rows if r[1] not in key]
    sample = sorted(random.Random(SEED).sample(rows, N))
    cols = ["event_id", "judgment_id", "title", "court", "section", "event_type", "scope", "scope_text", "subsection",
            "operative_quote", "source_paragraph", "raw_path"]
    with open(HERE / "events_review_sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(sample)
    print(f"{N} of {len(rows)} extracted events -> events_review_sample.csv")


if __name__ == "__main__":
    main()
