# Agent question sets

Benchmark for the research agent (`api/agent.py`), scored by `ground_truth/eval_agent.py` (README §7c).

- `agent_questions_dev.csv` (20): for tuning the system prompt. Re-run as often as needed.
- `agent_questions_heldout.csv` (30): scored **once**, after tuning. After a later prompt change, write a fresh
  held-out set instead of re-scoring this one.

Written 2026-09-30 by a Claude agent from `eval_agent --facts` (every section with a checked ruling); checked
mechanically (every provision and event exists, no section in both sets) and not-held cases confirmed by title search.
Columns: `qid, kind, question, expected_provisions, key_events, expect_not_held, notes` (lists `;`-separated;
`key_events` are answer-key `event_key`s or `event_id`s). Expected statuses are not stored: the harness reads them
from the resolver at scoring time.

Provenance of changes after the agent wrote the sets: d18, h26 and h27 replaced because the original cases were held
(Anarita Karimi Njeru, Matemu v Trusted Society, Ayuma v Kenya Railways scheme); the new not-held cases (Rose Wangui
Mambo v Limuru Country Club, Ann Njogu v AG, KACC v Online Enterprises) have no title match in `judgments`. Repealed
rows confirmed `repealed`; no_rulings rows have no verified court events. d07 and h14 kept as written.
