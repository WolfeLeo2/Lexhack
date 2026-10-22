"""Load the later-appeal pass's findings (pipeline/appeal_check.py) into judgment_appeals, so the API can show them.

  uv run python -m pipeline.load_appeals

Reads $LEXHACK_DATA/review/appeals/findings/*.json. Only appeals still pending, found with medium or high confidence,
are loaded: a wrong "appeal pending" note on a landmark ruling would be a harm of its own, so low-confidence findings are
listed here and left for a manual check. Reversals are not loaded: they already show as rulings "reversed on appeal"
(citation_events.affects_event_id). A finding may carry its own "checked_by" (hand-added ones); the default is the Sonnet
agent. Re-running replaces the table's contents.
"""
import json

from crawler.config import data_dir

from .db import apply_schema, connect

CHECKED_BY = "agent:claude-sonnet appeal check v1"
SHOWN = ("appeal_pending",)
CONFIDENT = ("medium", "high")


def main():
    found = [f for p in sorted((data_dir() / "review" / "appeals" / "findings").glob("*.json"))
             for f in json.loads(p.read_text(encoding="utf-8"))]
    keep = [f for f in found if f["later_history"] in SHOWN and f.get("confidence") in CONFIDENT and f.get("source_url")]
    held = [f for f in found if f["later_history"] in SHOWN and f not in keep]
    with connect() as conn:
        apply_schema(conn)
        with conn.transaction():
            conn.execute("DELETE FROM judgment_appeals")
            for f in keep:
                conn.execute("""INSERT INTO judgment_appeals (judgment_id, later_history, appellate_case, appellate_court,
                    appellate_date, outcome, source_url, confidence, checked_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                             (f["judgment_id"], f["later_history"], f.get("appellate_case") or None,
                              f.get("appellate_court") or None, f.get("appellate_date") or None, f.get("outcome"),
                              f["source_url"], f["confidence"], f.get("checked_by", CHECKED_BY)))
    print(f"{len(keep)} pending appeals loaded; {len(held)} held back for a manual check (low confidence or no source):")
    for f in held:
        print(f"  {f['judgment_id']}: {f.get('appellate_case') or '?'} ({f.get('confidence')})")


if __name__ == "__main__":
    main()
