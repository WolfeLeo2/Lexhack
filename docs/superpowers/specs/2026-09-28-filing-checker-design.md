# Filing checker, slice 1: design

Date: 2026-09-28. Status: approved in chat; this is the written spec.

## Goal

Paste a legal filing, get back every citation in it with three checks, each backed by evidence:

1. **Case:** does the cited judgment exist in our collection, and is it the case the filing names?
2. **Quote:** does the quoted passage appear in that judgment?
3. **Section:** what is the cited statute section's status (court's words, source)?

Hakiki reports what sources say. No valid/invalid verdicts, never "fake"; every response carries `DISCLAIMER`.

**Slice 1 scope:** pasted text; neutral citations (`[2017] KESC 2 (KLR)`); quotes in the same paragraph as a cited
case; section citations. **Slice 2 (not here):** `[2017] eKLR` and case-name-only matching, PDF/DOCX upload, an
agent-labelled benchmark, quotes not next to their citation.

## API

`POST /api/check`, body `{"text": str}` (max 200,000 characters, else 413). The web page posts through a Next.js
server action (server to server), so CORS stays GET-only.
Filings are never stored or logged.

Response `CheckReport`:

```
CheckReport
  findings: list[Finding]        # document order
  disclaimer: str
Finding
  kind: 'case' | 'section'
  raw_text: str                  # as written in the filing
  char_start, char_end: int      # offsets into the submitted text (for highlighting)
  case: CaseCheck | None
  quotes: list[QuoteCheck]       # quotes attributed to this case (kind='case' only)
  section: SectionCheck | None
CaseCheck
  result: 'found' | 'name_mismatch' | 'not_in_collection'
  cited_name: str | None         # case name the filing gives before the citation
  judgment: {judgment_id, title, court, decision_date, neutral_citation, source_url} | None
QuoteCheck
  quote: str                     # as written in the filing
  result: 'verbatim' | 'close' | 'not_found' | 'not_checked'
  similarity: float | None       # 0..1, for 'close'
  court_text: str | None         # the judgment's words at the best match; for not_found, the nearest passage if any
  paragraph: str | None          # judgment paragraph of the match
SectionCheck
  result: 'linked' | 'not_covered'   # not_covered = a law we don't hold, or a section we can't resolve
  act_ref: str | None
  provision: ProvisionRef | None
  status: str | None             # status_ke label
  summary_events: list[Event]    # the court's verbatim words, as on the section page
```

Pydantic models live in `api/main.py` next to the existing contract.

## Logic (`api/filing.py`, pure functions except text fetch)

**Case citations.** Regex for `[YYYY] <COURT> <N>` with optional `(KLR)`; court codes from the ones in `judgments`
(KESC, KECA, KEHC, KEELRC, KEELC, …). Normalise to our stored form `[YYYY] CODE N (KLR)` and look up
`judgments.neutral_citation` (skip `duplicate_of` rows).
- Not in table → `not_in_collection`. The UI says we hold about 10% of published judgments.
- In table → compare `cited_name` (the "X v Y" text just before the citation) with our title: party-name tokens,
  ignoring stopwords ("and", "another", "others", "republic", "attorney general" abbreviations handled by a small
  alias list). No shared party token → `name_mismatch`, else `found`. No `cited_name` → `found`.

**Quotes.** Passages in “…” or "…" of at least 8 words, in the same paragraph (blank-line separated) as a case
citation that resolved; attributed to the nearest such citation. Case not held → `not_checked`.
- Normalise both sides: lowercase, unify quote marks and dashes, collapse whitespace, strip `[` `]` editorial brackets.
- Split the quote on ellipses (`...`, `…`); every part must appear, in order → `verbatim`, with its paragraph.
- Otherwise fuzzy: locate the best window by shared 5-word shingles, score with `difflib.SequenceMatcher`;
  ratio ≥ 0.85 → `close` with `court_text`; else `not_found`.
- Paragraph number from `pipeline.extract_citations.paragraph_markers` / `paragraph_at`.

**Sections.** `pipeline.extract_citations.extract(text)` (no decision date → current Constitution), then
`pick_provision` with `provision_lookup(conn)` to get a `provision_id`; then `api.status.provision_status` for
status and summary events. No provision → `not_covered` with `act_ref`.

**Judgment text.** `judgment_text(raw_path)`: read `$LEXHACK_DATA/<raw_path>` if it exists, else fetch the same key
from R2 with `boto3` (`R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, bucket `R2_BUCKET` default
`lexhack-data`, read-only token). `functools.lru_cache`. Fetch failure → quotes for that case are `not_checked`;
the request still succeeds.

## Web (`web/app/check/`)

Text area, "Check" button, "Try a demo filing" menu (the three demo filings). Report: the filing with citations
highlighted by result, and one card per finding linking to `/p/<provision_id>` and the judgment's `source_url`.
Wording per result, never a verdict; the disclaimer at the top. Nav gets a "Check a filing" link.

## Demo filings (`demo_filings/`, each headed "SYNTHETIC: written by the Hakiki team for demonstration")

1. **clean.md**: real citations, verbatim quotes, sections without adverse rulings.
2. **hallucinated.md**: a real citation number under the wrong case name; a misquote of a real passage; a neutral
   citation we don't hold.
3. **stale_law.md**: relies on Penal Code s.204 as a mandatory death sentence and s.194 criminal defamation.

One copy, in `web/public/demo/`: the page fetches them, the tests read them.

## Testing

`api/test_filing.py`, same style as `api/test_status.py`:
- pure-function tests: citation regex, name comparison, quote normalisation, ellipsis splitting, fuzzy match;
- end-to-end on the three demo filings against Neon + local data: the expected result for each finding.

## Deployment

Railway: `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` set by Leo (read-only token). Add `boto3` to
`pyproject.toml`. Docs: README section and CLAUDE.md "Where we are".
