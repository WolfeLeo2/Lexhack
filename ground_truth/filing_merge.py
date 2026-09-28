"""Merge the labellers' answers (spec 2a): A and B label blind; where they differ (or either is 'unsure'), C decides.

  uv run python -m ground_truth.filing_merge dev            # writes labels_{A,B,C}.csv, lists items C must label
  uv run python -m ground_truth.filing_merge dev --final    # after C: writes filing_dev_gold.csv
  uv run python -m ground_truth.filing_merge --check        # self-check of the merge rule

Audit (labels/<set>_audit_*.json): an Opus labeller re-checked every gold not_held with a better search brief. An audit
answer replaces not_held only when it names a judgment (the first labellers' misses were omissions: capitalised titles,
dropped first names); it never turns a match into not_held.
"""
import csv
import json
import sys
from pathlib import Path

from crawler.config import data_dir

HERE = Path(__file__).resolve().parent


def load(name, who):
    out = {}
    for f in sorted((data_dir() / "review" / "filing" / "labels").glob(f"{name}_{who}_*.json")):
        for a in json.loads(f.read_text(encoding="utf-8")):
            out[a["item_id"]] = a["label"].strip()
    return out


def merge(items, a, b, c):
    """-> (gold rows, items C must label, items missing from A or B)."""
    missing = [i for i in items if i not in a or i not in b]
    need_c = [i for i in items if i not in missing and (a[i] != b[i] or "unsure" in (a[i], b[i]))]
    gold = [{"item_id": i, "gold": a[i] if i not in need_c else c.get(i, ""), "agreed": i not in need_c}
            for i in items if i not in missing]
    return gold, need_c, missing


def apply_audit(gold, audit):
    for g in gold:
        a = audit.get(g["item_id"], "not_held")
        if g["gold"] == "not_held" and a not in ("not_held", "unsure", ""):
            g["gold"], g["agreed"] = a, False
    return gold


def main():
    name, final = sys.argv[1], "--final" in sys.argv
    items = [r["item_id"] for r in csv.DictReader(open(HERE / f"filing_{name}_items.csv", encoding="utf-8"))]
    a, b, c = load(name, "A"), load(name, "B"), load(name, "C")
    gold, need_c, missing = merge(items, a, b, c)
    if missing:
        raise SystemExit(f"{len(missing)} items unlabelled by A or B, e.g. {missing[:5]}; re-run those batches")
    for who, labels in (("A", a), ("B", b), ("C", c)):
        with open(HERE / f"filing_{name}_labels_{who}.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([("item_id", "label")] + sorted(labels.items()))
    print(f"A/B agreement {len(items) - len(need_c)}/{len(items)}; C must label {len(need_c)}")
    (data_dir() / "review" / "filing" / f"{name}_need_c.json").write_text(json.dumps(need_c), encoding="utf-8")
    audit = load(name, "audit")
    if final and audit:
        before = sum(g["gold"] == "not_held" for g in gold)
        gold = apply_audit(gold, audit)
        print(f"audit: {before - sum(g['gold'] == 'not_held' for g in gold)} of {before} not_held items now name a judgment")
    if final:
        if any(not g["gold"] or g["gold"] == "unsure" for g in gold):
            raise SystemExit("C has not labelled every disagreement (or answered unsure): finish C first")
        with open(HERE / f"filing_{name}_gold.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["item_id", "gold", "agreed"])
            w.writeheader()
            w.writerows(gold)
        print("wrote", f"filing_{name}_gold.csv")


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        g, need, miss = merge(["1", "2", "3"], {"1": "x", "2": "x"}, {"1": "x", "2": "y"}, {"2": "y"})
        assert (need, miss, g[1]["gold"]) == (["2"], ["3"], "y"), (need, miss, g)
        g = apply_audit([{"item_id": "1", "gold": "not_held", "agreed": True}, {"item_id": "2", "gold": "x", "agreed": True},
                         {"item_id": "3", "gold": "not_held", "agreed": True}], {"1": "y", "2": "not_held", "3": "unsure"})
        assert [r["gold"] for r in g] == ["y", "x", "not_held"], g
        print("merge check passed")
    else:
        main()
