"""Kenyan status rules: how a section's events combine into its current status. Pure functions; no database.

An event stops counting when either
  1. a later event directly reverses it (affects_event: an appeal from that judgment), or
  2. a later event from a court of equal or higher rank points the other way (precedent: Mwaura (CA 2013) displaces
     Mutiso (CA 2010); the Supreme Court's 2024-25 rulings displace Kilwake (CA 2019), which was never appealed).
"interpreted" events never displace anything; they qualify the events on the same section.

The result is never a yes/no: it's a status label plus the events that produce it, each with the court's words.
"""
RANK = {"Supreme Court": 3, "Court of Appeal": 2, "High Court": 1}
LIMITING = {"declared_unconstitutional", "read_down", "severed", "repealed_by_statute"}
VALIDATING = {"upheld", "reversed_on_appeal"}


def direction(e):
    return "limits" if e["event_type"] in LIMITING else "validates" if e["event_type"] in VALIDATING else None


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
        if out[e["event_id"]]["state"] != "in effect" or not direction(e):
            continue
        for later in events[i + 1:]:
            if (direction(later) and direction(later) != direction(e)
                    and RANK.get(later["court"], 0) >= RANK.get(e["court"], 0)
                    and later.get("effective_date") != e.get("effective_date")):
                out[e["event_id"]].update(state="displaced by a later ruling", superseded_by=later["event_id"])
                break
    live = [out[e["event_id"]] for e in events if out[e["event_id"]]["state"] == "in effect"]
    limits = [e for e in live if direction(e) == "limits"]
    if any(e["event_type"] == "repealed_by_statute" for e in limits):
        status = "repealed"
    elif any(e["event_type"] == "declared_unconstitutional" and e["scope"] == "total" for e in limits):
        status = "declared unconstitutional"
    elif limits:
        status = "limited by a court"
    elif any(e["event_type"] == "upheld" for e in live):
        status = "in force; its validity has been tested in court"
    elif any(e["event_type"] == "reversed_on_appeal" for e in live):
        status = "in force; earlier court limits were reversed"
    elif events:
        status = "in force; interpreted by a court"
    else:
        status = "in force; no recorded court rulings"
    # ponytail: a lower court limiting a section after a higher court upheld it keeps "limited"; flag such
    # conflicts in the UI if they turn up in the extracted events.
    summary = limits or [e for e in live if direction(e)] or live
    # interpretations of the summary events (same section) travel with them
    summary += [e for e in live if e["event_type"] == "interpreted" and e not in summary]
    return {"status": status, "summary_events": summary, "history": [out[e["event_id"]] for e in events]}
