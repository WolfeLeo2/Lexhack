"""Load parsed Acts into Postgres: acts, act_versions, provisions, provision_texts. Idempotent.

  uv run python -m pipeline.load_acts

Reads $LEXHACK_DATA/parsed/act/*.json (written by crawler.parse). Re-running updates rows in place and keeps
existing embeddings unless a section's text changed.
"""
import json
import re
from collections import defaultdict

from crawler.config import data_dir, parsed_dir
from crawler.parse import out_path

from .db import apply_schema, connect

HEADING_RE = re.compile(r"^(\d+[A-Z]*)\.\s*(.*)$")   # '204. Punishment of murder', '8A. …'


def act_id_of(doc):
    cap = doc["metadata"].get("Citation", "")   # 'Cap. 63A'
    m = re.fullmatch(r"Cap\.\s*(\w+)", cap)
    if not m:
        raise ValueError(f"no Cap. citation for {doc['work']}: {cap!r}")
    return f"ke/act/cap-{m.group(1).lower()}", m.group(1)


def split_heading(h):
    m = HEADING_RE.match(h or "")
    return (m.group(1), m.group(2) or None) if m else (None, h)


def main():
    docs = [json.loads(p.read_text()) for p in sorted((parsed_dir() / "act").glob("*.json"))]
    docs.sort(key=lambda d: (d["work"], d["expression_date"]))
    acts, versions, provisions, texts = {}, [], {}, []
    for d in docs:
        act_id, cap = act_id_of(d)
        acts[act_id] = (act_id, "ke", d["title"], cap, d["work"])      # latest version's title wins
        vid = f"{act_id}@{d['expression_date']}"
        manual = d["retrieved_from"].startswith("manual/")
        versions.append((vid, act_id, d["expression_date"], "manual" if manual else "wayback",
                         d["url"], str(out_path(parsed_dir(), d).relative_to(data_dir()))))
        seen = set()
        for s in d["sections"]:
            if s["eid"] in seen:      # an eid should be unique per page; keep the first if not
                continue
            seen.add(s["eid"])
            pid = f"{act_id}/{s['eid']}"
            number, heading = split_heading(s["heading"])
            provisions[pid] = (pid, act_id, s["eid"], number, heading)   # latest version's heading wins
            texts.append((pid, vid, s["text"]))

    with connect() as conn:
        apply_schema(conn)
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO acts VALUES (%s,%s,%s,%s,%s) ON CONFLICT (act_id) DO UPDATE
                SET title=EXCLUDED.title, cap_number=EXCLUDED.cap_number, frbr_uri=EXCLUDED.frbr_uri""", list(acts.values()))
            cur.executemany("""INSERT INTO act_versions VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (version_id) DO UPDATE
                SET source=EXCLUDED.source, source_url=EXCLUDED.source_url, raw_path=EXCLUDED.raw_path""", versions)
            cur.executemany("""INSERT INTO provisions VALUES (%s,%s,%s,%s,%s) ON CONFLICT (provision_id) DO UPDATE
                SET number=EXCLUDED.number, heading=EXCLUDED.heading""", list(provisions.values()))
            cur.executemany("""INSERT INTO provision_texts (provision_id, version_id, text) VALUES (%s,%s,%s)
                ON CONFLICT (provision_id, version_id) DO UPDATE SET text=EXCLUDED.text,
                embedding = CASE WHEN provision_texts.text = EXCLUDED.text THEN provision_texts.embedding END""", texts)
    per_act = defaultdict(int)
    for pid, *_ in provisions.values():
        per_act[pid.rsplit("/", 1)[0]] += 1
    print(f"loaded {len(acts)} acts, {len(versions)} versions, {len(provisions)} provisions, {len(texts)} texts")
    for a, n in sorted(per_act.items()):
        print(f"  {a}: {n} provisions")


if __name__ == "__main__":
    main()
