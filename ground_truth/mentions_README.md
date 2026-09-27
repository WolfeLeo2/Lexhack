# Citation-extraction answer key (step 5)

Scores `pipeline.extract_citations` on a hand-checked sample. Independent of the extractor: candidates come from
a broader pattern (`mention_sample.py`), and each is labelled by reading the judgment.

| File | What |
|---|---|
| `mention_sample.py` | Draws the sample (fixed seed): 10 judgments each from kesc, keca, kehc; long ones cut to one window of 40 candidates |
| `mentions_candidates.csv` | Every candidate: judgment, candidate number, offset, the annotated span, context |
| `mentions_gold.csv` | The labels: one row per cited section (a list "sections 3 and 4" is two rows), or one `-` row for a non-citation |
| `eval_mentions.py` | Scores the extractor against the gold rows |

## Labelling rules

**In scope:** a numbered section or Article of a written law, cited by number: an Act, Code, Constitution (2010 or
repealed), treaty, or a named statutory instrument ("section 3 of the Legal Notice").

**Not a citation (`-`):** rules and orders ("Order 42 rule 6", "rule 5"), regulations cited as "regulation N";
paragraphs of a schedule; sections of a report, book, judgment or contract ("Article 5 of the Lease" is `-`
only if it is a private document); subsections cited alone ("sub-section (2)"); non-legal uses ("article 3 of the
newspaper"); a candidate that is only a fragment of a citation labelled at another candidate.

**`section_ref`:** the number and sub-provisions as written, spaces removed: `8(1)`, `159(2)(d)`, `34(6B)`.
One row per *section*: sub-provisions of the same section stay in one row, however they are joined
("206(a), (b) and (c)" is `206(a)`; "178 (1)(3)" is `178(1)(3)`). Scoring compares section numbers, not sub-provisions.
A range "sections 3 to 7" is expanded to one row per number. Where "as read with section 8(2)" has its own
candidate, 8(2) is labelled there, not at the first candidate.

**`act_ref`:** the law the judgment means, resolved by reading it ("the Act" -> the Act the judgment is about).
For our 8 Acts use the canonical names: `Penal Code`, `Sexual Offences Act`, `Kenya Information and
Communications Act`, `Criminal Procedure Code`, `Civil Procedure Act`, `Evidence Act`, `Employment Act`,
`Constitution of Kenya` (2010). The pre-2010 Constitution is `Constitution (repealed)`. Other laws: the short
title as named, without "the", year, Cap or Act number (`Law of Succession Act`). If the judgment doesn't make
the law clear, `unknown`.

## Verification (2026-09-27)

Drafted by Claude from context windows; each candidate then checked against the full judgment by three independent
subagents (one per court), which did not see the extractor. Their verdicts are in `mentions_review_{kesc,keca,kehc}.csv`:
544 ok, 7 fix, 0 unsure. 1 fix accepted (an Act name: County Government**s** Act); 6 declined, all proposals to
split sub-provisions of one section into separate rows (decided above: one row per section).

**Caveat:** the extractor was tuned on this same sample, so its scores here are optimistic. A fresh held-out
sample (another seed) gives an honest number.

**`status`:** `draft` (drafted by Claude from context) | `verified` (confirmed against the full judgment) |
`corrected` (changed by the verifier; old value in `note`).
