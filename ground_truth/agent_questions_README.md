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

## Fresh held-out set (2026-10-02)

- `agent_questions_heldout2.csv` (30, qids n01..n30): written after the first held-out set was scored, to measure the
  2026-10-02 fixes (`find_section`, single-word case names, ruling state in rendering). No section in common with dev;
  it may reuse sections of the first held-out set, with new questions. Kinds: status 5, topic 5, case 6 (2+ by a single
  party word), history 3, repealed 2, no_rulings 2, not_held 4, advice 3. Checked mechanically (provisions and events
  exist and belong to their rows, no dev overlap, repealed/no-rulings statuses confirmed). n26 and n27 replaced:
  Mitu-Bell and BAT v Ministry of Health are held; replaced with Mukisa Biscuit and Giella v Cassman Brown (no title
  match). Scored once.

## Third held-out set (2026-10-04)

- `agent_questions_heldout3.csv` (30, qids m01..m30): written to measure the 1a fixes (find_case falls back to the
  party-name search after an unconfirmed citation, rulings carry their Act, advice still looks the section up, false
  "not held" counted). No dev sections; reuses earlier held-out sections with new questions (few others have checked
  rulings). Kinds: status 4, topic 5, case 6 (2 by one word, 2 "X v Y (year)", 2 full names), history 3, repealed 2,
  no_rulings 2, not_held 4, advice 4. Checked mechanically. m25 and m26 replaced (Macharia v KCB and Speaker v Karume
  are held) with Karisa Chengo v Republic and Shah v Mbogo (no title match). Scored once.
