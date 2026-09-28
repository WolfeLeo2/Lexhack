# Filing Checker 2a: eKLR Matching and Benchmark, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The filing checker reads `Name [YYYY] eKLR` citations (half of real citations), matches them to judgments we hold by party names, case number and quotes, and a benchmark labelled by agents says how often it is right.

**Architecture:** `api/filing.py` gains eKLR detection, a title index (IDF-weighted party words per year, loaded once per process), `rank_eklr` + `decide` (thresholds are parameters so the benchmark can tune them), and a quote tie-break inside `case_findings`. The API contract gains `form`, `match_basis`, `candidates` and the `possible_match` result. The benchmark lives in `ground_truth/filing_*`: a sampler, a labeller agent type, a merge script and `eval_filing.py` (metrics, tuning, planted errors).

**Tech Stack:** Python (uv), psycopg, FastAPI/Pydantic; Next.js 16 client component; Claude agents (`.claude/agents/citation-labeler.md`).

**Spec:** `docs/superpowers/specs/2026-09-28-filing-checker-2a-eklr-design.md` (slice 1: `docs/superpowers/specs/2026-09-28-filing-checker-design.md`)

## Global Constraints

- Never a verdict, never "fake". `not_in_collection` copy keeps the ~10% caveat; `possible_match` is always worded as possible.
- Thresholds are tuned on **dev only**; **test** is scored once and that number is the one quoted.
- Labellers never see the checker's answers or gold files; two blind labels per item, a third agent decides disagreements.
- Starting thresholds: `FOUND_SCORE = 0.8`, `FOUND_MARGIN = 0.25`, `POSSIBLE_SCORE = 0.5`, `MIN_SHARED = 4.0`.
- Data paths from `LEXHACK_DATA`; agent working files under `$LEXHACK_DATA/review/filing/`.
- Commits straight to `main`, no `Co-Authored-By` line. Claude's shell: run from the repo root, use absolute tool paths (`cd web` has wiped PATH before); never run `next build` while `next dev` runs.
- UI: full creative latitude (CLAUDE.md); respect reduced motion.

## Review Focus

1. **A common surname alone** ("Mwangi v Republic [2019] eKLR", many Mwangi titles that year). Expect `possible_match` or `not_in_collection`, never a confident `found` on a guess. Pinned in Task 2 (`MIN_SHARED` and margin test).
2. **A case number from an earlier sentence** sitting in the 300 characters before the citation. Expect it ignored. Pinned in Task 1.
3. **An eKLR year with no judgments held** (e.g. 1950). Expect `not_in_collection`, no crash. Pinned in Task 2.
4. **Two candidates and a quote found in both** (identical texts). Expect `possible_match` stays; the tie-break needs exactly one. Pinned in Task 3.
5. **Label files with an item missing or malformed** (an agent stopped early). Expect the merge to list missing items and refuse to write gold. Pinned in Task 6.

---

## File Structure

- Modify `api/filing.py`: eKLR detection, name tokens, title index, `rank_eklr`, `decide`, `match_eklr`; `case_findings` handles both forms.
- Modify `api/test_filing.py`: tests for all of the above; demo expectations.
- Modify `api/main.py`: `CaseCheck` fields.
- Modify `web/public/demo/clean.txt`, `hallucinated.txt`: eKLR citations.
- Modify `web/lib/api.ts`, `web/app/check/Checker.tsx`: new fields, possible-match cards, basis line, empty-report copy.
- Create `ground_truth/filing_sample.py`: dev/test items, title lists, labelling batches.
- Create `.claude/agents/citation-labeler.md`: the labeller.
- Create `ground_truth/filing_merge.py`: labels → gold, agreement.
- Create `ground_truth/eval_filing.py`: metrics, `--tune`, `--planted`.
- Modify `README.md`, `CLAUDE.md`, `web/app/about/page.tsx`: results.

---

### Task 1: eKLR detection, case numbers, name tokens (pure)

**Files:** Modify `api/filing.py`, `api/test_filing.py`

**Interfaces:**
- Produces: `find_eklr(text) -> list[dict]` with keys `raw_text, char_start, char_end, form='eklr', year:int, citation=None, cited_name, case_number`; `find_cases` dicts gain `form='neutral'`; `case_number(s) -> str | None` ("397 of 2016"); `name_tokens(name) -> set[str]`; `party_part(title) -> str`.

- [ ] **Step 1: Write the failing test.** Add above `main()` in `api/test_filing.py`, and call `test_eklr()` first in `main()`:

```python
def test_eklr():
    t = ("the High Court in Jacqueline Okuta & another v Attorney General & 2 others (Petition No. 397 of 2016) "
         "[2017] eKLR held")
    e = filing.find_eklr(t)
    expect("eklr found", [(x["raw_text"], x["year"], x["form"]) for x in e], [("[2017] eKLR", 2017, "eklr")])
    expect("eklr name, number taken out", (e[0]["cited_name"], e[0]["case_number"]),
           ("Jacqueline Okuta & another v Attorney General & 2 others", "397 of 2016"))
    e = filing.find_eklr("relied on Gatirau Peter Munya vs Dickson Mwenda Kithinji & 3 Others [2014]eKLR relied upon")
    expect("no space, vs", (e[0]["year"], e[0]["cited_name"], e[0]["case_number"]),
           (2014, "Gatirau Peter Munya vs Dickson Mwenda Kithinji & 3 Others", None))
    e = filing.find_eklr("Civil Appeal No. 5 of 2019. In Salesio M’tonga v M’ithara & 3 others [2015] eKLR the")
    expect("earlier case number ignored", (e[0]["cited_name"], e[0]["case_number"]),
           ("Salesio M’tonga v M’ithara & 3 others", None))
    expect("case number normalised", filing.case_number("Petition E009 of 2023"), "E009 of 2023")
    expect("no case number", filing.case_number("Petition"), None)
    expect("name tokens keep initials", filing.name_tokens("JAC vs PW"), {"jac", "pw"})
    expect("name tokens drop case words", filing.name_tokens("Okuta v AG (Petition"), {"okuta"})
    expect("party part", filing.party_part(MURUATETU), "Muruatetu & another v Republic")
    expect("neutral form", filing.find_cases("[2017] KESC 2 (KLR)")[0]["form"], "neutral")
```

- [ ] **Step 2: Run it.** `uv run python -m api.test_filing` → Expected: `AttributeError: module 'api.filing' has no attribute 'find_eklr'`.

- [ ] **Step 3: Implement.** In `api/filing.py`:

Extend `NOT_A_PARTY` with case-kind words and "ag":

```python
NOT_A_PARTY = {"and", "another", "others", "the", "of", "in", "see", "per", "also", "held", "case", "matter", "court",
               "supreme", "appeal", "high", "republic", "attorney", "general", "state", "county", "government",
               "director", "public", "prosecutions", "dpp", "ors", "anor", "ltd", "limited", "kenya", "commission",
               "national", "ex", "parte", "re", "klr", "eklr", "ag", "petition", "civil", "criminal", "application",
               "suit", "cause", "misc", "miscellaneous", "hccc", "constitutional", "election", "judicial", "review",
               "succession", "reference", "no", "consolidated", "formerly", "number"}
```

Add after `NEUTRAL`:

```python
EKLR = re.compile(r"\[(?P<year>\d{4})\]\s*eKLR")
CASE_NO = re.compile(r"(?:No\.?\s*)?\b(?P<num>[A-Z]?\d+[A-Z]?)\s+of\s+(?P<y>(?:19|20)\d{2})\b")
V_WORD = re.compile(r"\sv(?:s)?\.?\s")
```

`find_cases` adds `"form": "neutral"` to each dict. Append:

```python
def case_number(s):
    """'Petition No. 397 of 2016' -> '397 of 2016'. The kind is dropped: filings write HCCC, Pet. or Constitutional
    Petition for the same case."""
    hits = list(CASE_NO.finditer(s or ""))
    return f"{hits[-1]['num'].upper()} of {hits[-1]['y']}" if hits else None


def eklr_context(text, start):
    """(case name, case number) for an eKLR citation at `start`. A case number counts only between the name's "v" and
    the citation ('Okuta v AG (Petition No. 397 of 2016) [2017] eKLR'); it is cut out before the name is read."""
    pre = text[max(0, start - 300):start]
    vs = list(V_WORD.finditer(pre))
    number = None
    if vs:
        hits = list(CASE_NO.finditer(pre, vs[-1].end()))
        if hits:
            number = f"{hits[-1]['num'].upper()} of {hits[-1]['y']}"
            pre = re.sub(r"\s*\([^()]*$", "", pre[:hits[-1].start()]).rstrip(" ,;")
    return cited_name(pre, len(pre)), number


def find_eklr(text):
    out = []
    for m in EKLR.finditer(text):
        name, number = eklr_context(text, m.start())
        out.append({"raw_text": m.group(0), "char_start": m.start(), "char_end": m.end(), "form": "eklr",
                    "year": int(m["year"]), "citation": None, "cited_name": name, "case_number": number})
    return out


def party_part(title):
    """The parties in one of our titles: 'Muruatetu & another v Republic; Katiba Institute… (Petition…) [2017]…'."""
    return re.split(r"\s\(|\s\[|;", title or "", maxsplit=1)[0]


def name_tokens(name):
    """Party words of a case name: words of 3+ letters, and all-caps initials ('JAC v PW'); generic words dropped."""
    return {w.lower() for w in WORD.findall(name or "")
            if (len(w) > 2 or (len(w) > 1 and w.isupper())) and not w.isdigit() and w.lower() not in NOT_A_PARTY}
```

- [ ] **Step 4: Run it.** `uv run python -m api.test_filing` → Expected: `all passed` (the fallback test's "judgment text unavailable" warning line is expected).

- [ ] **Step 5: Commit.** `git add api/filing.py api/test_filing.py && git commit -m "Filing checker: detect eKLR citations, their case names and numbers"`

---

### Task 2: Title index, ranking and the decision rule

**Files:** Modify `api/filing.py`, `api/test_filing.py`

**Interfaces:**
- Consumes: `name_tokens`, `party_part`, `case_number` (Task 1).
- Produces: `JUDGMENT_ROW` column order `(neutral_citation, judgment_id, title, court, decision_date, source_url, raw_path, has_full_text, case_number, year)`; `build_index(rows) -> {"idf": dict, "by_year": {year: [(row, tokens, number)]}}`; `title_index(conn)` (cached); `rank_eklr(index, year, name, number, min_shared=MIN_SHARED) -> [(score, row, by_number)]` best first; `decide(ranked, found_score=FOUND_SCORE, margin=FOUND_MARGIN, possible=POSSIBLE_SCORE) -> {"result", "basis", "rows"}`; `match_eklr(index, year, name, number) = decide(rank_eklr(...))`. Rows keep slice 1's positions 0–7, so `case_text(row, …)` and `JUDGMENT_COLS` work unchanged.

- [ ] **Step 1: Write the failing test.** Add above `main()` and call `test_ranking()` after `test_eklr()`:

```python
def fake_index(rows):
    """rows: (judgment_id, title, case_number, year) -> an index shaped like title_index()."""
    return filing.build_index([(None, jid, title, None, None, None, None, True, cn, y) for jid, title, cn, y in rows])


def test_ranking():
    idx = fake_index([("A", MURUATETU, "Petition 15 of 2015", 2017),
                      ("B", "Francis Mwangi v Republic", "Criminal Appeal 3 of 2016", 2017),
                      ("C", "Jacqueline Okuta & another v Attorney General & 2 others", "Petition 397 of 2016", 2017),
                      ("D", "John Ward v Standard Limited", "Civil Case 1062 of 2005", 2006),
                      ("E", "John Ward v Standard Limited", "Civil Case 1062 of 2005", 2006),
                      ("F", "Peter Mwangi v Republic", "Criminal Appeal 9 of 2019", 2019),
                      ("G", "James Mwangi v Republic", "Criminal Appeal 12 of 2019", 2019)]
                     + [(f"X{i}", f"Kamau{i} v Otieno{i}", None, 2010) for i in range(40)])
    def got(year, name, number=None):
        r = filing.decide(filing.rank_eklr(idx, year, name, number, min_shared=1.0))
        return r["result"], r["basis"], [row[1] for row in r["rows"]]
    expect("first names our title drops", got(2017, "Francis Karioko Muruatetu & another v Republic"),
           ("found", "party names and year", ["A"]))
    expect("case number", got(2017, "Jacqueline Okuta v AG", "397 of 2016"), ("found", "case number", ["C"]))
    expect("two same-name cases", got(2006, "John Ward v Standard Limited"), ("possible_match", None, ["D", "E"]))
    expect("unknown parties", got(2017, "Nobody Atall v Someone Else"), ("not_in_collection", None, []))
    expect("year we hold nothing for", got(1950, "Francis Mwangi v Republic"), ("not_in_collection", None, []))
    expect("common surname alone is never found", got(2019, "Mwangi v Republic")[0] != "found", True)
```

- [ ] **Step 2: Run it.** Expected: `AttributeError: module 'api.filing' has no attribute 'build_index'`.

- [ ] **Step 3: Implement.** Add `import math` to the imports. Add constants under `MAX_QUOTES`:

```python
# eKLR matching (spec 2a). Starting values; tuned on the dev set by ground_truth/eval_filing.py --tune.
FOUND_SCORE = 0.8     # best candidate's score needed for "found"
FOUND_MARGIN = 0.25   # ...and its lead over the runner-up
POSSIBLE_SCORE = 0.5  # candidates listed as a possible match
MIN_SHARED = 4.0      # shared party-word weight below this scores 0 (~ a word in more than ~250 of our titles)
```

Append:

```python
def build_index(rows):
    """rows in JUDGMENT_ROW order -> {"idf": word weight, "by_year": {year: [(row, party words, case number)]}}."""
    df, by_year = collections.Counter(), collections.defaultdict(list)
    for r in rows:
        words = name_tokens(party_part(r[2]))
        df.update(words)
        by_year[r[9]].append((r, words, case_number(r[8])))
    return {"idf": {w: math.log(len(rows) / n) for w, n in df.items()}, "by_year": by_year}


_INDEX = {}


def title_index(conn):
    """Every judgment we hold, indexed once per process (~16k titles, a few MB)."""
    if not _INDEX:
        _INDEX.update(build_index(conn.execute(
            """SELECT neutral_citation, judgment_id, title, court, decision_date::text, source_url, raw_path,
                      has_full_text, case_number, extract(year FROM decision_date)::int
               FROM judgments WHERE duplicate_of IS NULL""").fetchall()))
    return _INDEX


def name_score(cited, words, idf, min_shared):
    """Shared party-word weight over the better-covered side: our titles drop first names ('Muruatetu & another v
    Republic'), older titles carry names that filings abbreviate. Cited words in no title can't tell titles apart."""
    cited = {w for w in cited if w in idf}
    shared = sum(idf[w] for w in cited & words)
    if not cited or not words or shared < min_shared:
        return 0.0
    return shared / min(sum(idf[w] for w in cited), sum(idf[w] for w in words))


def rank_eklr(index, year, name, number, min_shared=MIN_SHARED):
    """[(score, row, matched on case number)] for the year's judgments, best first, zero scores dropped."""
    cited, idf, out = name_tokens(name), index["idf"], []
    for row, words, num in index["by_year"].get(year, ()):
        s = name_score(cited, words, idf, min_shared)
        by_number = bool(number) and num == number and (not cited or s > 0)
        if by_number or s > 0:
            out.append((1.0 if by_number else s, row, by_number))
    return sorted(out, key=lambda x: -x[0])


def decide(ranked, found_score=FOUND_SCORE, margin=FOUND_MARGIN, possible=POSSIBLE_SCORE):
    if ranked and ranked[0][0] >= found_score and ranked[0][0] - (ranked[1][0] if len(ranked) > 1 else 0) >= margin:
        return {"result": "found", "basis": "case number" if ranked[0][2] else "party names and year",
                "rows": [ranked[0][1]]}
    top = [row for s, row, _ in ranked if s >= possible][:3]
    return {"result": "possible_match" if top else "not_in_collection", "basis": None, "rows": top}


def match_eklr(index, year, name, number):
    return decide(rank_eklr(index, year, name, number))
```

- [ ] **Step 4: Run it.** Expected: `all passed`.

- [ ] **Step 5: Real-data check.** Add to `test_demos()` (it already opens a connection; put this inside a `with connect() as conn:` block at its start):

```python
    with connect() as conn:
        idx = filing.title_index(conn)
    def real(year, name, number=None):
        r = filing.match_eklr(idx, year, name, number)
        return r["result"], [row[1] for row in r["rows"]]
    expect("real Muruatetu", real(2017, "Francis Karioko Muruatetu & another v Republic"),
           ("found", ["ke/judgment/kesc/2017/2"]))
    expect("real Okuta", real(2017, "Jacqueline Okuta & another v Attorney General & 2 others"),
           ("found", ["ke/judgment/kehc/2017/8382"]))
    expect("real John Ward", real(2006, "John Ward v Standard Limited"),
           ("possible_match", ["ke/judgment/kehc/2006/2628", "ke/judgment/kehc/2006/2629"]))
```

If "real John Ward" lists the two ids in the other order, compare `sorted(...)` instead: order among equal scores carries no meaning. Run: `uv run python -m api.test_filing` → `all passed`.

- [ ] **Step 6: Commit.** `git add api/filing.py api/test_filing.py && git commit -m "Filing checker: rank eKLR candidates by weighted party names and case number"`

---

### Task 3: eKLR in the report: contract, quote tie-break, demo filings

**Files:** Modify `api/filing.py`, `api/main.py`, `api/test_filing.py`, `web/public/demo/clean.txt`, `web/public/demo/hallucinated.txt`

**Interfaces:**
- Consumes: Tasks 1–2; slice 1 `find_quotes`, `case_text`, `quote_check`, `match_quote`.
- Produces: case findings' `case` dict gains `form`, `match_basis`, `candidates` (list of `JudgmentRef` dicts); result may be `possible_match`. `CaseCheck` model gains `form: str`, `match_basis: str | None`, `candidates: list[JudgmentRef] = []`.

- [ ] **Step 1: Demo filings.** In `web/public/demo/clean.txt`, paragraph 2, after the Muruatetu 2021 quote's closing `".`, add the sentence: ` The directions followed the Court's judgment in Francis Karioko Muruatetu & another v Republic [2017] eKLR.` In `web/public/demo/hallucinated.txt`, after paragraph 4 add a blank line and:

```
5. See also John Ward v Standard Limited [2006] eKLR, where the court held that "the presence of the said Mr. Pravin Bowry before this court is necessary to enable the court to effectually and completely adjudicate upon and settle all the questions involved in the suit herein".

6. Finally, Tunutu Karamoja Traders v Olkaria Mbeere Holdings [2019] eKLR is directly in point.
```

- [ ] **Step 2: Write the failing tests.** In `test_demos()`, replace the `"clean"` and `"hallucinated"` expectations with:

```python
    expect("clean", summary(clean), [
        ("section", "section 107 of the Evidence Act", "linked", "in force; no recorded court rulings"),
        ("case", "[2021] KESC 31 (KLR)", "found", ["verbatim"]),
        ("section", "sections 203 and 204 of the Penal Code", "linked", "in force; no recorded court rulings"),
        ("section", "sections 203 and 204 of the Penal Code", "linked", "limited by a court"),
        ("case", "[2017] eKLR", "found", []),
    ])
    expect("hallucinated", [s[:4] for s in summary(bad) if s[0] == "case"], [
        ("case", "[2017] KESC 2 (KLR)", "name_mismatch", []),
        ("case", "[2017] KEHC 8382 (KLR)", "found", ["not_found"]),
        ("case", "[2017] KESC 2 (KLR)", "found", ["close"]),
        ("case", "[2019] KECA 99999 (KLR)", "not_in_collection", []),
        ("case", "[2006] eKLR", "found", ["verbatim"]),
        ("case", "[2019] eKLR", "not_in_collection", []),
    ])
    ward = next(f for f in bad["findings"] if f["raw_text"] == "[2006] eKLR")["case"]
    expect("quote settles two same-name cases", (ward["match_basis"], ward["judgment"]["judgment_id"], ward["candidates"]),
           ("quote", "ke/judgment/kehc/2006/2628", []))
    muru = next(f for f in clean["findings"] if f["raw_text"] == "[2017] eKLR")["case"]
    expect("eklr basis", (muru["form"], muru["match_basis"], muru["judgment"]["judgment_id"]),
           ("eklr", "party names and year", "ke/judgment/kesc/2017/2"))
    with connect() as conn:
        same = filing.check(conn, "In John Ward v Standard Limited [2006] eKLR the court said \"the defendant's "
                                  "application is allowed in terms of the prayers\".")["findings"][0]["case"]
    expect("no settling quote stays possible", (same["result"], len(same["candidates"])), ("possible_match", 2))
```

(The last quote is in neither judgment verbatim, so the tie stands; this pins Review Focus 4's "exactly one" rule.)

Run: `uv run python -m api.test_filing` → Expected: FAIL on "clean"/"hallucinated" (no eKLR findings yet).

- [ ] **Step 3: Implement.** Replace `case_findings` in `api/filing.py`:

```python
def case_findings(conn, text):
    cases = sorted(find_cases(text) + find_eklr(text), key=lambda c: c["char_start"])
    held = {r[0]: r for r in conn.execute(
        """SELECT neutral_citation, judgment_id, title, court, decision_date::text, source_url, raw_path, has_full_text
           FROM judgments WHERE neutral_citation = ANY(%s) AND duplicate_of IS NULL""",
        ([c["citation"] for c in cases if c["citation"]],))}
    index = title_index(conn) if any(c["form"] == "eklr" for c in cases) else None
    quotes = find_quotes(text, cases)
    texts, budget, out = {}, MAX_QUOTES, []
    for i, c in enumerate(cases):
        qs, candidates = quotes.get(i, []), []
        if c["form"] == "neutral":
            row = held.get(c["citation"])
            result = ("not_in_collection" if not row else
                      "found" if names_agree(c["cited_name"], row[2]) else "name_mismatch")
            basis = "neutral citation" if row else None
        else:
            m = match_eklr(index, c["year"], c["cited_name"], c["case_number"])
            result, basis = m["result"], m["basis"]
            row = m["rows"][0] if result == "found" else None
            candidates = m["rows"] if result == "possible_match" else []
            # a quote found word for word in exactly one candidate settles which case it is
            hits = [r for r in candidates
                    if (t := case_text(r, texts)) is not None and any(match_quote(q, t)["result"] == "verbatim" for q in qs)]
            if len(hits) == 1:
                result, basis, row, candidates = "found", "quote", hits[0], []
        out.append({"kind": "case", "raw_text": c["raw_text"], "char_start": c["char_start"],
                    "char_end": c["char_end"], "section": None, "quotes": [],
                    "case": {"result": result, "form": c["form"], "match_basis": basis, "cited_name": c["cited_name"],
                             "judgment": dict(zip(JUDGMENT_COLS, row[:6])) if row else None,
                             "candidates": [dict(zip(JUDGMENT_COLS, r[:6])) for r in candidates]}})
        for q in qs:
            out[-1]["quotes"].append(quote_check(q, case_text(row, texts) if budget > 0 else None))
            budget -= 1
    return out
```

In `api/main.py`, `CaseCheck` becomes:

```python
class CaseCheck(BaseModel):
    result: str                    # found | name_mismatch | possible_match | not_in_collection (never "fake")
    form: str                      # neutral ([2017] KESC 2 (KLR)) | eklr ([2017] eKLR)
    match_basis: str | None        # neutral citation | case number | party names and year | quote
    cited_name: str | None         # the case name the filing gives before the citation
    judgment: JudgmentRef | None   # ours, for found and name_mismatch
    candidates: list[JudgmentRef] = []   # possible_match: up to three, best first
```

- [ ] **Step 4: Run it.** `uv run python -m api.test_filing` → Expected: `all passed`. If "[2019] eKLR" is not `not_in_collection`, the invented names occur in a 2019 title: print `filing.rank_eklr(idx, 2019, "Tunutu Karamoja Traders v Olkaria Mbeere Holdings", None)[:3]`, then change the invented names in `hallucinated.txt` to words that print an empty list, and re-run.

- [ ] **Step 5: Endpoint check.** Start `uv run uvicorn api.main:app --port 8766` in the background; POST `web/public/demo/hallucinated.txt` as in slice 1 and confirm the `[2006] eKLR` finding has `"match_basis": "quote"`. Stop the server. Run `uv run python -m api.test_status` → `13/13 passed`.

- [ ] **Step 6: Commit.** `git add api/filing.py api/main.py api/test_filing.py web/public/demo && git commit -m "Filing checker: eKLR citations in the report, possible matches, quotes settle ties"`

---

### Task 4: Web: possible matches, match basis, empty-report copy

**Files:** Modify `web/lib/api.ts`, `web/app/check/Checker.tsx`

**Interfaces:** Consumes the `CaseCheck` fields from Task 3.

- [ ] **Step 1: Types.** In `web/lib/api.ts`, `CaseCheck` becomes:

```ts
export interface CaseCheck {
  result: 'found' | 'name_mismatch' | 'possible_match' | 'not_in_collection'
  form: 'neutral' | 'eklr'
  match_basis: 'neutral citation' | 'case number' | 'party names and year' | 'quote' | null
  cited_name: string | null
  judgment: JudgmentRef | null
  candidates: JudgmentRef[]
}
```

- [ ] **Step 2: UI.** In `Checker.tsx`'s `CaseLine`, before the `name_mismatch` branch, add the possible-match branch, and give `found` a basis line. Creative latitude applies; the required content:

```tsx
  if (c.result === 'possible_match')
    return (
      <div className="mt-2">
        <p className="text-seal">Possibly one of these cases in our collection. The citation gives only a year, and the names fit more than one:</p>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {c.candidates.map((k, n) => (
            <li key={k.judgment_id} style={{ ['--i' as string]: n }} className="candidate-card rounded-sm bg-paper px-3 py-2 ring-1 ring-rule">
              {k.source_url ? (
                <a href={k.source_url} className="link" target="_blank" rel="noreferrer">
                  {shortCase(k.title)}
                </a>
              ) : (
                shortCase(k.title)
              )}
              <span className="block text-sm text-ink-2">
                {k.court}, {fmtDate(k.decision_date)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    )
```

and for `found`, after the title sentence, when `c.match_basis && c.match_basis !== 'neutral citation'`: a small line `Matched on {BASIS[c.match_basis]}` with `BASIS = { 'case number': 'the case number', 'party names and year': 'the parties’ names and the year', quote: 'the quoted words, found only in this judgment' }`. Import `fmtDate` from `@/lib/format`. Add to `globals.css` a `.candidate-card` entrance (fade and lift in, delay `calc(0.2s + var(--i) * 0.08s)`), switched off under reduced motion. Empty-report copy becomes: "Hakiki reads neutral citations such as [2017] KESC 2 (KLR), eKLR citations such as [2017] eKLR, and sections of the Acts it holds. An empty report is not a sign the filing is sound."

- [ ] **Step 3: Check.** From the repo root, with `N=/Users/leo/.nvm/versions/node/v22.23.2/bin`:
`(cd web && $N/node $N/../lib/node_modules/npm/bin/npx-cli.js eslint app/check lib && $N/node node_modules/typescript/bin/tsc --noEmit -p . && $N/node --no-warnings lib/text.check.ts)`
Expected: exit 0 and `text checks passed`.

- [ ] **Step 4: Look.** Screenshot Exhibit B with the headless-Chrome script used for the redesign (scratchpad `shot.mjs`, API on :8766, dev on :3001) in light and dark; the `[2006] eKLR` note must say it was matched on the quote, and `[2019] eKLR` must read "Not in our collection". Then temporarily paste a two-candidate filing (the "no settling quote" text from Task 3) to see the candidate cards.

- [ ] **Step 5: Commit.** `git add web/lib/api.ts web/app/check/Checker.tsx web/app/globals.css && git commit -m "Web: eKLR matches, possible-match cards, match basis"`

---

### Task 5: Benchmark sample and the labeller

**Files:** Create `ground_truth/filing_sample.py`, `.claude/agents/citation-labeler.md`

**Interfaces:**
- Produces: `ground_truth/filing_{dev,test}_items.csv` (`item_id, judgment_id, char_start, raw_text, year, context`), `$LEXHACK_DATA/review/filing/titles_<year>.tsv` (`judgment_id, decision_date, case_number, title, text_path`), `$LEXHACK_DATA/review/filing/batches/<set>_<k>.json` (≤ 50 items: `item_id, citing_judgment_text, context, year, titles_file`).

- [ ] **Step 1: Write the sampler.**

```python
"""Filing benchmark sample (spec 2a): judgments with 2+ eKLR citations, split into dev and test; every eKLR citation in
them is an item. Also writes each needed year's list of titles and the labelling batches.

  uv run python -m ground_truth.filing_sample
"""
import csv
import json
import random
import re
from pathlib import Path

from api.filing import find_eklr
from crawler.config import data_dir
from pipeline.db import connect

HERE = Path(__file__).resolve().parent
SEED, PER_SET, BATCH = 2026, 40, 50
DEMO = {"ke/judgment/kehc/2017/8382", "ke/judgment/kesc/2017/2", "ke/judgment/kesc/2021/31",
        "ke/judgment/kehc/2006/2628", "ke/judgment/kehc/2006/2629"}


def earlier_benchmarks():
    return {r["judgment_id"] for f in ("mentions_gold.csv", "mentions_heldout_gold.csv")
            for r in csv.DictReader(open(HERE / f, encoding="utf-8"))}


def main():
    skip = DEMO | earlier_benchmarks()
    with connect() as conn:
        rows = conn.execute("""SELECT judgment_id, raw_path FROM judgments
                               WHERE duplicate_of IS NULL AND has_full_text ORDER BY judgment_id""").fetchall()
        titles = conn.execute("""SELECT judgment_id, decision_date::text, coalesce(case_number, ''), title, raw_path,
                                        extract(year FROM decision_date)::int
                                 FROM judgments WHERE duplicate_of IS NULL ORDER BY title""").fetchall()
    pool = []
    for jid, raw_path in rows:
        if jid in skip:
            continue
        text = json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or ""
        cites = find_eklr(text)
        if len(cites) >= 2:
            pool.append((jid, raw_path, text, cites))
    random.Random(SEED).shuffle(pool)
    out = data_dir() / "review" / "filing"
    (out / "batches").mkdir(parents=True, exist_ok=True)
    years = set()
    for name, part in (("dev", pool[:PER_SET]), ("test", pool[PER_SET:2 * PER_SET])):
        items = []
        for jid, raw_path, text, cites in part:
            for c in cites:
                items.append({"item_id": f"{name}-{len(items) + 1:04d}", "judgment_id": jid,
                              "char_start": c["char_start"], "raw_text": c["raw_text"], "year": c["year"],
                              "context": re.sub(r"\s+", " ", text[max(0, c["char_start"] - 300):c["char_end"] + 60]),
                              "citing_judgment_text": str(data_dir() / raw_path)})
                years.add(c["year"])
        with open(HERE / f"filing_{name}_items.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["item_id", "judgment_id", "char_start", "raw_text", "year", "context"])
            w.writeheader()
            w.writerows({k: it[k] for k in w.fieldnames} for it in items)
        for k in range(0, len(items), BATCH):
            batch = [{**{x: it[x] for x in ("item_id", "context", "year", "citing_judgment_text")},
                      "titles_file": str(out / f"titles_{it['year']}.tsv")} for it in items[k:k + BATCH]]
            (out / "batches" / f"{name}_{k // BATCH + 1}.json").write_text(json.dumps(batch, indent=1), encoding="utf-8")
        print(name, len(part), "judgments", len(items), "items")
    for y in sorted(years):
        with open(out / f"titles_{y}.tsv", "w", encoding="utf-8") as f:
            f.write("judgment_id\tdecision_date\tcase_number\ttitle\ttext_path\n")
            for jid, d, cn, t, rp, ty in titles:
                if ty == y:
                    f.write(f"{jid}\t{d}\t{cn}\t{t}\t{data_dir() / rp}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it.** `uv run python -m ground_truth.filing_sample` → Expected: two lines like `dev 40 judgments ~200 items` / `test 40 judgments ~200 items`; `ls $LEXHACK_DATA/review/filing/batches` lists `dev_1.json …`.

- [ ] **Step 3: The labeller agent type.** Create `.claude/agents/citation-labeler.md`:

```markdown
---
name: citation-labeler
description: Labels which judgment an eKLR citation in a Kenyan judgment refers to, for Hakiki's filing benchmark (ground_truth/filing_*). Use for $LEXHACK_DATA/review/filing/batches.
tools: Read, Grep, Write
---

You label citations for Hakiki's benchmark. Each item is a citation like "Jacqueline Okuta & another v Attorney
General & 2 others [2017] eKLR" found in a Kenyan judgment. Decide which judgment in our collection it refers to, or
that we don't hold it.

For each item in the batch file you are given:
1. Read `context` (the words around the citation). If the case name is cut off, Read `citing_judgment_text` and Grep
   for the citation to see more.
2. Grep `titles_file` (that year's judgments we hold: judgment_id, date, case number, title, text path) for the
   parties' distinctive names. Titles often drop first names ("Muruatetu & another v Republic") and may abbreviate.
3. If several titles could fit, open their `text_path` files and compare parties, court, case number and subject with
   the context. A citation's year is the year the judgment was delivered.
4. Answer the judgment_id only if you are confident it is the same case (same parties and matter). If none fits, answer
   `not_held`. If two fit and nothing distinguishes them, answer `unsure` and name both in the reason.

Output: a JSON array of {"item_id", "label" (a judgment_id, "not_held" or "unsure"), "reason" (one line)}. If the
output file exists, read it and skip items already in it. After EACH item, rewrite the whole file (valid JSON, UTF-8).

Never open anything under /Users/leo/Developer/Lexhack/ground_truth/, other labellers' files, or api/filing.py
results. Never modify any other file. When done, reply with one line: the count of items labelled.
```

- [ ] **Step 4: Commit.** `git add ground_truth/filing_sample.py ground_truth/filing_dev_items.csv ground_truth/filing_test_items.csv .claude/agents/citation-labeler.md && git commit -m "Filing benchmark: dev/test sample and the citation-labeler agent"`

---

### Task 6: Labelling runs and the merge

**Files:** Create `ground_truth/filing_merge.py`; outputs `ground_truth/filing_{dev,test}_labels_{A,B,C}.csv`, `ground_truth/filing_{dev,test}_gold.csv`

**Interfaces:**
- Consumes: batches (Task 5); agent outputs `$LEXHACK_DATA/review/filing/labels/<set>_<labeller>_<k>.json`.
- Produces: gold CSV `item_id, gold, agreed` (`gold` = judgment_id or `not_held`; `agreed` = A and B agreed).

- [ ] **Step 1: Write the merge and its failing check.** `ground_truth/filing_merge.py`:

```python
"""Merge the labellers' answers (spec 2a): A and B label blind; where they differ (or either is 'unsure'), C decides.

  uv run python -m ground_truth.filing_merge dev            # writes labels_{A,B}.csv, lists items C must label
  uv run python -m ground_truth.filing_merge dev --final    # after C: writes filing_dev_gold.csv
"""
import csv
import json
import sys
from pathlib import Path

from crawler.config import data_dir

HERE = Path(__file__).resolve().parent


def load(name, who):
    out = {}
    for f in sorted((data_dir() / "review" / "filing" / "labels").glob(f"{name}_{who}_*.json")):
        for a in json.loads(f.read_text(encoding="utf-8")):
            out[a["item_id"]] = a["label"].strip()
    return out


def merge(items, a, b, c):
    """-> (gold rows, items C must label, items missing from A or B). Pure, for the check in __main__."""
    missing = [i for i in items if i not in a or i not in b]
    need_c = [i for i in items if i not in missing and (a[i] != b[i] or "unsure" in (a[i], b[i]))]
    gold = [{"item_id": i, "gold": a[i] if i not in need_c else c.get(i, ""), "agreed": i not in need_c}
            for i in items if i not in missing]
    return gold, need_c, missing


def main():
    name, final = sys.argv[1], "--final" in sys.argv
    items = [r["item_id"] for r in csv.DictReader(open(HERE / f"filing_{name}_items.csv", encoding="utf-8"))]
    a, b, c = load(name, "A"), load(name, "B"), load(name, "C")
    gold, need_c, missing = merge(items, a, b, c)
    if missing:
        raise SystemExit(f"{len(missing)} items unlabelled by A or B, e.g. {missing[:5]}; re-run those batches")
    for who, labels in (("A", a), ("B", b), ("C", c)):
        with open(HERE / f"filing_{name}_labels_{who}.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([("item_id", "label")] + sorted(labels.items()))
    print(f"A/B agreement {len(items) - len(need_c)}/{len(items)}; C must label {len(need_c)}")
    (data_dir() / "review" / "filing" / f"{name}_need_c.json").write_text(json.dumps(need_c), encoding="utf-8")
    if final:
        if any(not g["gold"] or g["gold"] == "unsure" for g in gold):
            raise SystemExit("C has not labelled every disagreement (or answered unsure): finish C first")
        with open(HERE / f"filing_{name}_gold.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["item_id", "gold", "agreed"])
            w.writeheader()
            w.writerows(gold)
        print("wrote", f"filing_{name}_gold.csv")


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        g, need, miss = merge(["1", "2", "3"], {"1": "x", "2": "x"}, {"1": "x", "2": "y"}, {"2": "y"})
        assert (need, miss, g[1]["gold"]) == (["2"], ["3"], "y"), (need, miss, g)
        print("merge check passed")
    else:
        main()
```

Run: `uv run python -m ground_truth.filing_merge --check` → Expected: `merge check passed`. (This pins Review Focus 5: a missing item is reported, never silently dropped.)

- [ ] **Step 2: Label with A and B.** For each batch file `<set>_<k>.json`, dispatch two agents of type `citation-labeler` (A on model sonnet, B on model sonnet, separate spawns, neither sees the other), prompt: "Batch: `$LEXHACK_DATA/review/filing/batches/<set>_<k>.json`. Output: `$LEXHACK_DATA/review/filing/labels/<set>_<A|B>_<k>.json`." Run up to 8 at a time in the background. When all return, run `uv run python -m ground_truth.filing_merge dev` and `… test`. Expected: agreement lines, and no "unlabelled" error (if there is one, re-dispatch the named batches: the agent resumes from its file).

- [ ] **Step 3: Label disagreements with C.** For each set, write the items listed in `<set>_need_c.json` into `batches/<set>_C.json` (same item objects as the batches), dispatch one `citation-labeler` on model opus with output `labels/<set>_C_1.json`. Then `uv run python -m ground_truth.filing_merge dev --final` and `… test --final` → Expected: `wrote filing_dev_gold.csv` / `filing_test_gold.csv`.

- [ ] **Step 4: Commit.** `git add ground_truth/filing_merge.py ground_truth/filing_*_labels_*.csv ground_truth/filing_*_gold.csv && git commit -m "Filing benchmark: blind agent labels and gold for dev and test"`

---

### Task 7: `eval_filing.py`: metrics, tuning on dev, the test score

**Files:** Create `ground_truth/eval_filing.py`; Modify `api/filing.py` (tuned constants)

**Interfaces:**
- Consumes: items + gold CSVs; `filing.title_index`, `rank_eklr`, `decide`, `check`.
- Produces: `uv run python -m ground_truth.eval_filing --set dev|test` (metrics), `--tune` (grid search on dev).

- [ ] **Step 1: Write it.**

```python
"""Score eKLR matching against the agents' gold (spec 2a).

  uv run python -m ground_truth.eval_filing --set dev      # metrics with the current thresholds
  uv run python -m ground_truth.eval_filing --tune         # grid search on dev only
  uv run python -m ground_truth.eval_filing --set test     # once, after tuning: the number to quote
"""
import argparse
import csv
import itertools
import json
from pathlib import Path

from api import filing
from crawler.config import data_dir
from pipeline.db import connect

HERE = Path(__file__).resolve().parent


def load(name):
    items = {r["item_id"]: r for r in csv.DictReader(open(HERE / f"filing_{name}_items.csv", encoding="utf-8"))}
    gold = {r["item_id"]: r["gold"] for r in csv.DictReader(open(HERE / f"filing_{name}_gold.csv", encoding="utf-8"))}
    return items, gold


def answers(conn, items):
    """{item_id: (result, [judgment ids])} from the full checker run on each citing judgment (quote tie-break
    included), matched to items by character offset."""
    raw = dict(conn.execute("SELECT judgment_id, raw_path FROM judgments").fetchall())
    out, by_judgment = {}, {}
    for it in items.values():
        by_judgment.setdefault(it["judgment_id"], []).append(it)
    for jid, its in by_judgment.items():
        text = json.loads((data_dir() / raw[jid]).read_text(encoding="utf-8"))["text"] or ""
        found = {f["char_start"]: f["case"] for f in filing.case_findings(conn, text) if f["case"]["form"] == "eklr"}
        for it in its:
            c = found[int(it["char_start"])]
            ids = [c["judgment"]["judgment_id"]] if c["judgment"] else [k["judgment_id"] for k in c["candidates"]]
            out[it["item_id"]] = (c["result"], ids)
    return out


def metrics(ans, gold):
    n = len(gold)
    held = [i for i, g in gold.items() if g != "not_held"]
    found = [i for i, (r, _) in ans.items() if r == "found" and i in gold]
    right = [i for i in found if ans[i][1][0] == gold[i]]
    return {
        "items": n, "gold held": len(held),
        "found precision": f"{len(right)}/{len(found)}",
        "wrong-case rate": f"{len(found) - len(right)}/{n}",
        "coverage": f"{sum(1 for i in held if i in right)}/{len(held)}",
        "possible-match hit": f"{sum(1 for i in held if ans[i][0] == 'possible_match' and gold[i] in ans[i][1])}"
                              f"/{sum(1 for i in held if ans[i][0] == 'possible_match')}",
        "false found on not-held": f"{sum(1 for i in found if gold[i] == 'not_held')}"
                                   f"/{sum(1 for g in gold.values() if g == 'not_held')}",
    }


def tune(conn, items, gold):
    """Grid over the thresholds on dev, matcher only (no quote tie-break). Objective: fewest wrong cases, then most
    coverage."""
    idx = filing.title_index(conn)
    ctx = {}
    for it in items.values():
        text = it["context"]   # starts 300 characters before the citation (fewer near the start of a judgment)
        e = min(filing.find_eklr(text), key=lambda c: abs(c["char_start"] - min(300, int(it["char_start"]))))
        ctx[it["item_id"]] = (int(it["year"]), e["cited_name"], e["case_number"])
    best = None
    for ms in (2.0, 3.0, 4.0, 5.0, 6.0):
        ranked = {i: filing.rank_eklr(idx, *ctx[i], min_shared=ms) for i in gold}
        for fs, mg, ps in itertools.product((0.6, 0.7, 0.8, 0.9), (0.1, 0.2, 0.3, 0.4), (0.3, 0.4, 0.5, 0.6)):
            d = {i: filing.decide(r, fs, mg, ps) for i, r in ranked.items()}
            wrong = sum(1 for i, x in d.items() if x["result"] == "found" and x["rows"][0][1] != gold[i])
            cover = sum(1 for i, x in d.items() if x["result"] == "found" and x["rows"][0][1] == gold[i])
            key = (wrong, -cover)
            if best is None or key < best[0]:
                best = (key, dict(MIN_SHARED=ms, FOUND_SCORE=fs, FOUND_MARGIN=mg, POSSIBLE_SCORE=ps))
    print("best on dev (wrong, -coverage):", best[0], best[1])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", default="dev")
    p.add_argument("--tune", action="store_true")
    a = p.parse_args()
    items, gold = load("dev" if a.tune else a.set)
    with connect() as conn:
        if a.tune:
            tune(conn, items, gold)
        else:
            for k, v in metrics(answers(conn, items), gold).items():
                print(f"{k:>24}: {v}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dev metrics with starting thresholds.** `uv run python -m ground_truth.eval_filing --set dev` → prints the six metrics. Record them in the ledger.

- [ ] **Step 3: Tune on dev.** `uv run python -m ground_truth.eval_filing --tune` → prints the best thresholds. If the best has more than 1% wrong cases, look at the wrong items (print them) before accepting: a wrong gold label is reported as such, not tuned around. Set the four constants in `api/filing.py` to the printed values, with a comment `# tuned on the dev set, 2026-09-28 (eval_filing --tune)`. Re-run `--set dev` and `uv run python -m api.test_filing` (the fake-index tests pass their own `min_shared`; if a threshold change breaks a real-data demo expectation, report it as a finding rather than editing the expectation).

- [ ] **Step 4: Score test once.** `uv run python -m ground_truth.eval_filing --set test` → these are the numbers to quote. Save the output to `ground_truth/filing_test_results.txt`.

- [ ] **Step 5: Commit.** `git add ground_truth/eval_filing.py ground_truth/filing_test_results.txt api/filing.py && git commit -m "Filing benchmark: metrics, thresholds tuned on dev, test scored"`

---

### Task 8: Planted errors and false alarms

**Files:** Modify `ground_truth/eval_filing.py`

**Interfaces:** Adds `--planted`.

- [ ] **Step 1: Write it.** Add `import random` and `import re` to `eval_filing.py`'s imports, then add:

```python
MUTATIONS = ("drop a word", "swap a word", "insert not")


def mutate(words, how, rng, pool):
    w = list(words)
    k = rng.randrange(2, len(w) - 2)
    if how == "drop a word":
        del w[k]
    elif how == "swap a word":
        w[k] = rng.choice([p for p in pool if p.lower() != w[k].lower()])
    else:
        w.insert(k, "not")
    return w


def planted(conn):
    """Errors with known answers, planted in text built around real citations (no labels needed), then the
    false-alarm rate on real, unmodified neutral citations in the benchmark judgments."""
    rng, tally = random.Random(2026), {}
    rows = conn.execute("""SELECT neutral_citation, judgment_id, title, raw_path, extract(year FROM decision_date)::int
                           FROM judgments WHERE duplicate_of IS NULL AND has_full_text AND neutral_citation IS NOT NULL
                           ORDER BY judgment_id""").fetchall()
    sample = rng.sample(rows, 150)

    def count(kind, hit):
        tally.setdefault(kind, [0, 0])
        tally[kind][0] += bool(hit)
        tally[kind][1] += 1

    def case_of(text):
        return filing.check(conn, text)["findings"][0]

    for nc, jid, title, rp, y in sample[:50]:
        mine = filing.name_tokens(filing.party_part(title))
        other = rng.choice([r for r in rows if r[4] == y and not filing.name_tokens(filing.party_part(r[2])) & mine])
        count("wrong name -> name_mismatch",
              case_of(f"In {filing.party_part(other[2])} {nc}, the court held so.")["case"]["result"] == "name_mismatch")
        count("control: right name -> found",
              case_of(f"In {filing.party_part(title)} {nc}, the court held so.")["case"]["result"] == "found")
    for nc, jid, title, rp, y in sample[50:120]:
        text = json.loads((data_dir() / rp).read_text(encoding="utf-8"))["text"] or ""
        sents = [s.split() for s in re.split(r"(?<=[.;])\s+", text) if 14 <= len(s.split()) <= 30]
        if not sents:
            continue
        words, how = rng.choice(sents), rng.choice(MUTATIONS)
        pool = [w for s in sents for w in s if w.isalpha() and len(w) > 3]
        q = " ".join(mutate(words, how, rng, pool)).replace('"', "'")
        f = case_of(f"In {filing.party_part(title)} {nc}, it was held that \"{q}\".")
        count(f"altered quote ({how}) -> close or not_found",
              f["quotes"] and f["quotes"][0]["result"] in ("close", "not_found"))
    for nc, jid, title, rp, y in sample[120:150]:
        court = re.search(r"\] (\w+) ", nc)[1]
        top = max(int(r[0].split()[2]) for r in rows if r[4] == y and f"] {court} " in r[0])
        count("invented number -> not_in_collection",
              case_of(f"In Doe v Roe [{y}] {court} {top + 10000} (KLR), so held.")["case"]["result"] == "not_in_collection")
    for k, (hit, n) in tally.items():
        print(f"{k:>48}: {hit}/{n}")

    items = {**load("dev")[0], **load("test")[0]}
    raw = dict(conn.execute("SELECT judgment_id, raw_path FROM judgments").fetchall())
    flagged, total = [], 0
    for jid in sorted({it["judgment_id"] for it in items.values()}):
        text = json.loads((data_dir() / raw[jid]).read_text(encoding="utf-8"))["text"] or ""
        for f in filing.case_findings(conn, text):
            c = f["case"]
            if c["form"] == "neutral" and c["result"] in ("found", "name_mismatch"):
                total += 1
                if c["result"] == "name_mismatch":
                    flagged.append({"judgment_id": jid, "citation": f["raw_text"], "cited_name": c["cited_name"],
                                    "our_title": c["judgment"]["title"],
                                    "context": re.sub(r"\s+", " ", text[max(0, f["char_start"] - 250):f["char_end"] + 40])})
    print(f"{'real neutral citations flagged name_mismatch':>48}: {len(flagged)}/{total}")
    (data_dir() / "review" / "filing" / "false_alarms.json").write_text(json.dumps(flagged, indent=1), encoding="utf-8")
```

In `main()`: add `p.add_argument("--planted", action="store_true")`, and inside the `with connect()` block handle `if a.planted: planted(conn)` first (it needs no `--set`; load items only when not planted: move `items, gold = load(...)` into the non-planted branches).

- [ ] **Step 2: Run it.** `uv run python -m ground_truth.eval_filing --planted` → prints catch rates for wrong name, control, each quote mutation, invented number, and the false-alarm count. Save to `ground_truth/filing_planted_results.txt`.

- [ ] **Step 3: Check the false alarms.** If any are flagged, dispatch one `general-purpose` agent (model sonnet): "Read `$LEXHACK_DATA/review/filing/false_alarms.json`. For each entry decide whether the filing's case name and our title are the same case (an abbreviation or naming difference: a false alarm) or genuinely different cases (a real citation error in the judgment). Write `$LEXHACK_DATA/review/filing/false_alarms_verdicts.json` as [{citation, judgment_id, verdict: false_alarm|real_error, reason}]." Append the split to `filing_planted_results.txt`.

- [ ] **Step 4: Commit.** `git add ground_truth/eval_filing.py ground_truth/filing_planted_results.txt && git commit -m "Filing benchmark: planted errors and false alarms"`

---

### Task 9: Docs, About page, deploy

**Files:** Modify `README.md`, `CLAUDE.md`, `web/app/about/page.tsx`

- [ ] **Step 1: README.** In §7c's "Filing checker" subsection: eKLR matching (score, thresholds and their tuned values, quote tie-break, `possible_match`), the benchmark (sets, labelling, agreement), and the test and planted numbers copied from `filing_test_results.txt` / `filing_planted_results.txt`; how to re-run each script. Slice 2 list: 2a done; 2b, 2c next.

- [ ] **Step 2: About page.** Read `web/app/about/page.tsx`; add a short "How good is the filing checker?" part in its existing style with the test-set numbers (found precision, wrong-case rate, coverage) and planted catch rates, labelled "measured on our collection, labelled by AI reviewers".

- [ ] **Step 3: CLAUDE.md.** Item 9 (filing checker) gains 2a with the headline numbers; "Next" item 1 becomes 2b (upload), then 2c.

- [ ] **Step 4: Verify and commit.** `uv run python -m api.test_filing && uv run python -m api.test_status`; web lint/tsc (absolute paths); stop `next dev`, run `next build`, restart dev clean. `git add README.md CLAUDE.md web/app/about/page.tsx && git commit -m "Docs: filing checker 2a results"`

- [ ] **Step 5: Deploy.** Tell Leo to push (Vercel rebuilds the web). Deploy the API: `railway up --service api --ci` from the repo root; then POST `web/public/demo/hallucinated.txt` to `https://api-production-0506.up.railway.app/api/check` and confirm the `[2006] eKLR` finding has `match_basis: "quote"` (proves the live title index and R2 texts work).
