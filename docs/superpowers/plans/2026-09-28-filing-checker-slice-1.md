# Filing Checker, Slice 1: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paste a legal filing into Hakiki and get every case and section citation in it back with three evidence-backed checks: is the case in our collection (and the one the filing names), do quoted words appear in it, and what have courts done to each cited section.

**Architecture:** One new module `api/filing.py` holds pure functions (find citations, compare names, match quotes) plus `check(conn, text)`, which joins them with the database and the existing status rules (`api/status.py`). Judgment text comes from `$LEXHACK_DATA` on disk when present, else from the same key in Cloudflare R2 (the API host has no data folder). `POST /api/check` in `api/main.py` exposes it; the Next.js page `web/app/check/` posts through a server action, so no CORS change is needed.

**Tech Stack:** Python 3 (uv), FastAPI, psycopg, `boto3` (new, for R2), stdlib `difflib`/`re`; Next.js 16 (pnpm), React `useActionState`, Tailwind.

**Spec:** `docs/superpowers/specs/2026-09-28-filing-checker-design.md`

## Global Constraints

- Never output a valid/invalid verdict and never call a citation "fake"; `not_in_collection` UI copy says we hold about 10% of published judgments.
- Every report carries `DISCLAIMER` from `api/main.py` ("Hakiki reports what published sources say. It is not legal advice.").
- Quote courts verbatim; show the judgment's own words as evidence.
- Filings are never stored or logged.
- Max filing length 200,000 characters → HTTP 413.
- Quotes are checked only if at least 8 words; "close" threshold is a `difflib` ratio ≥ 0.85.
- Read data paths from `LEXHACK_DATA`; never hardcode paths. R2 env vars: `R2_ENDPOINT` (account endpoint, without the bucket name), `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, optional `R2_BUCKET` (default `lexhack-data`).
- Demo filings are headed "SYNTHETIC FILING: written by the Hakiki team for demonstration."
- Commits go straight to `main`, no `Co-Authored-By` line (Leo's rule). Claude's shell can't push; Leo pushes.
- Match surrounding style: plain-script tests (`uv run python -m api.test_filing`, like `api/test_status.py`), docstrings that say why, no frameworks.

## Review Focus

1. **Line endings from the browser.** A `<textarea>` submits `\r\n`; highlight offsets must match the text the report is drawn from. Expect: the action normalises to `\n` and the report renders the text it checked. Pinned in Task 5 (`splitAt` check + manual step).
2. **Non-ASCII in the filing (emoji, accented names).** Python offsets are code points, JS strings are UTF-16. Expect: highlights land on the citation. Pinned in Task 5 (`splitAt` check with an emoji).
3. **R2 unreachable or judgment is PDF-only (`has_full_text` false).** Expect: that case's quotes read "not checked", the rest of the report still returns. Pinned in Task 4 (`quote_check` tests).
4. **A paragraph citing two cases with a quote between them.** Expect: the quote goes to the nearest citation. Pinned in Task 2 (`find_quotes` test).
5. **Empty or oversized input.** Expect: empty → empty report (web shows "Paste a filing first."); > 200,000 characters → 413 with a readable message. Pinned in Task 4 (curl step) and Task 5 (action).

---

## File Structure

- Create `api/filing.py`: citation finding, name comparison, quote matching, judgment text fetch, `check()`.
- Create `api/test_filing.py`: pure tests + end-to-end on the demo filings.
- Modify `api/main.py`: response models + `POST /api/check`.
- Modify `pyproject.toml` / `uv.lock`: add `boto3` (via `uv add`).
- Create `web/public/demo/clean.txt`, `hallucinated.txt`, `stale_law.txt`: the synthetic filings (one copy, used by the web page and the tests).
- Modify `web/lib/api.ts`: TypeScript types for the report.
- Modify `web/lib/text.ts` + `web/lib/text.check.ts`: `splitAt` (code-point-safe highlighting) and its check.
- Create `web/app/check/actions.ts`, `web/app/check/Checker.tsx`, `web/app/check/page.tsx`.
- Modify `web/app/layout.tsx`: nav link.
- Modify `README.md`, `CLAUDE.md`: document the checker.

---

### Task 1: Case citations and case names (pure)

**Files:**
- Create: `api/filing.py`
- Test: `api/test_filing.py`

**Interfaces:**
- Produces: `find_cases(text: str) -> list[dict]` with keys `raw_text, char_start, char_end, citation, cited_name`; `citation` is normalised to our stored form `"[2017] KESC 2 (KLR)"`. `cited_name(text: str, start: int) -> str | None`. `names_agree(cited: str | None, title: str) -> bool`. Module constants `WORD` (regex) for later tasks.

- [ ] **Step 1: Write the failing test**

Create `api/test_filing.py`:

```python
"""Checks for the filing checker (api/filing.py). Pure checks first, then the three demo filings end to end
against Neon and local data.

  uv run python -m api.test_filing
"""
from . import filing

fails = []


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


MURUATETU = ("Muruatetu & another v Republic; Katiba Institute & 5 others (Amicus Curiae) (Petition 15 & 16 of 2015 "
             "(Consolidated)) [2017] KESC 2 (KLR) (14 December 2017) (Judgment)")


def test_cases():
    c = filing.find_cases("On sentence, the Supreme Court in Muruatetu & another v Republic [2017] KESC 2 (KLR) observed")
    expect("one case", len(c), 1)
    expect("citation", c[0]["citation"], "[2017] KESC 2 (KLR)")
    expect("cited name", c[0]["cited_name"], "Muruatetu & another v Republic")
    expect("raw text", c[0]["raw_text"], "[2017] KESC 2 (KLR)")
    c = filing.find_cases("as held in [2019]KECA 5.")
    expect("no space, no (KLR)", c[0]["citation"], "[2019] KECA 5 (KLR)")
    expect("no name", c[0]["cited_name"], None)
    expect("eKLR is slice 2", filing.find_cases("Okuta v AG [2017] eKLR"), [])
    expect("v. abbreviation", filing.find_cases("Republic v. Mwangi [2022] KECA 1106 (KLR)")[0]["cited_name"],
           "Republic v. Mwangi")
    expect("lead-in dropped", filing.find_cases("In Okuta v Attorney General [2017] KESC 2 (KLR) the")[0]["cited_name"],
           "Okuta v Attorney General")
    expect("wrong case", filing.names_agree("Okuta v Attorney General", MURUATETU), False)
    expect("right case", filing.names_agree("Muruatetu & another v Republic", MURUATETU), True)
    expect("only generic parties", filing.names_agree("Republic v Attorney General", MURUATETU), True)
    expect("no name given", filing.names_agree(None, MURUATETU), True)


def main():
    test_cases()
    for f in fails:
        print("FAIL", *f)
    print("FAILED" if fails else "all passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m api.test_filing`
Expected: `ImportError: cannot import name 'filing'`

- [ ] **Step 3: Write minimal implementation**

Create `api/filing.py`:

```python
"""Filing checker: every citation in a pasted filing, with three checks and the evidence for each
(docs/superpowers/specs/2026-09-28-filing-checker-design.md).

  case     is the cited judgment in our collection, and is it the case the filing names?
  quote    do the quoted words appear in that judgment?
  section  what have courts done to the cited section (api.status)?

Reports what the sources say. "Not in our collection" never means "fake": we hold about 10% of published judgments.
"""
import re

# [2017] KESC 2 (KLR). Any court code, so an invented court reads as "not in our collection" instead of being missed.
NEUTRAL = re.compile(r"\[(?P<year>\d{4})\]\s*(?P<court>[A-Z]{2,9})\s+(?P<num>\d+)(?:\s*\(KLR\))?")
WORD = re.compile(r"[^\W_]+")
V = {"v", "v.", "vs", "vs."}
GLUE = {"and", "another", "others", "of", "the", "&"}   # lowercase words that belong inside a case name
LEAD_IN = {"in", "see", "per", "also", "cf"}
# Words that don't tell cases apart: parties half of Kenya's cases share, and lead-in words.
NOT_A_PARTY = {"and", "another", "others", "the", "of", "in", "see", "per", "also", "held", "case", "matter", "court",
               "supreme", "appeal", "high", "republic", "attorney", "general", "state", "county", "government",
               "director", "public", "prosecutions", "dpp", "ors", "anor", "ltd", "limited", "kenya", "commission",
               "national", "ex", "parte", "re", "klr", "eklr"}


def cited_name(text, start):
    """'Muruatetu & another v Republic' from the words just before a citation, or None if they hold no 'X v Y'."""
    seg = re.split(r"(?<!\bv)(?<!\bvs)[.;:(]\s|\n", text[max(0, start - 200):start])[-1]
    words = seg.strip(" ,").split()
    vi = next((i for i, w in enumerate(words) if w.lower() in V), None)
    if not vi:
        return None
    # the name starts after the last ordinary lowercase word before the "v": "the Court in | Muruatetu & another v"
    first = max((i + 1 for i, w in enumerate(words[:vi]) if w[0].islower() and w.lower() not in GLUE), default=0)
    while first < vi and words[first].lower() in LEAD_IN:
        first += 1
    return " ".join(words[first:]) or None


def find_cases(text):
    return [{"raw_text": m.group(0), "char_start": m.start(), "char_end": m.end(),
             "citation": f"[{m['year']}] {m['court']} {m['num']} (KLR)", "cited_name": cited_name(text, m.start())}
            for m in NEUTRAL.finditer(text)]


def party_tokens(name):
    return {w for w in WORD.findall(name.lower()) if len(w) > 2 and not w.isdigit() and w not in NOT_A_PARTY}


def names_agree(cited, title):
    """False only when the filing's case name shares no party with our title for that citation: a real citation
    number under someone else's name, the classic invented citation."""
    # ponytail: exact party-word overlap, so a misspelt party ("Muruatatu") reads as a mismatch; fuzzy in slice 2
    mine = party_tokens(cited or "")
    return not mine or bool(mine & party_tokens(title))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m api.test_filing`
Expected: `all passed`

- [ ] **Step 5: Commit**

```bash
git add api/filing.py api/test_filing.py
git commit -m "Filing checker: find neutral case citations and compare case names"
```

---

### Task 2: Quotes, finding and matching (pure)

**Files:**
- Modify: `api/filing.py`
- Test: `api/test_filing.py`

**Interfaces:**
- Consumes: `find_cases`, `WORD` from Task 1.
- Produces: `find_quotes(text: str, cases: list[dict]) -> dict[int, list[str]]` (case index → quote strings). `match_quote(quote: str, text: str) -> dict` with keys `result` (`verbatim|close|not_found`), `similarity` (float or None), `court_text` (str or None: the judgment's words at the match; for `not_found` the nearest passage if any), `char_start` (int or None, offset in the judgment text).

- [ ] **Step 1: Write the failing test**

Add to `api/test_filing.py` above `main()`:

```python
JT = ("1. The appellant was convicted of murder.\n"
      "2. The mandatory nature of the death sentence as provided for under section 204 of the Penal Code is hereby "
      "declared unconstitutional.\n3. Costs to follow the event.")


def test_quotes():
    m = filing.match_quote("the mandatory nature of the death sentence as provided for under section 204", JT)
    expect("verbatim", m["result"], "verbatim")
    expect("verbatim offset", m["char_start"], JT.index("The mandatory"))
    expect("verbatim court text", m["court_text"],
           "The mandatory nature of the death sentence as provided for under section 204")
    m = filing.match_quote("The Mandatory nature of the death-sentence, as provided for under Section 204", JT)
    expect("case, dash, comma ignored", m["result"], "verbatim")
    m = filing.match_quote("The mandatory nature of the death sentence ... is hereby declared unconstitutional", JT)
    expect("ellipsis", m["result"], "verbatim")
    m = filing.match_quote("is hereby declared unconstitutional … The mandatory nature of the death sentence", JT)
    expect("ellipsis parts out of order", m["result"] == "verbatim", False)
    m = filing.match_quote("The mandatory nature of the death sentence as provided for under section 204 of the Penal "
                           "Code is declared unconstitutional", JT)
    expect("close", (m["result"], m["similarity"]), ("close", 0.95))
    m = filing.match_quote("The death sentence is abolished for every offence in the Republic of Kenya", JT)
    expect("not found", (m["result"], m["court_text"]), ("not_found", None))

    text = ("1. In Okuta v AG [2017] KEHC 8382 (KLR) and Muruatetu v Republic [2017] KESC 2 (KLR) the court said "
            "\"the mandatory nature of the death sentence is unconstitutional\" and \"too short to check\".\n\n"
            "2. Elsewhere it was said that \"a quote with no case citation in its paragraph is skipped\".")
    q = filing.find_quotes(text, filing.find_cases(text))
    expect("quote to nearest citation", dict(q), {1: ["the mandatory nature of the death sentence is unconstitutional"]})
```

and call it in `main()`:

```python
def main():
    test_cases()
    test_quotes()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m api.test_filing`
Expected: `AttributeError: module 'api.filing' has no attribute 'match_quote'`

- [ ] **Step 3: Write minimal implementation**

In `api/filing.py`, extend the imports:

```python
import collections
import difflib
import re
```

add constants under `NOT_A_PARTY`:

```python
QUOTE = re.compile(r"[“\"]([^”\"]+)[”\"]")
MIN_QUOTE_WORDS = 8
ELLIPSIS = re.compile(r"\.\s?\.\s?\.|…")
SHINGLE = 5    # words per shingle when locating a near-miss quote
CLOSE = 0.85   # difflib ratio at or above which a quote is "close" rather than "not found"
```

and append:

```python
def blocks(text):
    """(start, end) of each blank-line-separated paragraph of the filing."""
    return [(m.start(), m.end()) for m in re.finditer(r"\S(?:.|\n(?!\s*\n))*", text)]


def find_quotes(text, cases):
    """{case index: [quote, ...]}: quotes of MIN_QUOTE_WORDS or more words, each given to the nearest case citation
    in its paragraph. A quote in a paragraph without a case citation is skipped (slice 2)."""
    out = collections.defaultdict(list)
    for start, end in blocks(text):
        here = [i for i, c in enumerate(cases) if start <= c["char_start"] < end]
        for q in QUOTE.finditer(text, start, end) if here else ():
            if len(WORD.findall(q[1])) >= MIN_QUOTE_WORDS:
                out[min(here, key=lambda i: abs(cases[i]["char_start"] - q.start()))].append(q[1])
    return out


def tokens(s):
    """(lowercased word, start, end) for every word: quote marks, dashes, brackets and spacing drop out."""
    return [(m.group().lower(), m.start(), m.end()) for m in WORD.finditer(s)]


def find_run(words, run, start):
    n = len(run)
    return next((i for i in range(start, len(words) - n + 1) if words[i:i + n] == run), None)


def match_quote(quote, text):
    """Compare words only. An ellipsis splits the quote into parts that must appear in order. Failing that, the
    passage sharing the most 5-word runs with the quote is scored with difflib: close, or not found (the nearest
    passage is still returned so the reader can compare)."""
    doc = tokens(text)
    words = [w for w, _, _ in doc]
    parts = [p for p in ([w for w, _, _ in tokens(part)] for part in ELLIPSIS.split(quote)) if p]
    at, hits = 0, []
    for p in parts:
        j = find_run(words, p, at)
        if j is None:
            break
        hits.append(j)
        at = j + len(p)
    else:
        return {"result": "verbatim", "similarity": 1.0, "court_text": text[doc[hits[0]][1]:doc[at - 1][2]],
                "char_start": doc[hits[0]][1]}
    flat = [w for p in parts for w in p]
    n = min(SHINGLE, len(flat))
    index = collections.defaultdict(list)
    for j in range(len(words) - n + 1):
        index[tuple(words[j:j + n])].append(j)
    votes = collections.Counter(j - k for k in range(len(flat) - n + 1) for j in index.get(tuple(flat[k:k + n]), ()))
    if not votes:
        return {"result": "not_found", "similarity": None, "court_text": None, "char_start": None}
    s = max(votes.most_common(1)[0][0], 0)
    e = min(s + len(flat), len(words))
    ratio = round(difflib.SequenceMatcher(None, flat, words[s:e], autojunk=False).ratio(), 2)
    return {"result": "close" if ratio >= CLOSE else "not_found", "similarity": ratio,
            "court_text": text[doc[s][1]:doc[e - 1][2]], "char_start": doc[s][1]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m api.test_filing`
Expected: `all passed`

- [ ] **Step 5: Commit**

```bash
git add api/filing.py api/test_filing.py
git commit -m "Filing checker: find quotes and match them against judgment text"
```

---

### Task 3: Judgment text from disk or R2

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add boto3`)
- Modify: `api/filing.py`
- Test: `api/test_filing.py`

**Interfaces:**
- Produces: `judgment_text(raw_path: str) -> str` (the `text` field of the parsed judgment JSON; `""` if empty). Raises on fetch failure; callers decide what that means. `raw_path` is `judgments.raw_path`, e.g. `parsed/judgment/akn_ke_judgment_kehc_2017_8382_eng@2017-02-06.json`, which is also the R2 key.

- [ ] **Step 1: Write the failing test**

Add to `api/test_filing.py` above `main()`:

```python
OKUTA = "parsed/judgment/akn_ke_judgment_kehc_2017_8382_eng@2017-02-06.json"


def test_text():
    expect("okuta text", "to the extent that it covers offences other than" in filing.judgment_text(OKUTA), True)
```

and in `main()` add `test_text()` after `test_quotes()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m api.test_filing`
Expected: `AttributeError: module 'api.filing' has no attribute 'judgment_text'`

- [ ] **Step 3: Add boto3 and implement**

Run: `uv add boto3`

In `api/filing.py`, extend the imports:

```python
import collections
import difflib
import functools
import json
import os
import re
from pathlib import Path
```

and append:

```python
@functools.cache
def _r2():
    import boto3   # only the API host needs it
    return boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT"], region_name="auto",
                        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])


@functools.lru_cache(maxsize=256)
def judgment_text(raw_path):
    """A judgment's text: from $LEXHACK_DATA when this machine has it, else the same key in R2 (scripts/sync.sh
    keeps the bucket a copy of the data folder; the API host has no data folder)."""
    local = os.environ.get("LEXHACK_DATA")
    path = Path(local).expanduser() / raw_path if local else None
    if path and path.exists():
        body = path.read_text(encoding="utf-8")
    else:
        body = _r2().get_object(Bucket=os.environ.get("R2_BUCKET", "lexhack-data"), Key=raw_path)["Body"].read()
    return json.loads(body)["text"] or ""
```

- [ ] **Step 4: Run test to verify it passes (disk path)**

Run: `uv run python -m api.test_filing`
Expected: `all passed`

- [ ] **Step 5: Smoke-test the R2 path**

Needs the read-only `R2_*` variables in the local `.env` (the same values Leo put on Railway). If they are missing, ask Leo to add them; do not skip this step silently.

Run: `LEXHACK_DATA= uv run python -c "from api.filing import judgment_text; t = judgment_text('parsed/judgment/akn_ke_judgment_kehc_2017_8382_eng@2017-02-06.json'); print(len(t), 'to the extent that' in t)"`
Expected: a length in the tens of thousands and `True`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock api/filing.py api/test_filing.py
git commit -m "Filing checker: read judgment text from the data folder or R2"
```

---

### Task 4: `check()`, `POST /api/check`, demo filings

**Files:**
- Create: `web/public/demo/clean.txt`, `web/public/demo/hallucinated.txt`, `web/public/demo/stale_law.txt`
- Modify: `api/filing.py`, `api/main.py`
- Test: `api/test_filing.py`

**Interfaces:**
- Consumes: `find_cases`, `names_agree`, `find_quotes`, `match_quote`, `judgment_text`; `pipeline.extract_citations.extract / pick_provision / provision_lookup / paragraph_markers / paragraph_at`; `api.status.provision_status`.
- Produces: `quote_check(quote: str, row: tuple | None) -> dict` and `check(conn, text: str) -> {"findings": [Finding dict]}`, findings sorted by `char_start`, each shaped like the spec's `Finding`. HTTP: `POST /api/check` body `{"text": str}` → `CheckReport` JSON; 413 above 200,000 characters.

- [ ] **Step 1: Write the demo filings**

`web/public/demo/clean.txt`:

```
SYNTHETIC FILING: written by the Hakiki team for demonstration. Not a real case or a real filing.

IN THE HIGH COURT OF KENYA AT NAIROBI
CRIMINAL APPEAL NO. E000 OF 2026 (SYNTHETIC)

WRITTEN SUBMISSIONS OF THE APPELLANT ON SENTENCE

1. The prosecution bears the burden of proof. Under section 107 of the Evidence Act, whoever desires a court to give judgment as to any legal right or liability dependent on the existence of facts which he asserts must prove that those facts exist.

2. The appellant was convicted of murder. On sentence, we rely on the Supreme Court's directions in Muruatetu & another v Republic [2021] KESC 31 (KLR), where the Court stated that "The decision of Muruatetu and these guidelines apply only in respect to sentences of murder under sections 203 and 204 of the Penal Code".

3. We therefore ask the Court to exercise its discretion on sentence.
```

`web/public/demo/hallucinated.txt`:

```
SYNTHETIC FILING: written by the Hakiki team for demonstration. It contains deliberate citation errors, to show what Hakiki flags. Not a real case or a real filing.

IN THE HIGH COURT OF KENYA AT NAIROBI
PETITION NO. E000 OF 2026 (SYNTHETIC)

SUBMISSIONS OF THE RESPONDENT

1. Criminal defamation remains an offence in Kenya. In Okuta v Attorney General [2017] KESC 2 (KLR) the Supreme Court upheld the offence.

2. The High Court in Jacqueline Okuta & another v Attorney General & 2 others [2017] KEHC 8382 (KLR) declared that "section 194 of the Penal Code is unconstitutional and invalid in its entirety and is struck out".

3. The Supreme Court in Muruatetu & another v Republic [2017] KESC 2 (KLR) held that "The mandatory nature of the death sentence as provided for under section 204 of the Penal Code is declared unconstitutional".

4. The same position was affirmed in Wanjiru v Republic [2019] KECA 99999 (KLR).
```

`web/public/demo/stale_law.txt`:

```
SYNTHETIC FILING: written by the Hakiki team for demonstration. It relies on sections that courts have limited or struck down. Not a real case or a real filing.

IN THE HIGH COURT OF KENYA AT NAIROBI
CRIMINAL CASE NO. E000 OF 2026 (SYNTHETIC)

SUBMISSIONS OF THE PROSECUTION ON SENTENCE

1. The accused has been convicted of murder. Section 204 of the Penal Code provides that any person convicted of murder shall be sentenced to death. The Court has no discretion and must impose the death sentence.

2. The accused is further charged with criminal defamation contrary to section 194 of the Penal Code, and with improper use of a licensed telecommunication system contrary to section 29 of the Kenya Information and Communications Act.
```

- [ ] **Step 2: Write the failing test**

Add to `api/test_filing.py` above `main()`:

```python
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "web" / "public" / "demo"


def test_quote_check_fallbacks():
    pdf_only = ("[2017] KEHC 1 (KLR)", "j", "t", "c", None, None, "parsed/judgment/x.json", False)
    expect("pdf-only judgment", filing.quote_check("any quote at all", pdf_only)["result"], "not_checked")
    real = filing.judgment_text
    def down(_):
        raise OSError("R2 unreachable")
    filing.judgment_text = down
    try:
        held = ("[2017] KEHC 8382 (KLR)", "j", "t", "c", None, None, OKUTA, True)
        expect("text unreachable", filing.quote_check("any quote at all", held)["result"], "not_checked")
    finally:
        filing.judgment_text = real


def summary(report):
    """[(kind, raw text, result, quote results or status)] for comparing a report in one line."""
    out = []
    for f in report["findings"]:
        if f["kind"] == "case":
            out.append(("case", f["raw_text"], f["case"]["result"], [q["result"] for q in f["quotes"]]))
        else:
            out.append(("section", f["raw_text"], f["section"]["result"], f["section"]["status"]))
    return out


def test_demos():
    from pipeline.db import connect
    with connect() as conn:
        clean = filing.check(conn, (DEMO / "clean.txt").read_text(encoding="utf-8"))
        bad = filing.check(conn, (DEMO / "hallucinated.txt").read_text(encoding="utf-8"))
        stale = filing.check(conn, (DEMO / "stale_law.txt").read_text(encoding="utf-8"))
    expect("clean", summary(clean), [
        ("section", "section 107 of the Evidence Act", "linked", "in force; no recorded court rulings"),
        ("case", "[2021] KESC 31 (KLR)", "found", ["verbatim"]),
        ("section", "sections 203 and 204 of the Penal Code", "linked", "in force; no recorded court rulings"),
        ("section", "sections 203 and 204 of the Penal Code", "linked", "limited by a court"),
    ])
    quote = next(f for f in clean["findings"] if f["kind"] == "case")["quotes"][0]
    expect("clean quote paragraph", quote["paragraph"], "18")
    expect("hallucinated", [s[:4] for s in summary(bad) if s[0] == "case"], [
        ("case", "[2017] KESC 2 (KLR)", "name_mismatch", []),
        ("case", "[2017] KEHC 8382 (KLR)", "found", ["not_found"]),
        ("case", "[2017] KESC 2 (KLR)", "found", ["close"]),
        ("case", "[2019] KECA 99999 (KLR)", "not_in_collection", []),
    ])
    expect("stale", summary(stale), [
        ("section", "Section 204 of the Penal Code", "linked", "limited by a court"),
        ("section", "section 194 of the Penal Code", "linked", "limited by a court"),
        ("section", "section 29 of the Kenya Information and Communications Act", "linked", "declared unconstitutional"),
    ])
    s204 = next(f for f in stale["findings"] if f["raw_text"] == "Section 204 of the Penal Code")["section"]
    expect("court's words shown", any("mandatory nature of the death sentence" in e["operative_quote"]
                                      for e in s204["summary_events"]), True)
```

Update `main()`:

```python
def main():
    test_cases()
    test_quotes()
    test_text()
    test_quote_check_fallbacks()
    test_demos()
    for f in fails:
        print("FAIL", *f)
    print("FAILED" if fails else "all passed")
    raise SystemExit(1 if fails else 0)
```

Move the `from pathlib import Path` import to the top of the file with the other import.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run python -m api.test_filing`
Expected: `AttributeError: module 'api.filing' has no attribute 'quote_check'`

- [ ] **Step 4: Implement `quote_check` and `check`**

In `api/filing.py`, add imports:

```python
import logging
from datetime import date

from pipeline.extract_citations import extract, paragraph_at, paragraph_markers, pick_provision, provision_lookup

from .status import provision_status

log = logging.getLogger(__name__)
```

and append:

```python
JUDGMENT_COLS = ("neutral_citation", "judgment_id", "title", "court", "decision_date", "source_url")


def quote_check(quote, row):
    """row: a judgments row as selected in check() (raw_path at 6, has_full_text at 7), or None if not held."""
    out = {"quote": quote, "result": "not_checked", "similarity": None, "court_text": None, "paragraph": None}
    if not row or not row[7]:
        return out
    try:
        text = judgment_text(row[6])
    except Exception:   # R2 or disk unreachable: this quote is unchecked, the rest of the report still stands
        log.warning("judgment text unavailable: %s", row[6])
        return out
    m = match_quote(quote, text)
    para = paragraph_at(paragraph_markers(text), m["char_start"]) if m["char_start"] is not None else None
    return {**out, "result": m["result"], "similarity": m["similarity"], "court_text": m["court_text"],
            "paragraph": para}


def case_findings(conn, text):
    cases = find_cases(text)
    held = {r[0]: r for r in conn.execute(
        """SELECT neutral_citation, judgment_id, title, court, decision_date::text, source_url, raw_path, has_full_text
           FROM judgments WHERE neutral_citation = ANY(%s) AND duplicate_of IS NULL""",
        ([c["citation"] for c in cases],))}
    quotes = find_quotes(text, cases)
    out = []
    for i, c in enumerate(cases):
        row = held.get(c["citation"])
        result = ("not_in_collection" if not row else
                  "found" if names_agree(c["cited_name"], row[2]) else "name_mismatch")
        out.append({"kind": "case", "raw_text": c["raw_text"], "char_start": c["char_start"],
                    "char_end": c["char_end"], "section": None,
                    "case": {"result": result, "cited_name": c["cited_name"],
                             "judgment": dict(zip(JUDGMENT_COLS, row[:6])) if row else None},
                    "quotes": [quote_check(q, row) for q in quotes.get(i, [])]})
    return out


def section_findings(conn, text):
    mentions = list(extract(text))   # no decision date: "Article N" is the 2010 Constitution
    lookup = provision_lookup(conn)
    pids = [pick_provision(lookup, m["act_id"], m["section_ref"], date.today()) if m["act_id"] else None
            for m in mentions]
    refs = {r[0]: dict(zip(("provision_id", "act_id", "act_title", "number", "heading"), r)) for r in conn.execute(
        """SELECT p.provision_id, p.act_id, a.title, p.number, p.heading FROM provisions p JOIN acts a USING (act_id)
           WHERE p.provision_id = ANY(%s)""", ([p for p in pids if p],))}
    status = {p: provision_status(conn, p) for p in refs}
    return [{"kind": "section", "raw_text": m["raw_text"], "char_start": m["char_start"], "char_end": m["char_end"],
             "case": None, "quotes": [],
             "section": {"result": "linked" if p else "not_covered", "act_ref": m["act_ref"], "provision": refs.get(p),
                         "status": status[p]["status"] if p else None,
                         "summary_events": status[p]["summary_events"] if p else []}}
            for m, p in zip(mentions, pids)]


def check(conn, text):
    """-> {"findings": [...]} in document order, each shaped like api.main.Finding."""
    return {"findings": sorted(case_findings(conn, text) + section_findings(conn, text),
                               key=lambda f: f["char_start"])}
```

Note: `extract()` gives a list like "sections 203 and 204" one mention per section, with the same `raw_text` and span; the sort is stable, so they stay in 203, 204 order.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m api.test_filing`
Expected: `all passed`. If `hallucinated` shows a different quote result for `[2017] KEHC 8382`, print `bad["findings"]` and check the quote against the judgment before changing the expectation; the misquote ("in its entirety and is struck out") must never come back `verbatim` or `close`.

- [ ] **Step 6: Add the endpoint**

In `api/main.py`, change the import line `from .status import provision_status, statuses` to:

```python
from . import filing
from .status import provision_status, statuses
```

After the `Stats` model add:

```python
MAX_FILING = 200_000   # characters


class CheckRequest(BaseModel):
    text: str


class JudgmentRef(BaseModel):
    judgment_id: str
    title: str
    court: str | None
    decision_date: str | None
    neutral_citation: str | None
    source_url: str | None


class CaseCheck(BaseModel):
    result: str                    # found | name_mismatch | not_in_collection (we hold ~10%: never "fake")
    cited_name: str | None         # the case name the filing gives before the citation
    judgment: JudgmentRef | None   # ours, for found and name_mismatch


class QuoteCheck(BaseModel):
    quote: str                     # as written in the filing
    result: str                    # verbatim | close | not_found | not_checked (judgment not held or text unreachable)
    similarity: float | None
    court_text: str | None         # the judgment's words at the match; for not_found, the nearest passage if any
    paragraph: str | None          # judgment paragraph of that passage


class SectionCheck(BaseModel):
    result: str                    # linked | not_covered (a law we don't hold, or a section we can't resolve)
    act_ref: str | None
    provision: ProvisionRef | None
    status: str | None
    summary_events: list[Event]    # the court's verbatim words, as on the section page


class Finding(BaseModel):
    kind: str                      # case | section
    raw_text: str
    char_start: int                # offsets into the submitted text, in characters (code points)
    char_end: int
    case: CaseCheck | None
    quotes: list[QuoteCheck]
    section: SectionCheck | None


class CheckReport(BaseModel):
    findings: list[Finding]
    disclaimer: str
```

At the end of the routes add:

```python
@app.post("/api/check", response_model=CheckReport)
def check_filing(req: CheckRequest):
    """Every case and section citation in a pasted filing, with evidence (api/filing.py). The filing is not stored
    or logged."""
    if len(req.text) > MAX_FILING:
        raise HTTPException(413, f"filing longer than {MAX_FILING:,} characters")
    with db() as conn:
        res = filing.check(conn, req.text)
    return CheckReport(**res, disclaimer=DISCLAIMER)
```

- [ ] **Step 7: Exercise the endpoint**

Run: `uv run uvicorn api.main:app --port 8000` in the background, then:

```bash
python3 -c "import json; print(json.dumps({'text': open('web/public/demo/hallucinated.txt').read()}))" | curl -s -X POST localhost:8000/api/check -H 'Content-Type: application/json' -d @- | python3 -c "import json,sys; r=json.load(sys.stdin); print(len(r['findings']), r['disclaimer'])"
curl -s -X POST localhost:8000/api/check -H 'Content-Type: application/json' -d '{"text": ""}'
python3 -c "import json; print(json.dumps({'text': 'x' * 200001}))" | curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/check -H 'Content-Type: application/json' -d @-
```

Expected: a count (6: four cases, two sections) and the disclaimer; `{"findings":[],"disclaimer":"…"}`; `413`. Stop the server.

- [ ] **Step 8: Run the existing checks too**

Run: `uv run python -m api.test_status && uv run python -m api.test_filing`
Expected: `13/13 passed` and `all passed`.

- [ ] **Step 9: Commit**

```bash
git add api/filing.py api/main.py api/test_filing.py web/public/demo
git commit -m "Filing checker: POST /api/check and three synthetic demo filings"
```

---

### Task 5: Web page `/check`

**Files:**
- Modify: `web/lib/api.ts`, `web/lib/text.ts`, `web/lib/text.check.ts`, `web/app/layout.tsx`
- Create: `web/app/check/actions.ts`, `web/app/check/Checker.tsx`, `web/app/check/page.tsx`

**Interfaces:**
- Consumes: `POST /api/check` → `CheckReport` (Task 4); `API_URL` from `web/lib/api.ts`; `cap`, `courtActed`, `sectionHref`, `plural` from `web/lib/format.ts`.
- Produces: TS types `CheckReport, Finding, CaseCheck, QuoteCheck, SectionCheck, JudgmentRef`; `splitAt(text, spans)` in `web/lib/text.ts`; server action `checkFiling`.

- [ ] **Step 1: Write the failing check for `splitAt`**

Append to `web/lib/text.check.ts` (add `splitAt` to its import from `./text.ts`):

```ts
// Offsets from the API are code points (Python); an emoji is two UTF-16 units, so slicing by JS index would shift.
assert.deepEqual(splitAt('😀 see [2017] KESC 2 now', [{ char_start: 6, char_end: 19 }]), [
  { text: '😀 see ', span: null },
  { text: '[2017] KESC 2', span: 0 },
  { text: ' now', span: null },
])
assert.deepEqual(
  splitAt('ab cd', [{ char_start: 0, char_end: 5 }, { char_start: 3, char_end: 5 }]).map((p) => p.span),
  [null, 0, null],
) // overlapping citations: the earlier is marked
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && pnpm check`
Expected: fails with `splitAt` not exported (SyntaxError / TypeError on import).

- [ ] **Step 3: Implement `splitAt`**

Append to `web/lib/text.ts`:

```ts
/** Cut text into plain runs and citation runs. The API's offsets are code points (Python), so slice by code point,
 * not by UTF-16 index; a span overlapping the previous one is left unmarked. */
export function splitAt(text: string, spans: { char_start: number; char_end: number }[]) {
  const cps = Array.from(text)
  const out: { text: string; span: number | null }[] = []
  let at = 0
  spans.forEach((s, i) => {
    if (s.char_start < at) return
    out.push({ text: cps.slice(at, s.char_start).join(''), span: null })
    out.push({ text: cps.slice(s.char_start, s.char_end).join(''), span: i })
    at = s.char_end
  })
  out.push({ text: cps.slice(at).join(''), span: null })
  return out
}
```

Run: `cd web && pnpm check`
Expected: passes (no output, exit 0).

- [ ] **Step 4: Add the report types**

Append to `web/lib/api.ts`:

```ts
export interface JudgmentRef {
  judgment_id: string
  title: string
  court: string | null
  decision_date: string | null
  neutral_citation: string | null
  source_url: string | null
}

export interface CaseCheck {
  result: 'found' | 'name_mismatch' | 'not_in_collection'
  cited_name: string | null
  judgment: JudgmentRef | null
}

export interface QuoteCheck {
  quote: string
  result: 'verbatim' | 'close' | 'not_found' | 'not_checked'
  similarity: number | null
  court_text: string | null // the judgment's words at the match; for not_found, the nearest passage if any
  paragraph: string | null
}

export interface SectionCheck {
  result: 'linked' | 'not_covered'
  act_ref: string | null
  provision: ProvisionRef | null
  status: string | null
  summary_events: CourtEvent[]
}

export interface Finding {
  kind: 'case' | 'section'
  raw_text: string
  char_start: number // code points into the checked text
  char_end: number
  case: CaseCheck | null
  quotes: QuoteCheck[]
  section: SectionCheck | null
}

export interface CheckReport {
  findings: Finding[]
  disclaimer: string
}
```

- [ ] **Step 5: Server action**

Create `web/app/check/actions.ts`:

```ts
'use server'
import { API_URL, type CheckReport } from '@/lib/api'

export interface CheckState {
  text: string // the text that was checked, which the report's offsets refer to
  report: CheckReport | null
  error: string | null
}

export async function checkFiling(_prev: CheckState, form: FormData): Promise<CheckState> {
  // A textarea submits \r\n; normalise so the offsets the API returns match the text the report is drawn from.
  const text = String(form.get('text') ?? '').replace(/\r\n?/g, '\n')
  if (!text.trim()) return { text, report: null, error: 'Paste a filing first.' }
  try {
    const res = await fetch(`${API_URL}/api/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      cache: 'no-store',
    })
    if (res.status === 413) return { text, report: null, error: 'That filing is too long: the limit is 200,000 characters.' }
    if (!res.ok) return { text, report: null, error: `The checker answered ${res.status}. Try again in a moment.` }
    return { text, report: await res.json(), error: null }
  } catch {
    return { text, report: null, error: 'The checker is unreachable. Try again in a moment.' }
  }
}
```

- [ ] **Step 6: The checker component**

Create `web/app/check/Checker.tsx`:

```tsx
'use client'
import Link from 'next/link'
import { useActionState, useState } from 'react'
import type { CaseCheck, Finding, QuoteCheck, SectionCheck } from '@/lib/api'
import { cap, courtActed, sectionHref } from '@/lib/format'
import { splitAt } from '@/lib/text'
import { checkFiling, type CheckState } from './actions'

const DEMOS = [
  ['clean', 'Sound citations'],
  ['hallucinated', 'Invented and misquoted'],
  ['stale_law', 'Relies on struck-down law'],
] as const

/** A finding worth a second look: a case we can't match, words not found as quoted, or a section a court acted on. */
function needsLook(f: Finding) {
  if (f.case) return f.case.result !== 'found' || f.quotes.some((q) => q.result === 'close' || q.result === 'not_found')
  return !!f.section?.status && courtActed(f.section.status)
}

export function Checker() {
  const [state, action, pending] = useActionState<CheckState, FormData>(checkFiling, { text: '', report: null, error: null })
  const [text, setText] = useState('')

  async function loadDemo(name: string) {
    setText(await (await fetch(`/demo/${name}.txt`)).text())
  }

  return (
    <div className="mt-8">
      <form action={action}>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2 text-sm text-ink-2">
          <span>Try a synthetic filing:</span>
          {DEMOS.map(([name, label]) => (
            <button key={name} type="button" onClick={() => loadDemo(name)} className="underline decoration-rule underline-offset-4 hover:text-ink">
              {label}
            </button>
          ))}
        </div>
        <label htmlFor="filing" className="sr-only">
          Filing text
        </label>
        <textarea
          id="filing"
          name="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={14}
          maxLength={200000}
          placeholder="Paste a submission, pleading or judgment."
          className="statute mt-3 w-full rounded-sm border border-rule bg-paper p-4 text-[1.02rem] leading-relaxed focus:border-ink focus:outline-none"
        />
        <button type="submit" disabled={pending} className="mt-3 rounded-sm bg-ink px-5 py-2 text-paper disabled:opacity-60">
          {pending ? 'Checking…' : 'Check citations'}
        </button>
        {state.error && <p className="mt-3 text-seal" role="alert">{state.error}</p>}
      </form>
      {state.report && <Report text={state.text} findings={state.report.findings} disclaimer={state.report.disclaimer} />}
    </div>
  )
}

function Report({ text, findings, disclaimer }: { text: string; findings: Finding[]; disclaimer: string }) {
  const flagged = findings.filter(needsLook).length
  return (
    <section className="mt-12" aria-labelledby="report">
      <h2 id="report" className="statute text-2xl">
        {findings.length ? `${findings.length} citations found; ${flagged} worth a second look` : 'No citations found'}
      </h2>
      <p className="mt-2 text-sm text-ink-2">{disclaimer}</p>
      {findings.length > 0 && (
        <div className="mt-6 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="statute max-h-[70vh] overflow-y-auto whitespace-pre-wrap rounded-sm border border-rule p-5 leading-relaxed">
            {splitAt(text, findings).map((p, i) =>
              p.span === null ? (
                <span key={i}>{p.text}</span>
              ) : (
                <a key={i} href={`#f${p.span}`} className={needsLook(findings[p.span]) ? 'bg-seal/15 text-seal underline' : 'bg-panel underline decoration-rule'}>
                  {p.text}
                </a>
              ),
            )}
          </div>
          <ol className="divide-y divide-rule border-y border-rule">
            {findings.map((f, i) => (
              <li key={i} id={`f${i}`} className="py-5">
                <p className="statute text-lg">{f.raw_text}</p>
                {f.case && <CaseLine c={f.case} />}
                {f.quotes.map((q, j) => (
                  <QuoteLine key={j} q={q} />
                ))}
                {f.section && <SectionLine s={f.section} />}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}

function CaseLine({ c }: { c: CaseCheck }) {
  const j = c.judgment
  if (c.result === 'not_in_collection')
    return (
      <p className="mt-1 text-ink-2">
        Not in our collection. We hold about 10% of published Kenyan judgments, so this does not show the case doesn’t exist; check it on Kenya Law.
      </p>
    )
  return (
    <p className={`mt-1 ${c.result === 'name_mismatch' ? 'text-seal' : 'text-ink-2'}`}>
      {c.result === 'name_mismatch' ? `This citation belongs to a different case in our collection. The filing calls it “${c.cited_name}”; the citation is ` : 'In our collection: '}
      {j?.source_url ? (
        <a href={j.source_url} className="underline" target="_blank" rel="noreferrer">
          {j.title}
        </a>
      ) : (
        j?.title
      )}
      .
    </p>
  )
}

const QUOTE_LABEL: Record<QuoteCheck['result'], string> = {
  verbatim: 'Quoted words appear word for word in the judgment',
  close: 'Quoted words are close to the judgment but not word for word',
  not_found: 'Quoted words were not found in the judgment',
  not_checked: 'Quoted words not checked: we don’t hold this judgment’s text',
}

function QuoteLine({ q }: { q: QuoteCheck }) {
  const off = q.result === 'close' || q.result === 'not_found'
  return (
    <div className="mt-3 border-l-2 border-rule pl-3">
      <p className={off ? 'text-seal' : 'text-ink-2'}>
        {QUOTE_LABEL[q.result]}
        {q.result === 'close' && q.similarity !== null && ` (${Math.round(q.similarity * 100)}% similar)`}
        {q.paragraph && `, paragraph ${q.paragraph}`}.
      </p>
      <p className="statute mt-1 text-ink-2">Filing: “{q.quote}”</p>
      {off && q.court_text && <p className="statute mt-1">{q.result === 'close' ? 'The court wrote' : 'Nearest passage'}: “{q.court_text}”</p>}
    </div>
  )
}

function SectionLine({ s }: { s: SectionCheck }) {
  if (s.result === 'not_covered' || !s.provision)
    return <p className="mt-1 text-ink-2">{s.act_ref ? `${s.act_ref}: not` : 'Not'} a section Hakiki covers yet.</p>
  const p = s.provision
  return (
    <div className="mt-1">
      <p className={s.status && courtActed(s.status) ? 'text-seal' : 'text-ink-2'}>
        <Link href={sectionHref(p.provision_id)} className="underline">
          {p.act_title}, s.{p.number}
        </Link>
        : {cap(s.status ?? '')}.
      </p>
      {s.summary_events.map((e) => (
        <blockquote key={e.event_id} className="statute mt-2 border-l-2 border-seal/60 pl-3">
          “{e.operative_quote}”
          <footer className="mt-1 text-sm text-ink-2">
            {e.source_url ? (
              <a href={e.source_url} className="underline" target="_blank" rel="noreferrer">
                {e.title}
              </a>
            ) : (
              e.title
            )}
            {e.source_paragraph && `, para ${e.source_paragraph}`}
          </footer>
        </blockquote>
      ))}
    </div>
  )
}
```

- [ ] **Step 7: The page and nav link**

Create `web/app/check/page.tsx`:

```tsx
import type { Metadata } from 'next'
import { Checker } from './Checker'

export const metadata: Metadata = { title: 'Check a filing' }

export default function CheckPage() {
  return (
    <div className="pt-10">
      <h1 className="statute text-3xl">Check a filing</h1>
      <p className="mt-3 max-w-[68ch] text-ink-2">
        Paste a submission, pleading or judgment. Hakiki finds each case and section it cites and reports what the sources say: whether we hold the case, whether quoted
        words appear in it, and what courts have done to each section. Your text is not stored.
      </p>
      <Checker />
    </div>
  )
}
```

In `web/app/layout.tsx`, inside `<nav … aria-label="Main">`, add after the Acts link:

```tsx
              <Link href="/check" className="hover:text-ink">
                Check a filing
              </Link>
```

- [ ] **Step 8: Lint, type-check, build**

Run: `cd web && pnpm lint && pnpm check && pnpm build`
Expected: no errors. (Tailwind classes `bg-seal/15`, `bg-panel`, `border-rule`, `text-seal` already exist in the theme; `grep -rn "bg-panel\|text-seal" web/app web/components` confirms.)

- [ ] **Step 9: Run it and look**

Start the API (`uv run uvicorn api.main:app --reload`) and the web (`cd web && pnpm dev`; kill any stale `next-server` first). Open `http://localhost:3000/check`, then for each demo button: load, check, and confirm:
- "Invented and misquoted": `[2017] KESC 2` in paragraph 1 is flagged as a different case (Muruatetu); the Okuta quote shows "not found" with the nearest passage; the Muruatetu quote shows "close (95% similar)" and the court's words; `[2019] KECA 99999` reads "Not in our collection…".
- "Relies on struck-down law": ss.204, 194 and KICA s.29 are highlighted, each card quoting the court's order with a link.
- Paste the clean filing with an emoji added at the top (e.g. `😀 `): highlights still sit exactly on the citations.

Record a short GIF with the claude-in-chrome `gif_creator` if available (`filing_checker_demo.gif`).

- [ ] **Step 10: Commit**

```bash
git add web/lib/api.ts web/lib/text.ts web/lib/text.check.ts web/app/check web/app/layout.tsx
git commit -m "Web: Check a filing page with demo filings"
```

---

### Task 6: Docs and deploy check

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: README**

Add a subsection after the API section (README §7c; find it with `grep -n "^### 7c\|^## 7c" README.md`) titled `### The filing checker (slice 1)` covering: what the three checks are and their result values (copy the lists from the spec's API section), that `not_in_collection` never means fake, that judgment text is read from `$LEXHACK_DATA` or R2 (`R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, read-only token), the demo filings in `web/public/demo/` (synthetic), `uv run python -m api.test_filing`, and what slice 2 adds (eKLR and name-only matching, PDF/DOCX, an agent-labelled benchmark, quotes away from their citation).

- [ ] **Step 2: CLAUDE.md**

In "Where we are": add a done item "9. **Filing checker, slice 1** (2026-09-28): `api/filing.py`, `POST /api/check`, `web/app/check/`, three synthetic demo filings; tests `api.test_filing`." Replace "Next" item 1 with "**Filing checker slice 2**: `[YYYY] eKLR` and case-name matching, PDF/DOCX upload, agent-labelled benchmark, quotes away from their citation." Remove the "Before the presentation…" sentences (the presentation happened on 2026-09-27) but keep the verification as a to-do: "Confirm the live Kenya Law pages still lack court notes." In the Repo layout, `docs/superpowers/` holds specs and plans.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Docs: filing checker slice 1"
```

- [ ] **Step 4: Hand over for deploy**

Tell Leo: push with `! git push`; Railway redeploys the API (needs `boto3` from `uv.lock` and the `R2_*` vars he set); Cloudflare rebuilds the web. After deploy, run:

```bash
python3 -c "import json; print(json.dumps({'text': open('web/public/demo/hallucinated.txt').read()}))" | curl -s -X POST https://api-production-0506.up.railway.app/api/check -H 'Content-Type: application/json' -d @- | python3 -c "import json,sys; r=json.load(sys.stdin); print([(f['raw_text'], (f['case'] or f['section'])['result'], [q['result'] for q in f['quotes']]) for f in r['findings']])"
```

Expected: the same results as the local test, in particular `['not_found']` and `['close']` quote results, which prove the API host reads judgment text from R2 (it has no data folder).
