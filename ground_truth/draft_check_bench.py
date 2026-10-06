"""Benchmark draft mode's citation check (api/agent.py draft_check) on hand-built drafts. Deterministic: no LLM.

  uv run python -m ground_truth.draft_check_bench

Each row of draft_check_bench.json is a draft as the model would write it (raw text with [[...]] references), the
question, and the tool calls it made; the calls are replayed through api.tools against the database (read-only) to
give the steps and the seen IDs. `expect` lists the flagged items as [kind, result] ("a|b": either result). Prints
recall per expected kind and every false flag. This measures code, not a prompt: misses are reported, not tuned away.
"""
import json
from collections import Counter
from pathlib import Path

from api import agent, main, tools

HERE = Path(__file__).parent


def check(conn, row):
    """-> flagged [(kind, result, raw_text)] as draft() reports them (references_removed added as draft() does)."""
    steps, seen = [], {"section": set(), "event": set(), "judgment": set()}
    for name, args in row["calls"]:
        out = tools.call(name, args)
        for k, v in out["ids"].items():
            seen[k].update(v)
        steps.append({"tool": name, "args": args, "result": out["result"]})
    parts, removed = agent.render_parts(row["answer"], seen, conn)
    items = agent.draft_check(conn, parts, row["question"], steps)
    if removed:
        items.append(agent.item("", "note", "references_removed", "", True))
    return [(i["kind"], i["result"], i["raw_text"]) for i in items if i["flagged"]]


def run():
    rows = json.loads((HERE / "draft_check_bench.json").read_text(encoding="utf-8"))
    hit, total, false = Counter(), Counter(), []
    with main.POOL, main.db() as conn:
        for row in rows:
            got = check(conn, row)
            left = list(got)
            for kind, result in row["expect"]:
                label = f"{kind}:{result}"
                total[label] += 1
                m = next((g for g in left if g[0] == kind and g[1] in result.split("|")), None)
                if m:
                    hit[label] += 1
                    left.remove(m)
                else:
                    print(f"MISS  {row['id']} ({row['covers']}): expected {label}; flagged {[g[:2] for g in got]}")
            for g in left:
                false.append(row["id"])
                print(f"FALSE {row['id']} ({row['covers']}): {g[0]}:{g[1]} on {g[2][:80]!r}")
    print(f"\n{len(rows)} drafts; recall per expected kind:")
    for label in sorted(total):
        print(f"  {label:<36} {hit[label]}/{total[label]}")
    clean = sum(not r["expect"] for r in rows)
    print(f"  all                                  {sum(hit.values())}/{sum(total.values())}")
    print(f"false flags: {len(false)} in {len(set(false))} drafts {sorted(set(false))}; "
          f"drafts expecting nothing: {clean}, of which flagged: {len({r['id'] for r in rows if not r['expect']} & set(false))}")


if __name__ == "__main__":
    run()
