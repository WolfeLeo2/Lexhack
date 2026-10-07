"""Later-appeal pass: was a judgment behind a checked ruling later appealed, reversed or upheld? Reviewer agents search
the web (pipeline/appeal_brief.md); this script only exports the cases and reports what they found. Nothing here
writes to the database: an appeal found is a lead to fetch and classify, not a status change.

  uv run python -m pipeline.appeal_check export     # judgments behind checked court rulings -> batch_NN.json
  uv run python -m pipeline.appeal_check report     # findings, and whether each appellate judgment is in our collection

Files: $LEXHACK_DATA/review/appeals/batch_NN.json (cases), findings/batch_NN.json (written by the reviewers).
"""
import json
import re
import sys

from crawler.config import data_dir

from .db import connect

BATCH = 10


def root():
    r = data_dir() / "review" / "appeals"
    (r / "findings").mkdir(parents=True, exist_ok=True)
    return r


def export():
    with connect() as conn:
        rows = conn.execute("""
            SELECT j.judgment_id, j.title, j.court, j.case_number, j.neutral_citation, j.decision_date::text, j.source_url,
                   array_agg(DISTINCT a.title || ' s.' || p.number || ': ' || e.event_type)
            FROM citation_events e JOIN judgments j USING (judgment_id) JOIN provisions p USING (provision_id)
            JOIN acts a USING (act_id)
            WHERE e.verified AND e.event_type NOT IN ('amended_by_statute', 'repealed_by_statute')
              AND j.duplicate_of IS NULL
            GROUP BY 1, 2, 3, 4, 5, 6, 7 ORDER BY array_position(ARRAY['High Court', 'Court of Appeal', 'Supreme Court'],
                     j.court), j.decision_date""").fetchall()
    keys = ["judgment_id", "title", "court", "case_number", "neutral_citation", "decision_date", "url", "rulings"]
    cases = [dict(zip(keys, r)) for r in rows]
    for n in range(0, len(cases), BATCH):
        (root() / f"batch_{n // BATCH:02d}.json").write_text(json.dumps(cases[n:n + BATCH], indent=1), encoding="utf-8")
    print(f"{len(cases)} judgments in {-(-len(cases) // BATCH)} batches -> {root()}")


def report():
    found = [f for p in sorted((root() / "findings").glob("*.json")) for f in json.loads(p.read_text(encoding="utf-8"))]
    cases = {c["judgment_id"]: c for p in sorted(root().glob("batch_*.json")) for c in json.loads(p.read_text(encoding="utf-8"))}
    with connect() as conn:
        held = {r[0]: r[1] for r in conn.execute("SELECT neutral_citation, judgment_id FROM judgments WHERE neutral_citation IS NOT NULL")}
    counts = {}
    for f in found:
        counts[f["later_history"]] = counts.get(f["later_history"], 0) + 1
        if f["later_history"] == "none_found":
            continue
        cite = re.sub(r"\s+", " ", f.get("appellate_citation") or "").strip()
        ours = held.get(cite)
        c = cases.get(f["judgment_id"], {})
        print(f"{f['later_history']:<22} {c.get('title', f['judgment_id'])[:70]}\n"
              f"    -> {f.get('appellate_case') or '?'} {cite} ({f.get('confidence')}); "
              f"{'IN OUR COLLECTION: ' + ours if ours else 'not in our collection'}\n"
              f"    {f.get('outcome', '')[:220]}\n    {f.get('source_url', '')}")
    print(f"\n{len(found)}/{len(cases)} judgments checked: {counts}")


if __name__ == "__main__":
    {"export": export, "report": report}[sys.argv[1]]()
