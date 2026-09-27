"""Offline check of the Kenyan status rules on the answer key's two multi-event histories (README §5.4).

  uv run python -m api.test_status
"""
import csv
from pathlib import Path

from .status import with_leads
from .status_ke import resolve

COURT = {"kesc": "Supreme Court", "keca": "Court of Appeal", "kehc": "High Court"}
KEY = Path(__file__).resolve().parent.parent / "ground_truth" / "events.csv"


def events_for(provision_suffix):
    rows = [r for r in csv.DictReader(open(KEY, encoding="utf-8")) if r["provision_id"].endswith(provision_suffix)]
    ids = {r["event_key"]: n for n, r in enumerate(rows)}
    return [{"event_id": ids[r["event_key"]], "event_key": r["event_key"], "event_type": r["event_type"],
             "scope": r["scope"], "effective_date": r["effective_date"], "court": COURT[r["judgment_id"].split("/")[2]],
             "affects_event_id": ids.get(r["affects_event"])} for r in rows]


def states(res):
    return {e["event_key"]: e["state"] for e in res["history"]}


def main():
    fails = []
    s204 = resolve(events_for("sec_204"))
    want = {"E18": "displaced by a later ruling", "E20": "displaced by a later ruling", "E07": "in effect",
            "E08": "in effect"}
    if s204["status"] != "limited by a court" or states(s204) != want:
        fails.append(("s.204", s204["status"], states(s204)))
    if [e["event_key"] for e in s204["summary_events"]] != ["E07", "E08"]:
        fails.append(("s.204 summary", [e["event_key"] for e in s204["summary_events"]]))

    s8 = resolve(events_for("cap-63a/sec_8"))
    want = {"E09": "displaced by a later ruling", "E11": "reversed on appeal", "E12": "reversed on appeal",
            "E19": "reversed on appeal", "E13": "in effect", "E14": "in effect", "E15": "in effect"}
    if s8["status"] != "in force; earlier court limits were reversed" or states(s8) != want:
        fails.append(("s.8", s8["status"], states(s8)))

    for suffix, status in [("sec_29", "declared unconstitutional"), ("sec_194", "limited by a court"),
                           ("sec_162", "in force; its validity has been tested in court")]:
        got = resolve(events_for(suffix))["status"]
        if got != status:
            fails.append((suffix, got))
    if resolve([])["status"] != "in force; no recorded court rulings":
        fails.append(("no events",))
    # an unverified lead (a later Supreme Court "upheld") must not displace Muruatetu or change the status
    ev = [dict(e, verified=True) for e in events_for("sec_204")]
    lead = dict(ev[0], event_id=99, event_key="LEAD", event_type="upheld", court="Supreme Court",
                effective_date="2030-01-01", verified=False, affects_event_id=None)
    led = with_leads(resolve, ev + [lead])
    if led["status"] != "limited by a court" or states(led) != {**states(s204), "LEAD": "in effect"}:
        fails.append(("lead changed status", led["status"], states(led)))
    for f in fails:
        print("FAIL", *f)
    print(f"{8 - len(fails)}/8 passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
