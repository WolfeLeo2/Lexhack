"""Precision of extracted events, from two blind reviews of a random sample (events_review_sample.py).

  uv run python -m ground_truth.eval_events_review
  uv run python -m ground_truth.eval_events_review --resolved events_review_resolved.csv   # + adjudications

An event is RIGHT when it is a real event of the claimed type on the claimed section. Where reviewers A and B
disagree on that, the event is listed; an adjudicated row (same columns as a review file) settles it.
"""
import argparse
import collections
import csv
from pathlib import Path

HERE = Path(__file__).parent


def verdict(r, claimed):
    if r["is_event"] != "yes":
        return "not an event" if r["is_event"] == "no" else "unsure"
    if r["section_right"] != "yes":
        return "wrong section"
    return "right" if r["correct_type"] == claimed else f"wrong type ({r['correct_type']})"


def load(name):
    return {r["event_id"]: r for r in csv.DictReader(open(HERE / name, encoding="utf-8"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolved")
    args = ap.parse_args()
    sample = load("events_review_sample.csv")
    a, b = load("events_review_A.csv"), load("events_review_B.csv")
    res = load(args.resolved) if args.resolved else {}
    final, split, quotes = collections.Counter(), [], collections.Counter()
    for eid, e in sample.items():
        va, vb = verdict(a[eid], e["event_type"]), verdict(b[eid], e["event_type"])
        if eid in res:
            v = verdict(res[eid], e["event_type"])
        elif va == vb:
            v = va
        else:
            split.append((eid, e["event_type"], e["section"], va, vb))
            continue
        final[v] += 1
        if v == "right":
            quotes["operative" if "yes" in (a[eid]["quote_operative"], b[eid]["quote_operative"]) else "not operative"] += 1
    decided = sum(final.values())
    print(f"{len(sample)} sampled events: {decided} decided, {len(split)} split between reviewers")
    if decided:
        print(f"precision (right / decided): {final['right']}/{decided} = {final['right'] / decided:.0%}")
    print("verdicts:", dict(final), "| quotes of right events:", dict(quotes))
    for eid, typ, sec, va, vb in split:
        print(f"SPLIT event {eid} {typ} {sec}: A={va!r} B={vb!r}")


if __name__ == "__main__":
    main()
