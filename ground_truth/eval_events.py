"""Score event classification (pipeline.classify_events) against the answer key, from the database.

  uv run python -m ground_truth.eval_events

Only judgments that have been classified (have extracted rows, or were run and produced none) are scored; run
`classify_events --answer-key` first. An answer-key event is FOUND when an extracted event exists for the same
judgment and section; its event_type and scope are then compared. Extracted events on a negatives.csv pair are
FALSE ALARMS. Extracted events in answer-key judgments that the key doesn't have are listed for review (the key
isn't exhaustive: a judgment can rule on sections we didn't record).
"""
import collections
import csv
from pathlib import Path

from pipeline.db import connect

HERE = Path(__file__).parent


def main():
    key = list(csv.DictReader(open(HERE / "events.csv", encoding="utf-8")))
    neg = list(csv.DictReader(open(HERE / "negatives.csv", encoding="utf-8")))
    with connect() as conn:
        ran = {j for (j,) in conn.execute("SELECT judgment_id FROM event_runs")}
        ext = collections.defaultdict(list)
        for jid, pid, typ, scope, quote, para in conn.execute("""SELECT judgment_id, provision_id, event_type, scope,
                operative_quote, source_paragraph FROM citation_events WHERE method = 'extracted'"""):
            ext[(jid, pid)].append((typ, scope, quote, para))
    s, lines = collections.Counter(), []
    s["not_run"] = sum(k["judgment_id"] not in ran for k in key) + sum(n["judgment_id"] not in ran for n in neg)
    key = [k for k in key if k["judgment_id"] in ran]
    neg = [n for n in neg if n["judgment_id"] in ran]
    for k in key:
        got = ext.get((k["judgment_id"], k["provision_id"]), [])
        s["key"] += 1
        if not got:
            s["missed"] += 1
            lines.append(f"MISS  {k['event_key']} {k['event_type']} {k['case_name'][:60]}")
            continue
        s["found"] += 1
        typ = next((g for g in got if g[0] == k["event_type"]), got[0])
        s["type_right"] += typ[0] == k["event_type"]
        s["scope_right"] += typ[1] == k["scope"]
        if typ[0] != k["event_type"]:
            lines.append(f"TYPE  {k['event_key']} want {k['event_type']}, got {[g[0] for g in got]}")
        elif typ[1] != k["scope"]:
            lines.append(f"SCOPE {k['event_key']} {k['event_type']} want {k['scope']}, got {typ[1]}")
    for n in neg:
        got = ext.get((n["judgment_id"], n["provision_id"]), [])
        s["neg"] += 1
        if got:
            s["false_alarm"] += 1
            lines.append(f"FALSE {n['judgment_id']} {n['provision_id'].split('/')[-1]}: {[g[0] for g in got]}")
    keyed = {(k["judgment_id"], k["provision_id"]) for k in key}
    key_judgments = {k["judgment_id"] for k in key}
    extra = [(j, p, g) for (j, p), gs in ext.items() for g in gs if j in key_judgments and (j, p) not in keyed]
    print(f"answer key: {s['found']}/{s['key']} events found; of those, event_type right {s['type_right']}/{s['found']}, "
          f"scope right {s['scope_right']}/{s['found']}")
    print(f"negatives: {s['false_alarm']}/{s['neg']} false alarms")
    print(f"not scored (judgment not classified yet): {s['not_run']} answer-key/negative rows")
    print(f"extra events in answer-key judgments (review; may be real): {len(extra)}")
    print("\n".join(lines))
    for j, p, (typ, scope, quote, para) in extra:
        print(f"EXTRA {j} {p.split('/', 2)[2]} {typ}/{scope} para {para}: {quote[:110]}")


if __name__ == "__main__":
    main()
