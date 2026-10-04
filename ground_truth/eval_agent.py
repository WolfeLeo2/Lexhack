"""Score the research agent (api/agent.py) on a question set (README §7c).

  uv run python -m ground_truth.eval_agent --facts          # what the question writer works from
  uv run python -m ground_truth.eval_agent --selftest       # the scoring rules on hand-made answers
  uv run python -m ground_truth.eval_agent --set dev        # run + score; answers for the grader
  uv run python -m ground_truth.eval_agent --set heldout    # once, after tuning on dev
  uv run python -m ground_truth.eval_agent --set heldout2   # fresh held-out set, once, after the 2026-10-02 fixes

Scored in code: invented references (the headline), model-written quotes, section found, key rulings cited, not-held
wording. The judgement calls (contradicts the status, advice, verdict, lead as status) go to the answer-grader agent.
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
NOT_HELD_OK = re.compile(r"(?:not|n'?t) (?:currently )?(?:in|part of|(?:held|included|available) in) "
                         r"(?:Hakiki'?s|our|the) collection"
                         r"|Hakiki(?:'?s collection)? (?:does not|doesn'?t) (?:hold|include|contain|have)", re.I)
MODEL_QUOTE = re.compile(r'["“][^"“”]{20,}["”]')   # a quotation of 20+ characters the model wrote itself
NOT_HELD_BAD = re.compile(r"\b(?:does not|doesn'?t|did not|didn'?t) exist|\bfake\b|\binvalid\b|fabricated", re.I)


def split(s):
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def score(q, out, key_ids, event_section):
    """q: a question row; out: agent.run's result; key_ids: event_ids (str) the answer must cite; event_section:
    {event_id: provision_id} for every event the answer references. Only references a tool returned earn credit;
    section_found and key_rulings are left out when the question expects no section or no ruling."""
    rs = agent.refs(out["answer"])
    seen = {(k, v) for k, vs in out["seen"].items() for v in vs}
    cited_events = {v for k, v in rs if k == "event" and (k, v) in seen}
    cited_sections = ({v for k, v in rs if k == "section" and (k, v) in seen}
                      | {event_section.get(v) for v in cited_events})
    s = {"invented": sum((k, v) not in seen for k, v in rs),
         "model_quotes": len(MODEL_QUOTE.findall(agent.BRACKETS.sub("", out["answer"])))}
    if split(q["expected_provisions"]):
        s["section_found"] = all(p in cited_sections for p in split(q["expected_provisions"]))
    if key_ids:
        s["key_rulings"] = key_ids <= cited_events
    if q["expect_not_held"] == "yes":
        s["not_held_wording"] = bool(NOT_HELD_OK.search(out["answer"])) and not NOT_HELD_BAD.search(out["answer"])
    else:   # a 'not held' claim where the question expects none (the Wachira fault). An upper bound: it also fires
        # when an answer rightly says some other item isn't held
        s["false_not_held"] = int(bool(NOT_HELD_OK.search(out["answer"])))
    return s


def selftest():
    q = {"expected_provisions": "p1", "expect_not_held": "yes"}
    out = {"answer": "[[section:p1]] [[event:7]] [[event:8]] It is not in Hakiki's collection.",
           "seen": {"section": ["p1"], "event": ["7"], "judgment": []}}
    s = score(q, out, {"7"}, {"7": "p1"})
    assert s == {"invented": 1, "model_quotes": 0, "section_found": True, "key_rulings": True,
                 "not_held_wording": True}, s
    out["answer"] = "That case does not exist. [[event:7]]"
    s = score(q, out, {"7", "9"}, {"7": "p1"})
    assert s["not_held_wording"] is False and s["key_rulings"] is False and s["section_found"] is True, s
    for text, ok in [("Hakiki's collection does not hold the Land Registration Act or its section 26.", True),
                     ("The Data Protection Act, 2019 is not currently held in Hakiki's collection of statute law.", True),
                     ("That case does not exist.", False),
                     ("Hakiki's collection holds the Act; section 26 is in force.", False)]:
        got = score(q, {"answer": text, "seen": out["seen"]}, set(), {})["not_held_wording"]
        assert got is ok, (text, got)
    q = {"expected_provisions": "p2", "expect_not_held": ""}
    assert score(q, out, set(), {"7": "p1"}) == {"invented": 0, "model_quotes": 0, "section_found": False,
                                                 "false_not_held": 0}
    q = {"expected_provisions": "", "expect_not_held": ""}   # nothing expected: neither metric applies
    assert score(q, out, set(), {"7": "p1"}) == {"invented": 0, "model_quotes": 0, "false_not_held": 0}
    q = {"expected_provisions": "p1", "expect_not_held": ""}
    out = {"answer": "[[section:p1]] [[event:7]]", "seen": {"section": [], "event": [], "judgment": []}}
    s = score(q, out, {"7"}, {"7": "p1"})   # invented but correct references earn nothing
    assert s == {"invented": 2, "model_quotes": 0, "section_found": False, "key_rulings": False,
                 "false_not_held": 0}, s
    out = {"answer": 'It held "the mandatory nature of the death sentence" was void, “a short one” and '
                     '“to the extent that it covers other offences” [[event:7, 8]]',
           "seen": {"section": ["p1"], "event": ["7", "8"], "judgment": []}}
    s = score(q, out, set(), {})   # malformed reference is invented; two quotes of 20+ characters
    assert s == {"invented": 1, "model_quotes": 2, "section_found": False, "false_not_held": 0}, s
    q = {"expected_provisions": "p1", "expect_not_held": ""}   # held, but the answer says it isn't
    s = score(q, {"answer": "That case is not in Hakiki's collection.", "seen": out["seen"]}, set(), {})
    assert s["false_not_held"] == 1, s
    q = {"expected_provisions": "", "expect_not_held": "yes"}
    assert "false_not_held" not in score(q, {"answer": "Not in Hakiki's collection.", "seen": out["seen"]}, set(), {})
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

    def frac(k, label):   # over the questions the metric applies to
        return f"; {label} {sum(totals[k])}/{len(totals[k])}" if k in totals else ""
    print(f"\n{name}: {sum(totals['invented'])} invented references in {n} answers; "
          f"{sum(totals['model_quotes'])} model-written quotes" + frac("section_found", "section found")
          + frac("key_rulings", "key rulings") + frac("not_held_wording", "not-held wording")
          + f"; {sum(totals.get('false_not_held', []))} false not-held claims")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["dev", "heldout", "heldout2", "heldout3"])
    ap.add_argument("--facts", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    selftest() if a.selftest else facts() if a.facts else evaluate(a.set)
