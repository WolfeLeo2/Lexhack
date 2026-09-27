"""Agent review of extracted events: the step that turns unverified leads into checked rulings.

Code does what code is sure of (does the quote appear verbatim? what is the section's text?); reviewer agents do the
judging, following pipeline/review_brief.md: read the judgment, decide, and search the web for a later appeal.

  uv run python -m pipeline.review_events export --set benchmark   # the 111 blind-reviewed events (accuracy check)
  uv run python -m pipeline.review_events export --set leads       # every lead the API shows
  uv run python -m pipeline.review_events score                    # benchmark verdicts vs the blind consensus
  uv run python -m pipeline.review_events apply [--dry-run]        # write every saved verdict to citation_events

apply is idempotent and re-applies ALL saved verdicts (benchmark and leads), matched to live events by judgment,
section, type and quote. Run it after every classify_events / verify_events re-run: classify recreates rejected leads.
  accept  -> verified = true, verified_by = REVIEWER (the UI shows "checked by an AI reviewer")
  reject  -> check_verdict = 'fail' (hidden, like the DeepSeek checker's fails)
  unsure  -> left as a lead

Files go to $LEXHACK_DATA/review/<set>/: batch_NN.json (cases), text/<judgment>.txt (the judgment, wrapped so it can
be searched), verdicts/batch_NN.json (written by the reviewers). Nothing here writes to the database.
"""
import argparse
import csv
import json
import re
import textwrap
from pathlib import Path

from crawler.config import data_dir
from ground_truth.eval_events_review import verdict

from .db import connect

GT = Path(__file__).resolve().parent.parent / "ground_truth"
ROUNDS = ["", "_r2", "_r3"]
BATCH = 19
REVIEWER = "agent:claude-opus-5-5 review v1"   # benchmark 2026-09-27: 59/59 accepts right, 59/63 real events kept


def norm(s):
    """Compare quotes the way a reader would: case, spacing, curly quotes and dashes don't matter."""
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def quote_found(text, quote):
    """Every piece of the quote ('a [...] b' has two) must appear in the judgment, in order."""
    t, at = norm(text), 0
    for piece in (p for p in quote.split("[...]") if p.strip()):
        i = t.find(norm(piece), at)
        if i < 0:
            return False
        at = i + len(norm(piece))
    return True


def section_text(conn, act_title, number):
    row = conn.execute("""SELECT p.provision_id, t.text FROM provisions p JOIN acts a USING (act_id)
                          JOIN provision_texts t USING (provision_id) JOIN act_versions v USING (version_id)
                          WHERE a.title = %s AND p.number = %s ORDER BY v.version_date DESC LIMIT 1""",
                       (act_title, number)).fetchone()
    return row or (None, None)


def benchmark_cases(conn):
    """Events both blind reviewers agreed on, WITHOUT their verdicts: the reviewer agents must not see them."""
    out = []
    for sfx in ROUNDS:
        load = lambda n: {r["event_id"]: r for r in csv.DictReader(open(GT / n, encoding="utf-8"))}
        sample, a, b = load(f"events_review_sample{sfx}.csv"), load(f"events_review{sfx}_A.csv"), load(f"events_review{sfx}_B.csv")
        for eid, e in sample.items():
            if verdict(a[eid], e["event_type"]) != verdict(b[eid], e["event_type"]):
                continue
            m = re.match(r"(.+?) s\.(\S+) \(", e["section"])
            pid, stext = section_text(conn, m[1], m[2]) if m else (None, None)
            out.append({**e, "case_id": f"b{sfx or '_r1'}_{eid}", "provision_id": pid, "section_text": stext})
    return out


def key(judgment_id, section, event_type, quote):
    """How a saved verdict finds its event again after classify_events re-creates the rows with new ids."""
    return judgment_id, section, event_type, norm(quote)[:120]


def saved_verdicts():
    """{key: (case, verdict)} over every set reviewed so far."""
    out = {}
    for root in (data_dir() / "review").glob("*"):
        got = {v["case_id"]: v for f in sorted((root / "verdicts").glob("*.json")) for v in json.loads(f.read_text())}
        for f in sorted(root.glob("batch_*.json")):
            for c in json.loads(f.read_text()):
                if c["case_id"] in got:
                    out[key(c["judgment_id"], c["section"], c["event_type"], c["operative_quote"])] = (c, got[c["case_id"]])
    return out


def lead_cases(conn):
    rows = conn.execute("""
        SELECT e.event_id, e.judgment_id, j.title, j.court, a.title || ' s.' || p.number || ' (' || coalesce(p.heading, '') || ')',
               e.event_type, e.scope, coalesce(e.scope_text, ''), coalesce(e.subsection, ''), e.operative_quote,
               coalesce(e.source_paragraph, ''), j.raw_path, e.provision_id, e.effective_date::text
        FROM citation_events e JOIN judgments j USING (judgment_id) JOIN provisions p USING (provision_id) JOIN acts a USING (act_id)
        WHERE NOT e.verified AND e.check_verdict IS DISTINCT FROM 'fail' ORDER BY e.event_id""").fetchall()
    cols = ["event_id", "judgment_id", "title", "court", "section", "event_type", "scope", "scope_text", "subsection",
            "operative_quote", "source_paragraph", "raw_path", "provision_id", "effective_date"]
    out = []
    for r in rows:
        e = dict(zip(cols, r))
        e["event_id"] = str(e["event_id"])
        e["section_text"] = conn.execute("""SELECT t.text FROM provision_texts t JOIN act_versions v USING (version_id)
            WHERE t.provision_id = %s ORDER BY v.version_date DESC LIMIT 1""", (e["provision_id"],)).fetchone()[0]
        out.append({**e, "case_id": f"lead_{e['event_id']}"})
    done = saved_verdicts()
    todo = [c for c in out if key(c["judgment_id"], c["section"], c["event_type"], c["operative_quote"]) not in done]
    print(f"{len(out)} leads; {len(out) - len(todo)} already reviewed (benchmark or earlier batches); {len(todo)} to review")
    return todo


def export(which):
    root = data_dir() / "review" / which
    (root / "text").mkdir(parents=True, exist_ok=True)
    (root / "verdicts").mkdir(exist_ok=True)
    with connect() as conn:
        cases = benchmark_cases(conn) if which == "benchmark" else lead_cases(conn)
    for c in cases:
        j = json.loads((data_dir() / c["raw_path"]).read_text(encoding="utf-8"))
        text = j.get("text") or ""
        name = c["judgment_id"].replace("/", "_") + ".txt"
        path = root / "text" / name
        if not path.exists():
            path.write_text(f"{j.get('title')}\n{j.get('url')}\n\n" + "\n".join(textwrap.wrap(text, 140)), encoding="utf-8")
        c.update(judgment_text=str(path), judgment_url=j.get("url"), quote_found=quote_found(text, c["operative_quote"]))
        del c["raw_path"]
    for n in range(0, len(cases), BATCH):
        (root / f"batch_{n // BATCH:02d}.json").write_text(json.dumps(cases[n:n + BATCH], indent=1, ensure_ascii=False),
                                                            encoding="utf-8")
    print(f"{len(cases)} cases in {-(-len(cases) // BATCH)} batches -> {root}; "
          f"quote not found verbatim: {sum(not c['quote_found'] for c in cases)}")


def apply(dry_run):
    done = saved_verdicts()
    with connect() as conn:
        rows = conn.execute("""
            SELECT e.event_id, e.judgment_id, a.title || ' s.' || p.number || ' (' || coalesce(p.heading, '') || ')',
                   e.event_type, e.operative_quote, e.source_paragraph, e.verified, j.raw_path
            FROM citation_events e JOIN judgments j USING (judgment_id) JOIN provisions p USING (provision_id)
            JOIN acts a USING (act_id) WHERE e.method = 'extracted'""").fetchall()
        n = {"accept": 0, "reject": 0, "unsure": 0, "better_quote": 0}
        for eid, jid, section, etype, quote, para, verified, raw in rows:
            hit = done.get(key(jid, section, etype, quote))
            if not hit:
                continue
            c, v = hit
            n[v["decision"]] += 1
            if dry_run or v["decision"] == "unsure":
                continue
            if v["decision"] == "reject":
                conn.execute("UPDATE citation_events SET check_verdict = 'fail', check_reason = %s WHERE event_id = %s",
                             (f"{REVIEWER}: {v['reason']}"[:1000], eid))
                continue
            new_quote, note = quote, f"{REVIEWER}: {v['reason']}"
            better = (v.get("better_quote") or "").strip()
            # the reviewer's better quote replaces ours only if code finds it verbatim in the judgment too
            if better and quote_found(json.loads((data_dir() / raw).read_text(encoding="utf-8"))["text"] or "", better):
                new_quote, note = better, note + f" | pipeline quote was: {quote}"
                n["better_quote"] += 1
            conn.execute("""UPDATE citation_events SET verified = true, verified_by = %s, operative_quote = %s,
                            source_paragraph = coalesce(nullif(%s, ''), source_paragraph),
                            notes = coalesce(notes || ' | ', '') || %s WHERE event_id = %s AND NOT verified""",
                         (REVIEWER, new_quote, (v.get("paragraph") or "").strip(), note[:2000], eid))
        if not dry_run:
            conn.commit()
    print(f"{'would apply' if dry_run else 'applied'}: {n} (matched {sum(n[k] for k in ('accept', 'reject', 'unsure'))} "
          f"live events to saved verdicts)")


def score():
    root = data_dir() / "review" / "benchmark"
    got = {v["case_id"]: v for f in sorted((root / "verdicts").glob("*.json")) for v in json.loads(f.read_text())}
    cases = [c for f in sorted(root.glob("batch_*.json")) for c in json.loads(f.read_text())]
    labels = {}
    for sfx in ROUNDS:
        load = lambda n: {r["event_id"]: r for r in csv.DictReader(open(GT / n, encoding="utf-8"))}
        sample, a = load(f"events_review_sample{sfx}.csv"), load(f"events_review{sfx}_A.csv")
        for eid, e in sample.items():
            labels[f"b{sfx or '_r1'}_{eid}"] = verdict(a[eid], e["event_type"]) == "right"
    tp = fp = fn = tn = unsure = 0
    misses = []
    for c in cases:
        v = got.get(c["case_id"])
        if not v:
            continue
        right = labels[c["case_id"]]
        if v["decision"] == "unsure":
            unsure += 1
            continue
        acc = v["decision"] == "accept"
        tp += acc and right; fp += acc and not right; fn += (not acc) and right; tn += (not acc) and not right
        if acc != right:
            misses.append(f"{'ACCEPTED WRONG' if acc else 'REJECTED RIGHT'} {c['case_id']} {c['event_type']} {c['section'][:45]}: {v['reason'][:160]}")
    done = tp + fp + fn + tn
    print(f"{len(got)}/{len(cases)} reviewed; {unsure} unsure (left as leads)")
    print(f"agreement with the blind consensus: {tp + tn}/{done} = {(tp + tn) / max(done, 1):.1%}")
    print(f"precision of accepts: {tp}/{tp + fp} = {tp / max(tp + fp, 1):.1%}   (the number that decides whether we trust it)")
    print(f"real events kept: {tp}/{tp + fn} = {tp / max(tp + fn, 1):.1%}")
    print(*misses, sep="\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export").add_argument("--set", choices=["benchmark", "leads"], required=True)
    sub.add_parser("score")
    sub.add_parser("apply").add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "export":
        export(args.set)
    elif args.cmd == "apply":
        apply(args.dry_run)
    else:
        score()
