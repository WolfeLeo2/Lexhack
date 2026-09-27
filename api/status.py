"""Status of a provision: load its events and apply the jurisdiction's rules (status_ke for 'ke/...').

  uv run python -m api.status ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204
"""
import sys

from . import status_ke

RULES = {"ke": status_ke}


def load_events(conn, provision_id, include_unverified=False):
    """Manual (answer-key) and extracted events. When both record the same ruling (same judgment and type), the
    verified one wins. Extracted rows are unverified and say so."""
    return load_events_many(conn, [provision_id], include_unverified).get(provision_id, [])


def load_events_many(conn, provision_ids, include_unverified=False):
    """{provision_id: events} for many provisions in ONE query (search results). Extracted events the second-pass
    checker failed (pipeline/verify_events.py) are never returned."""
    rows = conn.execute("""
        SELECT e.provision_id, e.event_id, e.event_key, e.event_type, e.scope, e.scope_text, e.subsection, e.operative_quote,
               e.source_paragraph, e.effective_date::text, e.affects_event_id, e.method, e.verified, e.confidence,
               j.judgment_id, j.title, j.court, j.neutral_citation, j.source_url
        FROM citation_events e LEFT JOIN judgments j USING (judgment_id)
        WHERE e.provision_id = ANY(%s) AND (e.verified OR (%s AND e.check_verdict IS DISTINCT FROM 'fail'))
        ORDER BY e.method = 'manual' DESC, e.event_id""", (list(provision_ids), include_unverified)).fetchall()
    cols = ["event_id", "event_key", "event_type", "scope", "scope_text", "subsection", "operative_quote",
            "source_paragraph", "effective_date", "affects_event_id", "method", "verified", "confidence",
            "judgment_id", "title", "court", "neutral_citation", "source_url"]
    seen, out = set(), {}
    for pid, *r in rows:
        e = dict(zip(cols, r))
        if (pid, e["judgment_id"], e["event_type"]) in seen:
            continue
        seen.add((pid, e["judgment_id"], e["event_type"]))
        out.setdefault(pid, []).append(e)
    return out


def provision_status(conn, provision_id, include_unverified=False):
    rules = RULES[provision_id.split("/", 1)[0]]
    return rules.resolve(load_events(conn, provision_id, include_unverified))


def statuses(conn, provision_ids, include_unverified=False):
    """{provision_id: status label} for many provisions, one query."""
    events = load_events_many(conn, provision_ids, include_unverified)
    return {p: RULES[p.split("/", 1)[0]].resolve(events.get(p, []))["status"] for p in provision_ids}


if __name__ == "__main__":
    from pipeline.db import connect
    with connect() as conn:
        res = provision_status(conn, sys.argv[1])
    print(res["status"])
    for e in res["history"]:
        print(f"  {e['effective_date']} {e['event_key'] or 'extr'} {e['court']:<15} {e['event_type']:<26} {e['state']}")
