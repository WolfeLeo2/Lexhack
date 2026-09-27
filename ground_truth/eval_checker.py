"""Score the second-pass checker (pipeline.verify_events) on every event the blind reviews labelled (rounds 1-3).

  uv run python -m ground_truth.eval_checker

Label per event = the two reviewers' agreed verdict (split events are skipped): RIGHT (real event, right type and
section) or WRONG. The checker should FAIL the wrong ones and PASS the right ones. Its prompt was written from the
general rule, not from these cases, so this is a fair test.
"""
import csv
from pathlib import Path

from ground_truth.eval_events_review import verdict
from pipeline.verify_events import check_many

HERE = Path(__file__).parent
ROUNDS = {1: "", 2: "_r2", 3: "_r3"}


def main():
    claims, labels, rounds = [], [], []
    for rnd, sfx in ROUNDS.items():
        load = lambda n: {r["event_id"]: r for r in csv.DictReader(open(HERE / n, encoding="utf-8"))}
        sample = load(f"events_review_sample{sfx}.csv")
        a, b = load(f"events_review{sfx}_A.csv"), load(f"events_review{sfx}_B.csv")
        for eid, e in sample.items():
            va, vb = verdict(a[eid], e["event_type"]), verdict(b[eid], e["event_type"])
            if va != vb:
                continue
            claims.append(e)
            labels.append(va == "right")
            rounds.append(rnd)
    results = check_many(claims)
    print(f"{len(claims)} labelled events (reviewers agreed), {sum(labels)} right, {len(labels) - sum(labels)} wrong; "
          f"{sum(r[2] for r in results)} API calls")
    for rnd in (*ROUNDS, "all"):
        idx = [i for i, r in enumerate(rounds) if rnd == "all" or r == rnd]
        right = [i for i in idx if labels[i]]
        wrong = [i for i in idx if not labels[i]]
        kept = [i for i in idx if results[i][0] == "pass"]
        print(f"round {rnd}: wrong events caught {sum(results[i][0] != 'pass' for i in wrong)}/{len(wrong)}; "
              f"right events kept {sum(results[i][0] == 'pass' for i in right)}/{len(right)}; precision "
              f"{sum(labels[i] for i in idx)}/{len(idx)} -> {sum(labels[i] for i in kept)}/{len(kept)} after the check")
    for c, lab, (v, why, _) in zip(claims, labels, results):
        if (v == "pass") != lab:
            print(f"{'KEPT WRONG' if v == 'pass' else 'DROPPED RIGHT'} {c['event_id']} {c['event_type']} "
                  f"{c['section'][:40]}: {why[:150]}")


if __name__ == "__main__":
    main()
