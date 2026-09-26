"""Load parsed judgments into Postgres (`judgments`, metadata only). Idempotent.

  uv run python -m pipeline.load_judgments

Full text stays on disk in $LEXHACK_DATA/parsed/judgment/ (raw_path points at it): the Neon free plan's
~0.5 GB cap can't hold ~360 MB of text plus indexes. Extraction reads the files locally.
"""
import json
from datetime import datetime

from crawler.config import data_dir, parsed_dir
from crawler.parse import out_path

from .db import apply_schema, connect


def decision_date(d):
    try:
        return datetime.strptime(d["metadata"].get("Judgment date", ""), "%d %B %Y").date()
    except ValueError:
        return d["expression_date"]


def row(d):
    m = d["metadata"]
    judges = [j.strip() for j in (m.get("Judges") or "").split(",") if j.strip()] or None
    return (d["work"].removeprefix("/akn/"),                        # 'ke/judgment/kesc/2017/2'
            m.get("Media Neutral Citation") or m.get("Citation"),
            d["title"],
            m.get("Court"),
            m.get("Case number"),
            decision_date(d),
            judges,
            d["display_type"] != "pdf" and bool(d["text"]),
            "manual" if d["retrieved_from"].startswith("manual/") else "wayback",
            d["url"],                                                  # Kenya Law URL: what users click
            str(out_path(parsed_dir(), d).relative_to(data_dir())))


def main():
    rows = {}
    for p in sorted((parsed_dir() / "judgment").glob("*.json")):
        d = json.loads(p.read_text())
        r = row(d)
        if r[0] not in rows or d["expression_date"] > rows[r[0]][1]:   # one row per judgment: latest expression
            rows[r[0]] = (r, d["expression_date"])
    with connect() as conn:
        apply_schema(conn)
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO judgments VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (judgment_id) DO UPDATE SET neutral_citation=EXCLUDED.neutral_citation,
                title=EXCLUDED.title, court=EXCLUDED.court, case_number=EXCLUDED.case_number,
                decision_date=EXCLUDED.decision_date, judges=EXCLUDED.judges, has_full_text=EXCLUDED.has_full_text,
                source=EXCLUDED.source, source_url=EXCLUDED.source_url, raw_path=EXCLUDED.raw_path""",
                            [r for r, _ in rows.values()])
        print(f"loaded {len(rows)} judgments")
        for court, n, full, dated in conn.execute("""SELECT court, count(*), count(*) FILTER (WHERE has_full_text),
                count(*) FILTER (WHERE decision_date IS NOT NULL) FROM judgments GROUP BY 1 ORDER BY 2 DESC LIMIT 12"""):
            print(f"  {court}: {n} ({full} with full text, {dated} dated)")


if __name__ == "__main__":
    main()
