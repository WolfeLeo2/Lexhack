"""Kenyan status rules: how a section's events combine into its current status. Pure functions; no database.

An event stops counting when either
  1. a later event directly reverses it (affects_event: an appeal from that judgment), or
  2. a later event from a court of equal or higher rank points the other way ON THE SAME POINT (citation_events.issue;
     an interpretation counts when it carries a stance) (precedent: Mwaura (CA 2013) displaces
     Mutiso (CA 2010); the Supreme Court's 2024-25 rulings displace Kilwake (CA 2019), which was never appealed).
"interpreted" events never displace anything; they qualify the events on the same section.

The result is never a yes/no: it's a status label plus the events that produce it, each with the court's words.
"""
RANK = {"Supreme Court": 3, "Court of Appeal": 2, "High Court": 1}
# Parliament's changes (pipeline/statutory_events.py). They never displace, and are never displaced by, a court ruling;
# an amendment leaves the status alone (it shows in the history); a total repeal makes the section "repealed".
STATUTORY = {"repealed_by_statute", "amended_by_statute"}
LIMITING = {"declared_unconstitutional", "read_down", "severed", "repealed_by_statute"}
VALIDATING = {"upheld", "reversed_on_appeal"}


def direction(e):
    return "limits" if e["event_type"] in LIMITING else "validates" if e["event_type"] in VALIDATING else None


def pull(e):
    """Which way an event pushes for displacement. Like direction(), but an interpretation can carry a stance (the
    2021 Muruatetu directions cut against lower courts that stretched the 2017 ruling to other sections)."""
    return e.get("stance") if e["event_type"] == "interpreted" and e.get("stance") else direction(e)


def same_point(a, b):
    """Rulings displace each other only on the same legal point (citation_events.issue); unlabelled events are
    assumed to be on the same point, as before issues existed."""
    return not a.get("issue") or not b.get("issue") or a["issue"] == b["issue"]


def resolve(events):
    """events: dicts with event_id, event_type, scope, court, effective_date, affects_event_id (+ anything else, passed
    through). -> {"status", "summary_events", "history"}; history entries gain "state" and "superseded_by"."""
    events = sorted(events, key=lambda e: (e["effective_date"] or "", e["event_id"]))
    by_id = {e["event_id"]: e for e in events}
    out = {e["event_id"]: dict(e, state="in effect", superseded_by=None) for e in events}
    for e in events:                      # 1. direct reversals
        target = by_id.get(e.get("affects_event_id"))
        if target and e["event_type"] == "reversed_on_appeal":
            out[target["event_id"]].update(state="reversed on appeal", superseded_by=e["event_id"])
    for i, e in enumerate(events):        # 2. precedent: a later, equal-or-higher court pointing the other way
        if out[e["event_id"]]["state"] != "in effect" or not direction(e) or e["event_type"] in STATUTORY:
            continue
        for later in events[i + 1:]:
            if (later["event_type"] not in STATUTORY and pull(later) and pull(later) != direction(e) and same_point(e, later)
                    and RANK.get(later["court"], 0) >= RANK.get(e["court"], 0)
                    and later.get("effective_date") != e.get("effective_date")):
                out[e["event_id"]].update(state="displaced by a later ruling", superseded_by=later["event_id"])
                break
    live = [out[e["event_id"]] for e in events if out[e["event_id"]]["state"] == "in effect"]
    limits = [e for e in live if direction(e) == "limits"]
    court = [e for e in events if e["event_type"] not in STATUTORY]
    if any(e["event_type"] == "repealed_by_statute" and e["scope"] == "total" for e in live):
        status = "repealed"
    elif any(e["event_type"] == "declared_unconstitutional" and e["scope"] == "total" for e in limits):
        status = "declared unconstitutional"
    elif (limits := [e for e in limits if e["event_type"] not in STATUTORY]):
        status = "limited by a court"
    elif any(e["event_type"] == "reversed_on_appeal" for e in live):   # the reversal is the news, even if also upheld
        status = "in force; earlier court limits were reversed"
    elif any(e["event_type"] == "upheld" for e in live):
        status = "in force; its validity has been tested in court"
    elif court:
        status = "in force; interpreted by a court"
    else:
        status = "in force; no recorded court rulings"
    # ponytail: a lower court limiting a section after a higher court upheld it keeps "limited"; flag such
    # conflicts in the UI if they turn up in the extracted events.
    repeal = [e for e in live if e["event_type"] == "repealed_by_statute" and e["scope"] == "total"]
    live_court = [e for e in live if e["event_type"] not in STATUTORY]
    summary = repeal or limits or [e for e in live_court if direction(e)] or live_court
    # interpretations of the summary events (same section) travel with them
    if not repeal:
        summary += [e for e in live if e["event_type"] == "interpreted" and e not in summary]
    return {"status": status, "summary_events": summary, "history": [out[e["event_id"]] for e in events]}
