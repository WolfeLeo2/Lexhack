"""Load the answer key (ground_truth/events.csv) into citation_events as method='manual' rows. Idempotent.

  uv run python -m pipeline.load_ground_truth

Rows are keyed by event_key ('E07'), so re-running updates them in place. Keys removed from the CSV are deleted.
affects_event ('E07') is resolved to affects_event_id in a second pass, once every row has an id.
"""
import csv
from pathlib import Path

from .db import apply_schema, connect

CSV = Path(__file__).resolve().parent.parent / "ground_truth" / "events.csv"
COLS = ["event_key", "provision_id", "judgment_id", "event_type", "scope", "scope_text", "subsection",
        "operative_quote", "source_paragraph", "effective_date", "method", "verified", "verified_by",
        "confidence", "notes"]


def main():
    rows = list(csv.DictReader(open(CSV, newline="", encoding="utf-8")))
    values = [tuple((r[c] or None) if c not in ("verified",) else r[c] == "true" for c in COLS) for r in rows]
    with connect() as conn:
        apply_schema(conn)
        with conn.cursor() as cur:
            cur.execute("UPDATE citation_events SET affects_event_id = NULL WHERE method = 'manual'")
            cur.execute("DELETE FROM citation_events WHERE method = 'manual' AND event_key <> ALL(%s)",
                        ([r["event_key"] for r in rows],))
            sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in COLS[1:])
            cur.executemany(f"INSERT INTO citation_events ({', '.join(COLS)}) VALUES ({', '.join(['%s'] * len(COLS))}) "
                            f"ON CONFLICT (event_key) DO UPDATE SET {sets}", values)
            cur.executemany("""UPDATE citation_events e SET affects_event_id = t.event_id FROM citation_events t
                               WHERE e.event_key = %s AND t.event_key = %s""",
                            [(r["event_key"], r["affects_event"]) for r in rows if r["affects_event"]])
        n, v, links = conn.execute("""SELECT count(*), count(*) FILTER (WHERE verified),
            count(affects_event_id) FROM citation_events WHERE method = 'manual'""").fetchone()
    print(f"loaded {n} ground-truth events ({v} verified, {links} affects_event links)")


if __name__ == "__main__":
    main()
