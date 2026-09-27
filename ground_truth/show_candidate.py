"""Print the text around sampled candidates, for labelling and verifying mentions_gold.csv.

  uv run python -m ground_truth.show_candidate ke/judgment/kesc/2017/37            # every candidate, short context
  uv run python -m ground_truth.show_candidate ke/judgment/kesc/2017/37 5 --before 3000   # one candidate, wide context
  uv run python -m ground_truth.show_candidate ke/judgment/kesc/2017/37 --full      # the whole judgment text
"""
import argparse
import csv
import json
import re
from pathlib import Path

from crawler.config import parsed_dir

HERE = Path(__file__).parent


def judgment_text(judgment_id):   # latest expression of the judgment, as load_judgments stores it
    stem = "akn_" + judgment_id.replace("/", "_") + "_eng@"
    files = sorted(f for f in (parsed_dir() / "judgment").glob(stem + "*.json") if "source" not in f.name)
    return json.loads(files[-1].read_text(encoding="utf-8"))["text"] or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("judgment_id")
    ap.add_argument("cand", nargs="?", type=int)
    ap.add_argument("--before", type=int, default=300)
    ap.add_argument("--after", type=int, default=200)
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    text = judgment_text(args.judgment_id)
    if args.full:
        print(text)
        return
    for c in csv.DictReader(open(HERE / "mentions_candidates.csv", encoding="utf-8")):
        if c["judgment_id"] != args.judgment_id or c["cand"] == "-1":
            continue
        if args.cand is not None and int(c["cand"]) != args.cand:
            continue
        s = int(c["char_start"])
        flat = lambda t: re.sub(r"\s+", " ", t)
        print(f"c{c['cand']} @{s}: ...{flat(text[max(0, s - args.before):s])} [[{flat(text[s:s + args.after])}]]\n")


if __name__ == "__main__":
    main()
