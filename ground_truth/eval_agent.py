"""Score the research agent (api/agent.py) on a question set (README §7c).

  uv run python -m ground_truth.eval_agent --facts          # what the question writer works from
  uv run python -m ground_truth.eval_agent --selftest       # the scoring rules on hand-made answers
  uv run python -m ground_truth.eval_agent --set dev        # run + score; answers for the grader
  uv run python -m ground_truth.eval_agent --set heldout    # once, after tuning on dev

Scored in code: invented references (the headline), section found, key rulings cited, not-held wording. The judgement
calls (contradicts the status, advice, verdict, lead as status) go to the answer-grader agent.
"""
import argparse
import csv
import json
import os
import re
from pathlib import Path

from api import agent, main
from api.status import provision_status

HERE = Path(__file__).parent
OUT = Path(os.environ["LEXHACK_DATA"]) / "review" / "agent"
NOT_HELD_OK = re.compile(r"not (?:in|part of|held in) (?:Hakiki'?s|our|the) collection|Hakiki does not (?:hold|have)"
                         r"|Hakiki doesn'?t (?:hold|have)", re.I)
NOT_HELD_BAD = re.compile(r"\b(?:does not|doesn'?t|did not|didn'?t) exist|\bfake\b|\binvalid\b|fabricated", re.I)


def split(s):
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def score(q, out, key_ids, event_section):
    """q: a question row; out: agent.run's result; key_ids: event_ids (str) the answer must cite; event_section:
    {event_id: provision_id} for every event the answer references."""
    rs = agent.refs(out["answer"])
    seen = {(k, v) for k, vs in out["seen"].items() for v in vs}
    cited_events = {v for k, v in rs if k == "event"}
    cited_sections = {v for k, v in rs if k == "section"} | {event_section.get(v) for v in cited_events}
    s = {"invented": sum((k, v) not in seen for k, v in rs),
         "section_found": all(p in cited_sections for p in split(q["expected_provisions"])),
         "key_rulings": key_ids <= cited_events}
    if q["expect_not_held"] == "yes":
        s["not_held_wording"] = bool(NOT_HELD_OK.search(out["answer"])) and not NOT_HELD_BAD.search(out["answer"])
    return s


def selftest():
    q = {"expected_provisions": "p1", "expect_not_held": "yes"}
    out = {"answer": "[[section:p1]] [[event:7]] [[event:8]] It is not in Hakiki's collection.",
           "seen": {"section": ["p1"], "event": ["7"], "judgment": []}}
    s = score(q, out, {"7"}, {"7": "p1"})
    assert s == {"invented": 1, "section_found": True, "key_rulings": True, "not_held_wording": True}, s
    out["answer"] = "That case does not exist. [[event:7]]"
    s = score(q, out, {"7", "9"}, {"7": "p1"})
    assert s["not_held_wording"] is False and s["key_rulings"] is False and s["section_found"] is True, s
    q = {"expected_provisions": "p2", "expect_not_held": ""}
    assert score(q, out, set(), {"7": "p1"}) == {"invented": 0, "section_found": False, "key_rulings": True}
    print("selftest ok")


def facts():
    """Every section with a checked ruling, its status and rulings: the question writer's source."""
    with main.POOL, main.db() as conn:
        pids = [r[0] for r in conn.execute("SELECT DISTINCT provision_id FROM citation_events WHERE verified "
                                           "AND judgment_id IS NOT NULL ORDER BY 1")]
        rows = []
        for p in pids:
            res = provision_status(conn, p)
            head = conn.execute("SELECT a.title, p.number, p.heading FROM provisions p JOIN acts a USING (act_id) "
                                "WHERE provision_id = %s", (p,)).fetchone()
            rows.append({"provision_id": p, "act": head[0], "number": head[1], "heading": head[2],
                         "status": res["status"],
                         "rulings": [{k: e[k] for k in ("event_id", "event_key", "event_type", "scope", "court", "title",
                                                        "neutral_citation", "effective_date", "state")}
                                     for e in res["history"] if e.get("judgment_id")]})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "facts.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} sections -> {OUT / 'facts.json'}")


def key_event_ids(conn, keys):
    """event_keys (answer key, e.g. 'E07') or event_ids -> event_ids as strings."""
    named = [k for k in keys if not k.isdigit()]
    found = dict(conn.execute("SELECT event_key, event_id::text FROM citation_events WHERE event_key = ANY(%s)",
                              (named,)).fetchall())
    missing = set(named) - set(found)
    if missing:
        raise SystemExit(f"unknown event keys: {sorted(missing)}")
    return {found.get(k, k) for k in keys}


def evaluate(name):
    with main.POOL:
        qs = list(csv.DictReader(open(HERE / f"agent_questions_{name}.csv", encoding="utf-8")))
        results, totals = [], {}
        for q in qs:
            out = agent.run(q["question"])
            with main.db() as conn:
                key_ids = key_event_ids(conn, split(q["key_events"]))
                ev = [v for k, v in agent.refs(out["answer"]) if k == "event" and v.isdigit()]
                event_section = dict(conn.execute("SELECT event_id::text, provision_id FROM citation_events "
                                                  "WHERE event_id = ANY(%s)", ([int(v) for v in ev],)).fetchall())
                rendered, _ = agent.render(out["answer"], out["seen"], conn)
                expected = {p: provision_status(conn, p)["status"] for p in split(q["expected_provisions"])}
            s = score(q, out, key_ids, event_section)
            results.append({"qid": q["qid"], "kind": q["kind"], "question": q["question"], "answer": out["answer"],
                            "rendered": rendered, "steps": out["steps"], "expected_status": expected, "scores": s})
            for k, v in s.items():
                totals.setdefault(k, []).append(v)
            print(f"{q['qid']:<6} {q['kind']:<10} {json.dumps(s)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}_answers.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    n = len(qs)
    print(f"\n{name}: {sum(totals['invented'])} invented references in {n} answers; "
          f"section found {sum(totals['section_found'])}/{n}; key rulings {sum(totals['key_rulings'])}/{n}"
          + (f"; not-held wording {sum(totals['not_held_wording'])}/{len(totals['not_held_wording'])}"
             if "not_held_wording" in totals else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["dev", "heldout"])
    ap.add_argument("--facts", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    selftest() if a.selftest else facts() if a.facts else evaluate(a.set)
