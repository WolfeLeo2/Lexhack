"""Status audit: does each section's derived status read correctly, given its whole history?

The event review checks events one at a time; this checks what the rules (api/status_ke.py) make of them together.

  uv run python -m pipeline.audit_status export     # every section with a checked ruling -> $LEXHACK_DATA/review/status_audit/
  uv run python -m pipeline.audit_status report     # summarise the auditors' findings
  uv run python -m pipeline.audit_status issues     # load review/issues/labels.json -> citation_events.issue / stance

Auditors (agents) write findings/batch_NN.json; nothing here writes to the database.
"""
import argparse
import collections
import json

from api.status import provision_status
from crawler.config import data_dir

from .db import connect

ROOT = data_dir() / "review" / "status_audit"
BATCH = 15


def export():
    (ROOT / "findings").mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        pids = [p for (p,) in conn.execute("""SELECT DISTINCT e.provision_id FROM citation_events e
            LEFT JOIN judgments j USING (judgment_id) WHERE e.verified AND j.duplicate_of IS NULL ORDER BY 1""")]
        sections = []
        for pid in pids:
            head = conn.execute("""SELECT a.title, p.number, p.heading, t.text FROM provisions p JOIN acts a USING (act_id)
                JOIN provision_texts t USING (provision_id) JOIN act_versions v USING (version_id)
                WHERE p.provision_id = %s ORDER BY v.version_date DESC LIMIT 1""", (pid,)).fetchone()
            res = provision_status(conn, pid)
            raw = dict(conn.execute("SELECT judgment_id, raw_path FROM judgments WHERE judgment_id = ANY(%s)",
                                    ([e["judgment_id"] for e in res["history"] if e["judgment_id"]],)).fetchall())
            sections.append({
                "provision_id": pid, "act": head[0], "section": head[1], "heading": head[2], "text": head[3],
                "status": res["status"], "summary_event_ids": [e["event_id"] for e in res["summary_events"]],
                "history": [{k: e[k] for k in ("event_id", "effective_date", "court", "title", "event_type", "scope",
                                               "scope_text", "subsection", "operative_quote", "source_paragraph",
                                               "state", "superseded_by", "verified_by")}
                            | {"judgment_file": str(data_dir() / raw[e["judgment_id"]]) if e["judgment_id"] in raw else None}
                            for e in res["history"]]})
    for n in range(0, len(sections), BATCH):
        (ROOT / f"batch_{n // BATCH:02d}.json").write_text(json.dumps(sections[n:n + BATCH], indent=1, default=str,
                                                                      ensure_ascii=False), encoding="utf-8")
    print(f"{len(sections)} sections in {-(-len(sections) // BATCH)} batches -> {ROOT}")


def report():
    found = [f for p in sorted((ROOT / "findings").glob("*.json")) for f in json.loads(p.read_text())]
    print(collections.Counter(f["verdict"] for f in found))
    for f in found:
        if f["verdict"] != "ok":
            print(f"\n[{f['verdict']}] {f['provision_id']}\n  derived: {f['derived_status']}\n  should read: "
                  f"{f.get('should_read', '')}\n  cause: {f.get('cause', '')}  events: {f.get('event_ids', [])}\n  why: {f['reason']}")


def issues():
    """The legal point each ruling decides, labelled by an agent, so displacement compares like with like."""
    labels = json.loads((data_dir() / "review" / "issues" / "labels.json").read_text())
    with connect() as conn:
        conn.cursor().executemany("UPDATE citation_events SET issue = %s, stance = %s WHERE event_id = %s",
                                  [(v["issue"], v.get("stance"), int(k)) for k, v in labels.items()])
        conn.commit()
    print(f"labelled {len(labels)} events")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "report", "issues"])
    {"export": export, "report": report, "issues": issues}[ap.parse_args().cmd]()
