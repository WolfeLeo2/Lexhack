# Filing checker, slice 2a: eKLR matching and the filing benchmark

Date: 2026-09-28. Status: design approved in chat; this is the written spec. Builds on slice 1
(`docs/superpowers/specs/2026-09-28-filing-checker-design.md`, `api/filing.py`).

## Why

In 400 random judgments we hold, `[YYYY] eKLR` citations are as common as neutral ones (1,035 vs 990; in half the
judgments). Slice 1 reads only neutral citations, so it misses half of what a real filing cites. And no number yet says
how often the checker is right; the benchmark gives that.

Kenya Law's own judgment-to-judgment links are no shortcut: in a 400-judgment sample, 25 of 2,761 links carried an eKLR
citation as anchor text; the rest are the sidebar of related judgments. Labels come from agents.

## Matching `Name [YYYY] eKLR`

**Detection.** `(?P<year>\d{4})\]\s*eKLR` after `[`, also `[YYYY]eKLR`. The case name comes from `cited_name()` (slice 1),
extended to skip a parenthesised case number between name and citation ("Katiba Institute & another v Attorney General
& another (Constitutional Petition No. 209 of 2016; [2017] eKLR)").

**Case number.** In the 200 characters before the citation, `(?P<kind>[A-Z][A-Za-z .]*?)\s+(?:No\.?\s*)?(?P<num>[A-Z]?\d+[A-Z]?)\s+of\s+(?P<y>\d{4})`,
normalised to `<num> of <y>` (kind ignored: filings write "HCCC", "Pet.", "Constitutional Petition" for the same thing).
Our `judgments.case_number` ("Petition 397 of 2016", 16,113 of 16,419 rows) is normalised the same way.

**Candidates.** Judgments with `extract(year from decision_date) = year`, not `duplicate_of`, loaded once per year
(`functools.lru_cache`): id, title, party part of the title (`title` up to the first ` (`, `[`, or `;`), case number.

**Score.** Party tokens: lowercase words of 2+ letters, plus all-caps initials of 2+ letters ("JAC", "PW"), minus
`NOT_A_PARTY` (slice 1). Weight each token by IDF over all titles we hold (`log(N / df)`), computed once. Score of a
candidate = sum of weights of cited tokens found in its party part / sum of weights of all cited tokens (0..1).
Case number equal → score set to 1.0 and basis `case number`.

**Decision** (thresholds `FOUND_SCORE`, `FOUND_MARGIN`, `POSSIBLE_SCORE`; starting values 0.8, 0.25, 0.5, tuned on the
dev set only):
- best ≥ `FOUND_SCORE` and best − second ≥ `FOUND_MARGIN` → `found`, basis `party names and year` (or `case number`);
- else candidates with score ≥ `POSSIBLE_SCORE` (top 3) → `possible_match`;
- else → `not_in_collection`.

**Quotes break ties.** For `possible_match`, each quote attributed to the citation is matched against every candidate;
if exactly one candidate holds a quote `verbatim`, the result becomes `found` with basis `quote`.

Neutral citations keep slice 1's logic; their basis is `neutral citation`.

## API contract changes (`api/main.py`, `web/lib/api.ts`)

`CaseCheck` gains:
- `result`: adds `possible_match`;
- `form`: `neutral` | `eklr`;
- `match_basis`: `neutral citation` | `case number` | `party names and year` | `quote` | null;
- `candidates`: `list[JudgmentRef]` (possible_match only; best first).

`QuoteCheck` for a `possible_match` case: `not_checked` unless a quote settled the match. `find_quotes` attributes quotes
to eKLR citations exactly as to neutral ones.

## UI (`web/app/check/Checker.tsx`)

- `found` notes say what the match rests on ("Matched on party names and year").
- `possible_match`: a pinned note, "Possibly one of these cases in our collection", with the candidates as small index
  cards (short name, court, date, link). Counts as worth a second look.
- The empty-report copy no longer says eKLR is unread.
Creative latitude per CLAUDE.md.

## Benchmark (`ground_truth/filing_*`, `ground_truth/eval_filing.py`)

**Sets.** Judgments with at least 2 eKLR citations, excluding the slice 1 demo judgments and the 60 mention-benchmark
judgments; sampled with a fixed seed into **dev** (40 judgments) and **test** (40). Every eKLR citation in them is an item.
`ground_truth/filing_sample.py` writes `filing_{dev,test}_items.csv`: item id, citing judgment, citation text, 300
characters of context, cited year.

**Labels.** Agent type `.claude/agents/citation-labeler.md` (tools: Read, Grep, Write). For each item it gets the context
and a file of that year's titles and case numbers (`$LEXHACK_DATA/review/filing/titles_<year>.tsv`), and answers
`judgment_id` or `not_held`, with a one-line reason. Two agents label each set blind (A, B), without seeing the
checker's answer. Agreement is reported; disagreements go to a third agent whose label decides. Files:
`filing_{dev,test}_labels_{A,B,C}.csv`, merged into `filing_{dev,test}_gold.csv`.

**Metrics** (per set, printed by `eval_filing.py --set dev|test`):
- *found precision*: share of `found` answers that name the gold judgment;
- *wrong-case rate*: `found` answers naming a different judgment, over all items (the dangerous error);
- *coverage*: gold-held items answered `found` with the right judgment;
- *possible-match hit rate*: gold-held items answered `possible_match` whose candidates include the gold judgment;
- *false found on not-held*: gold `not_held` items answered `found`.
Thresholds are tuned on dev; test is scored once, and that is the number quoted.

**Planted errors** (`eval_filing.py --planted`, no labels needed; source: verified items and real neutral citations
in the dev+test judgments):
- *wrong name*: a real neutral citation given another held case's name → expect `name_mismatch`;
- *altered quote*: a passage verbatim in a held judgment, altered by dropping a word, swapping one word for another from
  the same judgment, or inserting "not" → expect `close` or `not_found`, never `verbatim`;
- *invented number*: `[YYYY] KEHC <number above the year's highest we hold + 10000>` → expect `not_in_collection`.
Reported as catch rates. **False alarms** on real, unmodified neutral citations in the same judgments: share flagged
`name_mismatch` (agents check a sample of flagged ones to split real errors from abbreviations).

Headline numbers go in README §7c and the About page, labelled as measured on our collection.

## Testing

`api/test_filing.py` gains pure checks for eKLR detection, case-number normalisation, scoring and the decision rule,
and end-to-end checks: the Okuta/Muruatetu eKLR citations resolve `found`; an eKLR citation to a made-up case is
`not_in_collection`; a two-candidate case is `possible_match` and a quote settles it. The demo filings gain eKLR
citations.

## Out of scope (2b, 2c, later)

Upload (2b); quotes away from their citation (2c); `[YYYY] KLR` law-report citations; citations with no year.
