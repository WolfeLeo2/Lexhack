"""Score pipeline.extract_citations against the hand-labelled sample. Runs the current extractor code on the
parsed judgment text (not the database rows), so it measures the code as it is now.

  uv run python -m ground_truth.eval_mentions            # summary
  uv run python -m ground_truth.eval_mentions --errors   # also list every miss and wrong Act

A gold citation matches an extracted one in the same judgment when the extracted citation's span covers the gold
candidate's offset and the section numbers agree (sub-provisions ignored). Only the annotated span of each judgment
counts. "Act" scoring, on matched pairs:
  held Act / repealed Constitution  -> the extractor must name the same one
  other law                         -> the extractor must name some other (non-held) law; names compared loosely
  gold 'unknown'                    -> not scored
An extracted citation with no Act (act_ref NULL) is 'unresolved': left for the LLM pass, not counted as wrong.
"""
import argparse
import collections
import csv
import json
import re
from pathlib import Path

from crawler.config import data_dir
from pipeline.db import connect
from pipeline.extract_citations import CANONICAL, REPEALED_CONSTITUTION, extract

HERE = Path(__file__).parent
HELD = set(CANONICAL.values()) | {REPEALED_CONSTITUTION}


def base(ref):
    m = re.match(r"\d+[A-Z]{0,2}", ref)
    return m.group(0) if m else ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--errors", action="store_true")
    ap.add_argument("--llm", action="store_true", help="also apply pipeline.llm_resolve to unresolved citations")
    args = ap.parse_args()
    if args.llm:
        from crawler.config import require_env
        from pipeline.llm_resolve import NOT_CITATION, UNKNOWN, resolve_judgment
        api_key, cache = require_env("GEMINI_API_KEY"), data_dir() / "cache" / "llm"
        cache.mkdir(parents=True, exist_ok=True)

    cands = list(csv.DictReader(open(HERE / "mentions_candidates.csv", encoding="utf-8")))
    offset = {(c["judgment_id"], c["cand"]): int(c["char_start"]) for c in cands if c["cand"] != "-1"}
    spans = {}   # judgment -> (first, last) candidate offset: extractions outside it weren't annotated
    for (jid, _), off in offset.items():
        lo, hi = spans.get(jid, (off, off))
        spans[jid] = (min(lo, off), max(hi, off))
    spans.update({c["judgment_id"]: (0, -1) for c in cands if c["cand"] == "-1"})
    gold = collections.defaultdict(list)   # judgment -> [(offset, base number, act_ref, row)]
    for g in csv.DictReader(open(HERE / "mentions_gold.csv", encoding="utf-8")):
        if g["section_ref"] != "-":
            gold[g["judgment_id"]].append((offset[(g["judgment_id"], g["cand"])], base(g["section_ref"]), g["act_ref"], g))
    with connect() as conn:
        rows = conn.execute("""SELECT judgment_id, raw_path, decision_date, title FROM judgments
                               WHERE judgment_id = ANY(%s)""", (list(spans),)).fetchall()

    s, errors = collections.Counter(), []
    for jid, raw_path, ddate, title in rows:
        text = json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or ""
        lo, hi = spans[jid]
        every = list(extract(text, ddate))
        if args.llm:
            answers, _ = resolve_judgment(title, text, every, api_key, cache)
            for x in every:
                law, conf = answers.get((x["char_start"], x["char_end"]), (None, None))
                if x["act_ref"] in (None, "the Act", "the Code") and law not in (None, UNKNOWN, NOT_CITATION):
                    x["act_ref"] = law
        ext = [x for x in every if x["char_end"] > lo and x["char_start"] <= hi]
        used = set()
        for off, num, act, g in gold[jid]:
            s["gold"] += 1
            hit = next((i for i, x in enumerate(ext) if i not in used and x["char_start"] <= off < x["char_end"]
                        and base(x["section_ref"]) == num), None)
            if hit is None:
                s["missed"] += 1
                errors.append(f"MISS  {jid} c{g['cand']} {g['section_ref']} @ {act}: ...{text[off:off + 90]}")
                continue
            used.add(hit)
            s["matched"] += 1
            got = ext[hit]["act_ref"]
            if act == "unknown":
                s["act_unscored"] += 1
            elif got is None or got in ("the Act", "the Code"):
                s["act_unresolved"] += 1
            elif (act in HELD and got == act) or (act not in HELD and got not in HELD):
                s["act_right"] += 1
            else:
                s["act_wrong"] += 1
                errors.append(f"WRONG {jid} c{g['cand']} {g['section_ref']}: gold {act!r}, got {got!r}")
        for i, x in enumerate(ext):
            s["extracted"] += 1
            if i not in used:
                s["spurious"] += 1
                errors.append(f"EXTRA {jid} {x['section_ref']} @ {x['act_ref']}: {x['raw_text'][:90]}")

    p = s["matched"] / s["extracted"] if s["extracted"] else 0
    r = s["matched"] / s["gold"] if s["gold"] else 0
    scored = s["act_right"] + s["act_wrong"] + s["act_unresolved"]
    print(f"{len(rows)} judgments, {s['gold']} gold citations, {s['extracted']} extracted")
    print(f"detection: precision {p:.1%} ({s['matched']}/{s['extracted']}), recall {r:.1%} ({s['matched']}/{s['gold']}), "
          f"{s['missed']} missed, {s['spurious']} spurious")
    if scored:
        print(f"Act, of {scored} matched citations: {s['act_right']} right ({s['act_right'] / scored:.1%}), "
              f"{s['act_wrong']} wrong ({s['act_wrong'] / scored:.1%}), {s['act_unresolved']} unresolved "
              f"({s['act_unresolved'] / scored:.1%}, for the LLM pass); {s['act_unscored']} gold 'unknown' not scored")
    unverified = sum(g["status"] == "draft" for g in csv.DictReader(open(HERE / "mentions_gold.csv", encoding="utf-8")))
    if unverified:
        print(f"UNVERIFIED: {unverified} gold rows are still drafts")
    if args.errors:
        print("\n".join(errors))


if __name__ == "__main__":
    main()
