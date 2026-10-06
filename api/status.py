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


def chains(rows):
    """rows: (act_id, number, provision_id, [version dates]) -> {provision_id: chain, oldest first, of
    {"provision_id", "versions"}} for sections renumbered between versions: two or more IDs in one Act with the same
    number whose versions don't overlap (each ID's versions all before the next one's). Overlapping IDs are two
    different sections that share a number, and stay apart."""
    groups, out = {}, {}
    for act, number, pid, versions in rows:
        groups.setdefault((act, number), []).append({"provision_id": pid, "versions": list(versions)})
    for g in groups.values():
        g.sort(key=lambda x: x["versions"][0])
        if len(g) > 1 and all(a["versions"][-1] < b["versions"][0] for a, b in zip(g, g[1:])):
            out |= {x["provision_id"]: g for x in g}
    return out


def renumbering(conn, provision_ids):
    """The renumbered-section lookup (chains) for these provisions, one query. Every caller that merges a section's
    old and new IDs (status, counts, citations, the Acts list, the agent tools) goes through here."""
    rows = conn.execute("""
        SELECT p.act_id, p.number, p.provision_id, array_agg(v.version_date::text ORDER BY v.version_date)
        FROM provisions p JOIN provision_texts t USING (provision_id) JOIN act_versions v USING (version_id)
        WHERE (p.act_id, p.number) IN (SELECT act_id, number FROM provisions WHERE provision_id = ANY(%s))
        GROUP BY 1, 2, 3""", (list(provision_ids),)).fetchall()
    return chains(rows)


def members(chain_map, provision_id):
    """Every ID of the section: itself, plus its other numberings if renumbered."""
    return [x["provision_id"] for x in chain_map.get(provision_id, [{"provision_id": provision_id}])]


def load_events_many(conn, provision_ids, include_unverified=False):
    """{provision_id: events} for many provisions in ONE events query (search results). A renumbered section gets the
    events of all its IDs (each event keeps its own provision_id). Extracted events the second-pass checker failed
    (pipeline/verify_events.py) are never returned."""
    chain_map = renumbering(conn, provision_ids)
    own = load_own(conn, {q for p in provision_ids for q in members(chain_map, p)}, include_unverified)
    out = {}
    for p in provision_ids:
        seen = set()
        for q in members(chain_map, p):   # one ruling recorded on both IDs counts once
            keys = set()
            for e in own.get(q, []):
                k = (e["judgment_id"] or (e["source_paragraph"], e["effective_date"]), e["event_type"])
                if k not in seen:
                    out.setdefault(p, []).append(e)
                    keys.add(k)
            seen |= keys
    return out


def load_own(conn, provision_ids, include_unverified):
    rows = conn.execute("""
        SELECT e.provision_id, e.event_id, e.event_key, e.event_type, e.scope, e.scope_text, e.subsection, e.operative_quote,
               e.source_paragraph, e.effective_date::text, e.affects_event_id, e.method, e.verified, e.verified_by, e.confidence, e.issue, e.stance,
               j.judgment_id, j.title, j.court, j.neutral_citation, j.source_url
        FROM citation_events e LEFT JOIN judgments j USING (judgment_id)
        WHERE e.provision_id = ANY(%s) AND (e.verified OR (%s AND e.check_verdict IS DISTINCT FROM 'fail'))
          AND j.duplicate_of IS NULL   -- a judgment Kenya Law published twice counts once (pipeline/dedupe_judgments.py)
        ORDER BY e.method = 'manual' DESC, e.event_id""", (list(provision_ids), include_unverified)).fetchall()
    cols = ["event_id", "event_key", "event_type", "scope", "scope_text", "subsection", "operative_quote",
            "source_paragraph", "effective_date", "affects_event_id", "method", "verified", "verified_by", "confidence", "issue", "stance",
            "judgment_id", "title", "court", "neutral_citation", "source_url"]
    seen, out = set(), {}
    for pid, *r in rows:
        e = dict(zip(cols, r))
        k = (pid, e["judgment_id"] or e["event_key"] or e["event_id"], e["event_type"])   # Parliament's events have no judgment
        if k in seen:
            continue
        seen.add(k)
        out.setdefault(pid, []).append(e | {"provision_id": pid})
    return out


def with_leads(resolve, events):
    """Status, summary and the states of verified events come from verified events alone; unverified leads are
    listed in the history with the state they would have, but never change what the verified record says."""
    res = resolve([e for e in events if e["verified"]])
    if all(e["verified"] for e in events):
        return res
    checked = {e["event_id"]: e for e in res["history"]}
    return {**res, "history": [checked.get(e["event_id"], e) for e in resolve(events)["history"]]}


def provision_status(conn, provision_id, include_unverified=False):
    rules = RULES[provision_id.split("/", 1)[0]]
    return with_leads(rules.resolve, load_events(conn, provision_id, include_unverified))


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
