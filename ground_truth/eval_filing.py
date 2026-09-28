"""Score the filing checker (spec 2a).

  uv run python -m ground_truth.eval_filing --set dev      # eKLR matching vs the agents' gold, current thresholds
  uv run python -m ground_truth.eval_filing --tune         # grid search on dev only
  uv run python -m ground_truth.eval_filing --set test     # once, after tuning: the number to quote
  uv run python -m ground_truth.eval_filing --planted      # planted errors + false alarms (no labels needed)
"""
import argparse
import csv
import itertools
import json
import random
import re
from pathlib import Path

from api import filing
from crawler.config import data_dir
from pipeline.db import connect

HERE = Path(__file__).resolve().parent
MUTATIONS = ("drop a word", "swap a word", "insert not")


def load(name):
    items = {r["item_id"]: r for r in csv.DictReader(open(HERE / f"filing_{name}_items.csv", encoding="utf-8"))}
    gold_file = HERE / f"filing_{name}_gold.csv"
    gold = ({r["item_id"]: r["gold"] for r in csv.DictReader(open(gold_file, encoding="utf-8"))}
            if gold_file.exists() else {})
    return items, gold


def judgment_text(conn, jid, _raw={}):
    if not _raw:
        _raw.update(conn.execute("SELECT judgment_id, raw_path FROM judgments").fetchall())
    return json.loads((data_dir() / _raw[jid]).read_text(encoding="utf-8"))["text"] or ""


def answers(conn, items):
    """{item_id: (result, [judgment ids])} from the full checker run on each citing judgment (quote tie-break
    included), matched to items by character offset."""
    out, by_judgment = {}, {}
    for it in items.values():
        by_judgment.setdefault(it["judgment_id"], []).append(it)
    for jid, its in by_judgment.items():
        found = {f["char_start"]: f["case"] for f in filing.case_findings(conn, judgment_text(conn, jid))
                 if f["case"]["form"] == "eklr"}
        for it in its:
            c = found[int(it["char_start"])]
            ids = [c["judgment"]["judgment_id"]] if c["judgment"] else [k["judgment_id"] for k in c["candidates"]]
            out[it["item_id"]] = (c["result"], ids)
    return out


def right_id(jid, gold):
    """Gold may list alternatives ('a|b'): one ruling Kenya Law published twice, either id is right."""
    return jid in gold.split("|")


def metrics(ans, gold):
    held = [i for i, g in gold.items() if g != "not_held"]
    found = [i for i in gold if ans[i][0] == "found"]
    right = [i for i in found if right_id(ans[i][1][0], gold[i])]
    possible = [i for i in held if ans[i][0] == "possible_match"]
    return {
        "items": len(gold), "gold held": len(held),
        "found precision": f"{len(right)}/{len(found)}",
        "wrong-case rate": f"{len(found) - len(right)}/{len(gold)}",
        "coverage": f"{len(right)}/{len(held)}",
        "possible-match hit": f"{sum(1 for i in possible if any(right_id(j, gold[i]) for j in ans[i][1]))}/{len(possible)}",
        "false found on not-held": f"{sum(1 for i in found if gold[i] == 'not_held')}/{len(gold) - len(held)}",
    }


def tune(conn, items, gold):
    """Grid over the thresholds on dev, matcher only (no quote tie-break). Objective: fewest wrong cases, then most
    coverage."""
    idx = filing.title_index(conn)
    ctx = {}
    for i in gold:
        it = items[i]
        # the context starts 300 characters before the citation (fewer near the start of a judgment)
        e = min(filing.find_eklr(it["context"]),
                key=lambda c: abs(c["char_start"] - min(300, int(it["char_start"]))))
        ctx[i] = (int(it["year"]), e["cited_name"], e["case_number"])
    best = None
    for ms in (2.0, 3.0, 4.0, 5.0, 6.0):
        ranked = {i: filing.rank_eklr(idx, *ctx[i], min_shared=ms) for i in gold}
        for fs, mg, ps in itertools.product((0.6, 0.7, 0.8, 0.9), (0.1, 0.2, 0.3, 0.4), (0.3, 0.4, 0.5, 0.6)):
            d = {i: filing.decide(r, fs, mg, ps) for i, r in ranked.items()}
            wrong = sum(1 for i, x in d.items() if x["result"] == "found" and not right_id(x["rows"][0][1], gold[i]))
            cover = sum(1 for i, x in d.items() if x["result"] == "found" and right_id(x["rows"][0][1], gold[i]))
            key = (wrong, -cover)
            if best is None or key < best[0]:
                best = (key, dict(MIN_SHARED=ms, FOUND_SCORE=fs, FOUND_MARGIN=mg, POSSIBLE_SCORE=ps))
    print("best on dev (wrong, -coverage):", best[0], best[1])


def mutate(words, how, rng, pool):
    w = list(words)
    k = rng.randrange(2, len(w) - 2)
    if how == "drop a word":
        del w[k]
    elif how == "swap a word":
        w[k] = rng.choice([p for p in pool if p.lower() != w[k].lower()])
    else:
        w.insert(k, "not")
    return w


def planted(conn):
    """Errors with known answers, planted in text built around real citations (no labels needed), then the
    false-alarm rate on real, unmodified neutral citations in the benchmark judgments."""
    rng, tally = random.Random(2026), {}
    rows = conn.execute("""SELECT neutral_citation, judgment_id, title, raw_path, extract(year FROM decision_date)::int
                           FROM judgments WHERE duplicate_of IS NULL AND has_full_text AND neutral_citation IS NOT NULL
                           ORDER BY judgment_id""").fetchall()
    sample = rng.sample(rows, 150)

    def count(kind, hit):
        tally.setdefault(kind, [0, 0])
        tally[kind][0] += bool(hit)
        tally[kind][1] += 1

    def first(text):
        return filing.check(conn, text)["findings"][0]

    for nc, jid, title, rp, y in sample[:50]:
        mine = filing.name_tokens(filing.party_part(title))
        other = rng.choice([r for r in rows if r[4] == y and not filing.name_tokens(filing.party_part(r[2])) & mine])
        count("wrong name -> name_mismatch",
              first(f"In {filing.party_part(other[2])} {nc}, the court held so.")["case"]["result"] == "name_mismatch")
        count("control: right name -> found",
              first(f"In {filing.party_part(title)} {nc}, the court held so.")["case"]["result"] == "found")
    for nc, jid, title, rp, y in sample[50:120]:
        text = json.loads((data_dir() / rp).read_text(encoding="utf-8"))["text"] or ""
        sents = [s.split() for s in re.split(r"(?<=[.;])\s+", text) if 14 <= len(s.split()) <= 30]
        if not sents:
            continue
        words, how = rng.choice(sents), rng.choice(MUTATIONS)
        pool = [w for s in sents for w in s if w.isalpha() and len(w) > 3]
        q = " ".join(mutate(words, how, rng, pool)).replace('"', "'")
        f = first(f"In {filing.party_part(title)} {nc}, it was held that \"{q}\".")
        count(f"altered quote ({how}) -> close or not_found",
              f["quotes"] and f["quotes"][0]["result"] in ("close", "not_found"))
    for nc, jid, title, rp, y in sample[120:150]:
        court = re.search(r"\] (\w+) ", nc)[1]
        top = max(int(r[0].split()[2]) for r in rows if r[4] == y and f"] {court} " in r[0])
        count("invented number -> not_in_collection",
              first(f"In Doe v Roe [{y}] {court} {top + 10000} (KLR), so held.")["case"]["result"] == "not_in_collection")
    for k, (hit, n) in tally.items():
        print(f"{k:>48}: {hit}/{n}")

    items = {**load("dev")[0], **load("test")[0]}
    flagged, total = [], 0
    for jid in sorted({it["judgment_id"] for it in items.values()}):
        text = judgment_text(conn, jid)
        for f in filing.case_findings(conn, text):
            c = f["case"]
            if c["form"] == "neutral" and c["result"] in ("found", "name_mismatch"):
                total += 1
                if c["result"] == "name_mismatch":
                    flagged.append({"judgment_id": jid, "citation": f["raw_text"], "cited_name": c["cited_name"],
                                    "our_title": c["judgment"]["title"],
                                    "context": re.sub(r"\s+", " ", text[max(0, f["char_start"] - 250):f["char_end"] + 40])})
    print(f"{'real neutral citations flagged name_mismatch':>48}: {len(flagged)}/{total}")
    (data_dir() / "review" / "filing" / "false_alarms.json").write_text(json.dumps(flagged, indent=1), encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", default="dev")
    p.add_argument("--tune", action="store_true")
    p.add_argument("--planted", action="store_true")
    a = p.parse_args()
    with connect() as conn:
        if a.planted:
            planted(conn)
            return
        items, gold = load("dev" if a.tune else a.set)
        if not gold:
            raise SystemExit("no gold yet: run ground_truth.filing_merge first")
        if a.tune:
            tune(conn, items, gold)
        else:
            for k, v in metrics(answers(conn, items), gold).items():
                print(f"{k:>24}: {v}")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--check"]:
        m = metrics({"1": ("found", ["a"]), "2": ("found", ["x"]), "3": ("possible_match", ["b", "c"])},
                    {"1": "a|z", "2": "y", "3": "c"})
        assert (m["found precision"], m["wrong-case rate"], m["possible-match hit"]) == ("1/2", "1/3", "1/1"), m
        print("eval check passed")
    else:
        main()
