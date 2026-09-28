"""Filing benchmark sample (spec 2a): judgments with 2+ eKLR citations, split into dev and test; every eKLR citation in
them is an item. Also writes each needed year's list of titles and the labelling batches.

  uv run python -m ground_truth.filing_sample              # dev + test
  uv run python -m ground_truth.filing_sample test2        # a fresh held-out set: the next 40 of the same shuffle

test2 was added after test had been scored once and the matcher then changed (review fixes): it gives a clean number.
"""
import sys
import csv
import json
import random
import re
from pathlib import Path

from api.filing import find_eklr
from crawler.config import data_dir
from pipeline.db import connect

HERE = Path(__file__).resolve().parent
SEED, PER_SET, BATCH = 2026, 40, 50
DEMO = {"ke/judgment/kehc/2017/8382", "ke/judgment/kesc/2017/2", "ke/judgment/kesc/2021/31",
        "ke/judgment/kehc/2006/2628", "ke/judgment/kehc/2006/2629"}


def earlier_benchmarks():
    return {r["judgment_id"] for f in ("mentions_gold.csv", "mentions_heldout_gold.csv")
            for r in csv.DictReader(open(HERE / f, encoding="utf-8"))}


def main():
    skip = DEMO | earlier_benchmarks()
    with connect() as conn:
        rows = conn.execute("""SELECT judgment_id, raw_path FROM judgments
                               WHERE duplicate_of IS NULL AND has_full_text ORDER BY judgment_id""").fetchall()
        titles = conn.execute("""SELECT judgment_id, decision_date::text, coalesce(case_number, ''), title, raw_path,
                                        extract(year FROM decision_date)::int
                                 FROM judgments WHERE duplicate_of IS NULL ORDER BY title""").fetchall()
    pool = []
    for jid, raw_path in rows:
        if jid in skip:
            continue
        text = json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or ""
        cites = find_eklr(text)
        if len(cites) >= 2:
            pool.append((jid, raw_path, text, cites))
    random.Random(SEED).shuffle(pool)
    out = data_dir() / "review" / "filing"
    (out / "batches").mkdir(parents=True, exist_ok=True)
    years = set()
    sets = (("dev", pool[:PER_SET]), ("test", pool[PER_SET:2 * PER_SET]), ("test2", pool[2 * PER_SET:3 * PER_SET]))
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, part in [x for x in sets if (x[0] == only if only else x[0] != "test2")]:
        items = []
        for jid, raw_path, text, cites in part:
            for c in cites:
                items.append({"item_id": f"{name}-{len(items) + 1:04d}", "judgment_id": jid,
                              "char_start": c["char_start"], "raw_text": c["raw_text"], "year": c["year"],
                              "context": re.sub(r"\s+", " ", text[max(0, c["char_start"] - 300):c["char_end"] + 60]),
                              "citing_judgment_text": str(data_dir() / raw_path)})
                years.add(c["year"])
        with open(HERE / f"filing_{name}_items.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["item_id", "judgment_id", "char_start", "raw_text", "year", "context"])
            w.writeheader()
            w.writerows({k: it[k] for k in w.fieldnames} for it in items)
        for k in range(0, len(items), BATCH):
            batch = [{**{x: it[x] for x in ("item_id", "context", "year", "citing_judgment_text")},
                      "titles_file": str(out / f"titles_{it['year']}.tsv")} for it in items[k:k + BATCH]]
            (out / "batches" / f"{name}_{k // BATCH + 1}.json").write_text(json.dumps(batch, indent=1), encoding="utf-8")
        print(name, len(part), "judgments", len(items), "items")
    for y in sorted(years):
        with open(out / f"titles_{y}.tsv", "w", encoding="utf-8") as f:
            f.write("judgment_id\tdecision_date\tcase_number\ttitle\ttext_path\n")
            for jid, d, cn, t, rp, ty in titles:
                if ty == y:
                    f.write(f"{jid}\t{d}\t{cn}\t{t}\t{data_dir() / rp}\n")


if __name__ == "__main__":
    main()
