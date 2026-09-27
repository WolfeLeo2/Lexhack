"""Draw the hand-checked sample for scoring citation extraction (step 5). Deterministic (fixed seed).

  uv run python -m ground_truth.mention_sample

Writes ground_truth/mentions_candidates.csv: every place in the sampled judgments where a citation *could* be,
found by a deliberately broader pattern than the extractor's, so the answer key doesn't inherit its blind spots.
Each candidate is then labelled by hand in mentions_gold.csv (see decisions in mentions_README.md).

Sample: 10 judgments per court (kesc, keca, kehc) with text. A judgment with more than WINDOW candidates is
annotated on one random contiguous window of WINDOW candidates; scoring counts only that span.
"""
import csv
import json
import random
import re
from pathlib import Path

from crawler.config import data_dir
from pipeline.db import connect

HERE = Path(__file__).parent
SEED, PER_COURT, WINDOW, CTX = 2026, 10, 40, 220
BROAD = re.compile(r"(?i)(sections?|secs?\.?|ss?\.|articles?|arts?\.?)\s*\d")


def main():
    with connect() as conn:
        rows = conn.execute("""SELECT judgment_id, raw_path FROM judgments WHERE has_full_text
                               ORDER BY judgment_id""").fetchall()
    rnd = random.Random(SEED)
    sample = []
    for court in ("kesc", "keca", "kehc"):
        sample += rnd.sample([r for r in rows if f"/{court}/" in r[0]], PER_COURT)
    out = []
    for jid, raw_path in sample:
        text = json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or ""
        cands = list(BROAD.finditer(text))
        lo = rnd.randrange(len(cands) - WINDOW + 1) if len(cands) > WINDOW else 0
        cands = cands[lo:lo + WINDOW]
        span = (cands[0].start(), cands[-1].end() + 200) if cands else (0, 0)
        for i, m in enumerate(cands):
            out.append({"judgment_id": jid, "cand": i, "char_start": m.start(), "span_start": span[0],
                        "span_end": span[1],
                        "context": re.sub(r"\s+", " ", text[max(0, m.start() - CTX):m.start() + CTX])})
        if not cands:
            out.append({"judgment_id": jid, "cand": -1, "char_start": "", "span_start": 0, "span_end": 0,
                        "context": "(no candidates)"})
    with open(HERE / "mentions_candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"{len(sample)} judgments, {sum(r['cand'] >= 0 for r in out)} candidates -> mentions_candidates.csv")


if __name__ == "__main__":
    main()
