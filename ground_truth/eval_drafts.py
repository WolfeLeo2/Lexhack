"""Run draft mode (api.agent.draft, as /api/chat mode=draft calls it) on agent_drafts_dev.csv, real Gemini, cached.

  uv run python -m ground_truth.eval_drafts

Writes $LEXHACK_DATA/review/agent/drafts_dev_answers.json in the answer-grader's item shape (qid, question, answer,
rendered, steps, expected_status) plus the draft check's items. answer and steps are the final run's (the revision,
if any) as captured from agent.run; first_answer is the draft before revision. Prints checker items flagged after
revision, revisions triggered and references removed.
"""
import csv
import json
from pathlib import Path

from api import agent, main
from api.status import provision_status

from .eval_agent import OUT, split

HERE = Path(__file__).parent


def evaluate():
    qs = list(csv.DictReader(open(HERE / "agent_drafts_dev.csv", encoding="utf-8")))
    real_run, results = agent.run, []

    with main.POOL:
        for q in qs:
            runs, tools_used = [], []

            def recording(*a, **kw):   # agent.draft unchanged; keep each run's raw answer and steps for the grader
                out = real_run(*a, **kw)
                runs.append(out)
                return out
            agent.run = recording
            try:
                d = agent.draft(q["question"], on_step=lambda name, args: tools_used.append(name))
            finally:
                agent.run = real_run
            with main.db() as conn:
                expected = {p: provision_status(conn, p)["status"] for p in split(q["expected_provisions"])}
            flagged = [i for i in d["check"] if i["flagged"]]
            results.append({"qid": q["qid"], "kind": q["kind"], "question": q["question"],
                            "answer": runs[-1]["answer"], "first_answer": runs[0]["answer"],
                            "rendered": "".join(map(agent.part_text, d["parts"])),
                            "steps": [s for r in runs for s in r["steps"]], "expected_status": expected,
                            "revised": "revise" in tools_used, "removed": d["removed"], "check": d["check"]})
            print(f"{q['qid']:<4} {q['kind']:<18} revised={results[-1]['revised']!s:<5} removed={d['removed']} "
                  f"flagged={[(i['kind'], i['result']) for i in flagged]}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "drafts_dev_answers.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    flags = [i for r in results for i in r["check"] if i["flagged"]]
    print(f"\n{len(results)} drafts: {len(flags)} checker items flagged after revision "
          f"({sum(bool([i for i in r['check'] if i['flagged']]) for r in results)} drafts); "
          f"{sum(r['revised'] for r in results)} revisions triggered; "
          f"{sum(r['removed'] for r in results)} references removed")
    for r in results:
        for i in r["check"]:
            if i["flagged"]:
                print(f"  {r['qid']} {i['kind']}:{i['result']} {i['raw_text'][:70]!r} - {i['note']}")


if __name__ == "__main__":
    evaluate()
