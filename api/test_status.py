"""Offline check of the Kenyan status rules on the answer key's two multi-event histories (README §5.4).

  uv run python -m api.test_status
"""
import csv
from pathlib import Path

from .status import chains, with_leads
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
    # Parliament: an amendment changes nothing; a total repeal wins; a later court ruling doesn't displace a repeal
    amend = dict(ev[0], event_id=98, event_key="AMD", event_type="amended_by_statute", court=None, scope="partial",
                 effective_date="2003-01-01", verified=True, affects_event_id=None)
    if with_leads(resolve, ev + [amend])["status"] != "limited by a court":
        fails.append(("amendment changed status",))
    if resolve([amend])["status"] != "in force; no recorded court rulings":
        fails.append(("amendment-only status", resolve([amend])["status"]))
    rep = dict(amend, event_id=97, event_key="REP", event_type="repealed_by_statute", scope="total")
    upheld_after = dict(ev[0], event_id=96, event_key="UP", event_type="upheld", court="Supreme Court",
                        effective_date="2030-01-01", affects_event_id=None)
    r = resolve([rep, upheld_after])
    if r["status"] != "repealed" or states(r)["REP"] != "in effect":
        fails.append(("repeal", r["status"], states(r)))
    # issues: a later ruling on a different point doesn't displace; a stance-bearing interpretation does
    hc = dict(ev[0], event_id=90, event_key="HC", event_type="upheld", court="High Court", effective_date="2014-01-01",
              affects_event_id=None, issue="consensual adolescent sex")
    ca = dict(ev[0], event_id=91, event_key="CA", event_type="read_down", court="Court of Appeal",
              effective_date="2019-01-01", affects_event_id=None, issue="minimum sentence discretion")
    if states(resolve([hc, ca]))["HC"] != "in effect":
        fails.append(("different point displaced", states(resolve([hc, ca]))))
    kit = dict(ca, event_id=92, event_key="KIT", event_type="declared_unconstitutional", effective_date="2018-01-01",
               issue="mandatory death sentence")
    dirs = dict(kit, event_id=93, event_key="DIR", event_type="interpreted", court="Supreme Court",
                effective_date="2021-07-06", stance="validates")
    if states(resolve([kit, dirs]))["KIT"] != "displaced by a later ruling":
        fails.append(("stance did not displace", states(resolve([kit, dirs]))))
    # renumbering: same number, versions one after the other -> one chain; overlapping versions -> two sections
    rows = [("a", "45", "sec_45", ["2007", "2022-04"]), ("a", "45", "part_VI__sec_45", ["2022-12", "2024"]),
            ("a", "43", "part_V__sec_43", ["1972", "2022"]), ("a", "43", "part_VI__sec_43", ["2021", "2024"]),
            ("a", "1", "sec_1", ["2007", "2024"])]
    got = {k: [x["provision_id"] for x in v] for k, v in chains(rows).items()}
    if got != {"sec_45": ["sec_45", "part_VI__sec_45"], "part_VI__sec_45": ["sec_45", "part_VI__sec_45"]}:
        fails.append(("renumbering chains", got))
    for f in fails:
        print("FAIL", *f)
    print(f"{14 - len(fails)}/14 passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
