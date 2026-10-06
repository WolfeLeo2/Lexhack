"""Status of a provision: load its events and apply the jurisdiction's rules (status_ke for 'ke/...').

  uv run python -m api.status ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204
"""
import collections
import difflib
import re
import sys

from . import status_ke

RULES = {"ke": status_ke}


def load_events(conn, provision_id, include_unverified=False, chain_map=None):
    """Manual (answer-key) and extracted events. When both record the same ruling (same judgment and type), the
    verified one wins. Extracted rows are unverified and say so."""
    return load_events_many(conn, [provision_id], include_unverified, chain_map).get(provision_id, [])


# Cosmetic heading changes at a revision (Employment Act s.71: the court was renamed)
HEADING_ALIASES = {"employment and labour relations court": "industrial court"}
PLACEHOLDER = re.compile(r"^(spent|deleted|repealed)\b")


def norm_heading(h):
    h = " ".join(re.sub(r"[^a-z0-9]+", " ", (h or "").lower()).split())
    for a, b in HEADING_ALIASES.items():
        h = h.replace(a, b)
    return h


def same_section(a, b):
    """Headings match: equal up to case, punctuation and small slips (s.57 child/children, s.79 'Regiser'). A
    '[Spent]' / '[Deleted…]' heading matches only another placeholder with the same number (s.31A)."""
    ha, hb = norm_heading(a["heading"]), norm_heading(b["heading"])
    if not ha or not hb:
        return False
    if PLACEHOLDER.match(ha) or PLACEHOLDER.match(hb):
        return bool(PLACEHOLDER.match(ha) and PLACEHOLDER.match(hb)) and a["number"] == b["number"]
    return difflib.SequenceMatcher(None, ha, hb).ratio() >= 0.9


def chains(rows):
    """rows: (act_id, number, provision_id, heading, [version dates]) -> {provision_id: chain, oldest first, of
    {"provision_id", "number", "versions"}} for sections Kenya Law renumbered between versions: an ID whose versions
    all come before another ID's in the same Act, with the same heading (same_section), whatever the numbers (the
    Employment Act's 2022 revision moved ss.83-92 down one place). The match must be unique: among the earliest later
    IDs with that heading, the same number breaks a tie (two 'Interpretation' sections); otherwise no merge. Two IDs
    whose versions overlap are different sections."""
    acts = {}
    for act, number, pid, heading, versions in rows:
        acts.setdefault(act, []).append({"provision_id": pid, "number": number, "heading": heading,
                                         "versions": list(versions)})
    out = {}
    for rs in acts.values():
        links = {}
        for a in rs:
            later = [b for b in rs if a["versions"][-1] < b["versions"][0] and same_section(a, b)]
            first = min((b["versions"][0] for b in later), default=None)
            later = [b for b in later if b["versions"][0] == first]
            if len(later) > 1:
                later = [b for b in later if b["number"] == a["number"]]
            if len(later) == 1:
                links[a["provision_id"]] = later[0]["provision_id"]
        taken = collections.Counter(links.values())
        links = {a: b for a, b in links.items() if taken[b] == 1}   # each new ID claimed by one old ID only
        by_id = {r["provision_id"]: {k: r[k] for k in ("provision_id", "number", "versions")} for r in rs}
        for head in set(links) - set(links.values()):
            chain = [head]
            while chain[-1] in links:
                chain.append(links[chain[-1]])
            out |= {x: [by_id[y] for y in chain] for x in chain}
    return out


def renumbering(conn, provision_ids):
    """The renumbered-section lookup (chains) for the Acts of these provisions, one query. Every caller that merges a
    section's old and new IDs (status, counts, citations, the Acts list, the agent tools) goes through here; pass its
    result on as chain_map to avoid repeating it."""
    rows = conn.execute("""
        SELECT p.act_id, p.number, p.provision_id, p.heading, array_agg(v.version_date::text ORDER BY v.version_date)
        FROM provisions p JOIN provision_texts t USING (provision_id) JOIN act_versions v USING (version_id)
        WHERE p.act_id IN (SELECT act_id FROM provisions WHERE provision_id = ANY(%s))
        GROUP BY 1, 2, 3, 4""", (list(provision_ids),)).fetchall()
    return chains(rows)


def members(chain_map, provision_id):
    """Every ID of the section: itself, plus its other numberings if renumbered."""
    return [x["provision_id"] for x in chain_map.get(provision_id, [{"provision_id": provision_id}])]


def load_events_many(conn, provision_ids, include_unverified=False, chain_map=None):
    """{provision_id: events} for many provisions in ONE events query (search results). A renumbered section gets the
    events of all its IDs (each event keeps its own provision_id). Extracted events the second-pass checker failed
    (pipeline/verify_events.py) are never returned."""
    chain_map = renumbering(conn, provision_ids) if chain_map is None else chain_map
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


def provision_status(conn, provision_id, include_unverified=False, chain_map=None):
    rules = RULES[provision_id.split("/", 1)[0]]
    return with_leads(rules.resolve, load_events(conn, provision_id, include_unverified, chain_map))


def statuses(conn, provision_ids, include_unverified=False, chain_map=None):
    """{provision_id: status label} for many provisions, one query."""
    events = load_events_many(conn, provision_ids, include_unverified, chain_map)
    return {p: RULES[p.split("/", 1)[0]].resolve(events.get(p, []))["status"] for p in provision_ids}


if __name__ == "__main__":
    from pipeline.db import connect
    with connect() as conn:
        res = provision_status(conn, sys.argv[1])
    print(res["status"])
    for e in res["history"]:
        print(f"  {e['effective_date']} {e['event_key'] or 'extr'} {e['court']:<15} {e['event_type']:<26} {e['state']}")
