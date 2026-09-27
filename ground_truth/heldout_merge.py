"""Merge the two independent labellings of the held-out sample into mentions_heldout_gold.csv.

  uv run python -m ground_truth.heldout_merge            # write agreed rows + list disagreements
  uv run python -m ground_truth.heldout_merge --resolved heldout_labels/resolved.csv   # + adjudicated rows

Each candidate was labelled twice (heldout_labels/{court}_A.csv and _B.csv), by labellers that saw neither each other
nor the extractor. Where both give the same set of (section, law) rows the candidate is `verified`; otherwise it is
listed in heldout_labels/disagreements.csv and needs a resolved row (status `adjudicated`) before scoring.
"""
import argparse
import collections
import csv
import re
from pathlib import Path

HERE = Path(__file__).parent
LABELS = HERE / "heldout_labels"


def key(row):
    ref = re.sub(r"\s+", "", row["section_ref"])
    base = re.match(r"\d+[A-Z]{0,2}", ref)
    return (base.group(0) if base else ref, re.sub(r"\s+", " ", row["act_ref"]).strip().lower())


def load(path):
    out = collections.defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        out[(r["judgment_id"], r["cand"])].append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolved", help="CSV of adjudicated rows (same columns as the label files)")
    args = ap.parse_args()
    resolved = load(HERE / args.resolved) if args.resolved else {}
    gold, disagree, stats = [], [], collections.Counter()
    for court in ("kesc", "keca", "kehc"):
        a, b = load(LABELS / f"{court}_A.csv"), load(LABELS / f"{court}_B.csv")
        for cand in sorted(set(a) | set(b), key=lambda c: (c[0], int(c[1]))):
            ra, rb = a.get(cand, []), b.get(cand, [])
            if cand in resolved:
                rows, status = resolved[cand], "adjudicated"
            elif ra and sorted(map(key, ra)) == sorted(map(key, rb)):
                rows, status = ra, "verified"
            else:
                stats["disagree"] += 1
                disagree.append({"judgment_id": cand[0], "cand": cand[1],
                                 "A": "; ".join(f"{r['section_ref']} @ {r['act_ref']}" for r in ra),
                                 "B": "; ".join(f"{r['section_ref']} @ {r['act_ref']}" for r in rb)})
                continue
            stats[status] += 1
            gold += [{"judgment_id": cand[0], "cand": cand[1], "section_ref": r["section_ref"], "act_ref": r["act_ref"],
                      "status": status, "note": r.get("note", "")} for r in rows]
    with open(HERE / "mentions_heldout_gold.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["judgment_id", "cand", "section_ref", "act_ref", "status", "note"])
        w.writeheader()
        w.writerows(gold)
    with open(LABELS / "disagreements.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["judgment_id", "cand", "A", "B"])
        w.writeheader()
        w.writerows(disagree)
    print(f"candidates: {stats['verified']} agreed, {stats['adjudicated']} adjudicated, {stats['disagree']} disagree "
          f"(listed in heldout_labels/disagreements.csv, NOT in the gold file)")


if __name__ == "__main__":
    main()
