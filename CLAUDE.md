# Project brief: Kenyan statute citator (LexHack 2026)

Read this before doing any work in this repo. It explains what we're building, why, what's decided, and where things stand.

## What we're building, in one paragraph

A tool that tells you whether a section of a Kenyan law is **still good law**: in force, amended, repealed, or limited or struck down by a court. It does this by linking court judgments to the specific statute sections they affected. On top of that sits a **filing checker**: give it a legal document and it flags citations that are fake, misquoted, or rely on a section a court has struck down.

Think of it as a citator (like Shepard's or KeyCite in the US) for Kenya, which does not currently exist.

## Why it matters (this is the pitch)

Kenya Law publishes the official consolidated statutes. Our pilot found that **its consolidated text does not record court decisions that struck down sections.** Examples:

- **Penal Code s.204** still reads "Any person convicted of murder shall be sentenced to death" in the 2022 and 2023 versions, years after the Supreme Court in *Muruatetu* (2017) held the mandatory death sentence unconstitutional.
- **Penal Code s.194** (criminal defamation) carries no note of *Okuta* (2017).
- Of 1,038 editorial remarks across the statute pages we fetched, **not one mentions a court decision.** They are all amendment history.

So anyone (a lawyer, a student, or an AI tool) reading the official text gets it wrong. Our tool fixes that.

**To verify before the presentation:** that the live Kenya Law pages still lack these notes. Our evidence is from Internet Archive snapshots.

## The core design principle: never a simple yes/no

Courts often strike down a section only **partly**, "to the extent that" it does something. Examples:

- *Okuta*: s.194 is unconstitutional "to the extent that it covers offences other than those contemplated under Article 33(2)(a)-(d)". The rest survives.
- *Muruatetu*: s.204 is not dead. Only the *mandatory* nature of the death sentence is unconstitutional.

A section can also have a **history**: struck down, then reversed on appeal. So:

- Never output a red/green flag.
- Always output the status **plus the court's own words**, quoted verbatim, with the source.
- Store every event separately and derive status from the sequence of events.

Example output:

> **Penal Code s.204**: limited by the Supreme Court in *Francis Karioko Muruatetu & another v Republic* [2017] eKLR. Unconstitutional to the extent it makes the death sentence mandatory for murder. Otherwise in force. [link to judgment, paragraph]

**The tool reports what sources say. It never gives legal advice.**

## Hackathon context

- LexHack 2026: virtual student hackathon, AI × Law × Civic Tech. Judged on real-world impact, practical usability and innovation.
- Team of two. Leo owns the statutes, the provision database, retrieval and status logic. His teammate owns document handling: judgment parsing, citation extraction from filings, and the evidence trail.
- Relevant tracks: AI Safety & Governance (catching hallucinated legal citations) and Legal Automation.

## Data: what we use and the rules

**Data access (updated 2026-09-23):** legal advice to the team is that the data may be used as public domain, non-commercial. The Kenya Law terms page that prohibits scraping is out of date. Bulk pulls from the Internet Archive are fine; `crawler/scope.wayback-judgments.yaml` pulls every archived Supreme Court, Court of Appeal and High Court judgment. Technical note: new.kenyalaw.org returns a 403 to bot User-Agents, and its robots.txt blocks AI crawlers (ClaudeBot and others) by name, so Claude won't crawl it directly.

| Data | Source | Status |
|---|---|---|
| Statutes | Internet Archive snapshots | Done: 8 Acts, 31 versions (table in README §4.5). Focus: Penal Code (3/3 versions), Sexual Offences Act (9/9), KICA (2/13). For citation linking: Constitution, Civil Procedure Act, Evidence Act, Criminal Procedure Code. Gaps filled by saving pages by hand |
| Judgments | Internet Archive bulk pull (kesc, keca, kehc) + 1 saved by hand | Done: 16,419 distinct judgments (286 PDF-only, no text). Metadata in Postgres; full text on disk |
| Ground truth | `ground_truth/events.csv` (19 events) + `negatives.csv` (6 mention-only) | Done: drafted by Claude, audited blind, verified by agents + Leo (E11 = read_down): 19/19. Loaded into `citation_events`. Decisions in `ground_truth/decisions.md`. Check: `uv run python -m ground_truth.check` |
| Demo filings | Written by us, clearly labelled as synthetic | Not started |

Details of the Internet Archive pilot are in `crawler/REPORT.md`.

**Focus Acts:** Penal Code (Cap. 63), Sexual Offences Act (Cap. 63A), Kenya Information and Communications Act (Cap. 411A, s.29).

## What the pilot found (facts to build on)

- Statutes carry **stable section IDs (eIds) that don't change between versions**. Exception: the Employment Act's IDs changed at its 2022-12-31 revision (`sec_45` → `part_VI__sec_45`); the focus Acts are stable. Examples:
  - KICA s.29 → `part_III__sec_29`
  - Penal Code s.194 → `part_II__chp_XVIII__sec_194`
  - Penal Code s.204 → `part_II__chp_XVIII__subpart_nn_1__sec_204`
- Versions appear in URLs as `eng@YYYY-MM-DD`. Penal Code: 3 versions (all fetched). KICA: 13 listed (2 archived). Employment Act: 13 listed (11 archived).
- 71 of 73 judgments have full HTML text. OCR is a minor concern.
- Judgment metadata always has citation, court, case number and date. Judges are present ~70% of the time. **No fields** for parties, legislation cited or cases cited.
- **Links from judgments to legislation are unreliable**: whole-Act only, never section-level, and often missing (*Muruatetu* doesn't link the Penal Code at all). **Citations must be extracted from the judgment text.**
- Internet Archive holds only ~10% of judgments. It's a sample, not a mirror.

### The three anchor judgments (operative orders confirmed verbatim in `crawler/REPORT.md`)

| Case | Section | What the court did |
|---|---|---|
| *Geoffrey Andare v AG & 2 others* [2016] eKLR, HC Petition 149 of 2015 | KICA s.29 | Declared unconstitutional (whole section) |
| *Jacqueline Okuta & another v AG & 2 others* [2017] eKLR, HC Petition 397 of 2016 | Penal Code s.194 | Declared unconstitutional, partial ("to the extent that…") |
| *Francis Karioko Muruatetu & another v Republic* [2017] eKLR, SC Petitions 15 & 16 of 2015 | Penal Code s.204 | Mandatory nature of death sentence declared unconstitutional (partial) |

### Leads, now checked (2026-09-23, from the judgment texts)

- **Muruatetu 2021 directions exist:** [2021] KESC 31, 6 July 2021. Para 18(i): Muruatetu "appl[ies] only in respect to sentences of murder under sections 203 and 204 of the Penal Code". So s.204 has a multi-event history.
- **Sexual Offences Act s.8 is "read down, then reversed", not "struck down, then revived":**
  - The Court of Appeal read s.8 as not binding the court's discretion: *Kilwake* [2019] KECA 5 and *Mwangi* [2022] KECA 1106. In *Manyeso* [2023] KECA 827 it went further, treating the life sentence as unconstitutional.
  - The Supreme Court reversed *Mwangi* ([2024] KESC 34) and *Manyeso* ([2025] KESC 16), and set aside *Ayako* ([2025] KESC 20).
  - *Mwangi* SC para 65 says the Court of Appeal "did not declare any particular provision of the Sexual Offences Act unconstitutional".

## Tech stack (decided)

- **Pipeline:** Python. `pymupdf` for PDFs, `warcio` for the archive, plain `re` + an LLM pass for citation extraction. Plain scripts, no orchestration framework.
- **Database:** Postgres with `pgvector` on **Neon** (project `empty-firefly-79861883`, branch `production`, free plan ~0.5 GB). One database for everything; judgment full text stays on disk (`judgments.raw_path`).
- **Embeddings:** `gemini-embedding-2`, 1536 dims (key: `GEMINI_API_KEY` in `.env`). Free tier: 1,000 texts/day; `pipeline/embed.py` caches every vector and resumes.
- **Search:** hybrid, Postgres full-text search + pgvector, merged with reciprocal rank fusion.
- **API:** FastAPI.
- **Frontend:** Next.js.
- **Don't use** LangChain or LlamaIndex. Write retrieval directly.
- LLM calls: structured JSON output, cached to disk by input hash.

## Repo layout

```
~/lexhack/                 git repo (code only)
  CLAUDE.md                this file
  crawler/                 Internet Archive pilot code + REPORT.md
  pipeline/                parsing, extraction, loading
  api/                     FastAPI
  web/                     Next.js
  .env                     LEXHACK_DATA, etc. (gitignored)

$LEXHACK_DATA/             outside the repo, never committed
  raw/                     WARC files, frontier.db, WARC index, manual/ (hand-saved pages)
  parsed/                  normalised JSON per document
```

Always read paths from the `LEXHACK_DATA` environment variable. Never hardcode paths, never commit data.

## Schema

**The live schema is `pipeline/schema.sql`** (applied to Neon). It extends the draft below with `provision_texts.tsv`, and on `citation_events`: `event_key`, `subsection`, `verified_by`, `notes`, and CHECK constraints on `event_type` / `scope`. The draft is kept for reference.

Every ID includes the jurisdiction so the design can extend beyond Kenya later.

- `provision_id` format: `{jurisdiction}/act/{act-slug}/{eid}`, e.g. `ke/act/cap-63/part_II__chp_XVIII__sec_204`
- Status rules (how events combine into a status) live in a **per-jurisdiction module**, not in the core, because rules differ between countries.

```sql
CREATE TABLE acts (
  act_id        TEXT PRIMARY KEY,          -- e.g. 'ke/act/cap-63'
  jurisdiction  TEXT NOT NULL,             -- 'ke'
  title         TEXT NOT NULL,
  cap_number    TEXT,                      -- '63'
  frbr_uri      TEXT                       -- AKN URI from the page URL
);

CREATE TABLE act_versions (
  version_id    TEXT PRIMARY KEY,          -- act_id + '@' + date
  act_id        TEXT REFERENCES acts,
  version_date  DATE NOT NULL,
  source        TEXT NOT NULL,             -- 'wayback' | 'manual'
  source_url    TEXT,
  raw_path      TEXT                       -- relative to $LEXHACK_DATA
);

CREATE TABLE provisions (
  provision_id  TEXT PRIMARY KEY,          -- act_id + '/' + eid
  act_id        TEXT REFERENCES acts,
  eid           TEXT NOT NULL,             -- stable across versions
  number        TEXT,                      -- '204'
  heading       TEXT
);

CREATE TABLE provision_texts (             -- the text of a section in one version
  provision_id  TEXT REFERENCES provisions,
  version_id    TEXT REFERENCES act_versions,
  text          TEXT NOT NULL,
  embedding     VECTOR(1536),
  PRIMARY KEY (provision_id, version_id)
);

CREATE TABLE judgments (
  judgment_id       TEXT PRIMARY KEY,
  neutral_citation  TEXT,                  -- '[2017] eKLR'
  title             TEXT NOT NULL,
  court             TEXT,
  case_number       TEXT,
  decision_date     DATE,
  judges            TEXT[],
  has_full_text     BOOLEAN,
  source            TEXT NOT NULL,         -- 'wayback' | 'manual'
  source_url        TEXT,
  raw_path          TEXT
);

-- Every place a judgment mentions a statute section. Raw extraction output.
CREATE TABLE citation_mentions (
  mention_id    SERIAL PRIMARY KEY,
  judgment_id   TEXT REFERENCES judgments,
  provision_id  TEXT REFERENCES provisions,  -- NULL if not yet resolved
  raw_text      TEXT NOT NULL,               -- 'section 204 of the Penal Code'
  paragraph     TEXT,
  char_start    INT,
  char_end      INT,
  method        TEXT NOT NULL,               -- 'regex' | 'llm'
  confidence    REAL
);

-- What a court (or Parliament) actually DID to a section. This table is the project.
CREATE TABLE citation_events (
  event_id          SERIAL PRIMARY KEY,
  provision_id      TEXT REFERENCES provisions NOT NULL,
  judgment_id       TEXT REFERENCES judgments,   -- NULL for statutory events
  event_type        TEXT NOT NULL,
    -- 'declared_unconstitutional' | 'read_down' | 'severed' | 'upheld'
    -- | 'interpreted' | 'reversed_on_appeal' | 'repealed_by_statute'
    -- | 'amended_by_statute'
  scope             TEXT NOT NULL,               -- 'total' | 'partial'
  scope_text        TEXT,                        -- verbatim "to the extent that..." clause
  operative_quote   TEXT NOT NULL,               -- exact words of the order
  source_paragraph  TEXT,
  effective_date    DATE,
  affects_event_id  INT REFERENCES citation_events, -- e.g. an appeal reversing an earlier declaration
  method            TEXT NOT NULL,               -- 'manual' | 'extracted'
  verified          BOOLEAN DEFAULT FALSE,       -- human-checked
  confidence        REAL
);
```

**Ground truth** = rows in `citation_events` with `method = 'manual'` and `verified = true`. The extractor is measured against these.

## The filing checker (thin on purpose)

For each citation in an uploaded document, three checks only:

1. **Does the case exist?** Match against `judgments`.
2. **Does the quoted passage appear in it?** Text match against the judgment.
3. **Is the cited section still live?** Look up the provision's status from `citation_events`.

**Do not build** "does this case actually support the argument". It's an interesting research problem and a time sink. It goes in the pitch as a next step.

## Where we are and what's next

Full history and file-by-file explanation: `README.md`.

Done:
1. **Data:** 8 Acts (31 versions) and 16,419 judgments from the Internet Archive; *Mwaura* saved by hand. `crawler/`.
2. **Ground truth:** 19 events, all verified. `ground_truth/`.
3. **Database:** Neon Postgres. `pipeline/schema.sql`; `load_acts.py` (1,862 sections, 4,592 texts); `embed.py`.
4. **Judgments and answer key in the database:** `load_judgments.py` (16,419 rows, metadata only), `load_ground_truth.py` (19 events).
5. **Citation extraction, regex (done) + LLM (in progress)** → `citation_mentions` (README §7).
   - Regex: `pipeline/extract_citations.py`, 304,310 mentions in 13,098 judgments; every law recorded in `act_ref`, `provision_id` set for our 8 Acts (173,014). Tests: `pipeline.test_extract`.
   - LLM: `pipeline/llm_resolve.py` (`gemini-3.5-flash-lite`, cached in `$LEXHACK_DATA/cache/llm/`) resolves bare mentions. ~400 of 7,385 judgments done; the free tier allows ~500 requests/day. Re-run daily, or enable billing (~$5–8).
   - Scored on a verified 30-judgment sample (`ground_truth/mentions_README.md`; `uv run python -m ground_truth.eval_mentions --llm`): precision 99.5%, recall 98.5%, law right 99.3% / wrong 0%. Those regex scores are optimistic (tuned on that sample). **Held-out score, the one to quote:** 30 unseen judgments, double-labelled blind (469/471 agreement): precision 98.1%, recall 98.1%, law right 88.8% / wrong 0.5% / unresolved 10.7% (regex only). `eval_mentions --set heldout`.
   - **Order matters:** `extract_citations` rebuilds all mention rows (regex and LLM); always run `llm_resolve` after it.

Next:
- **Finish step 5:** the LLM pass (above). Embeddings are done (all 4,592).
6. **Event classification** → `citation_events` (`method='extracted'`); measure against the ground truth and `negatives.csv`. Also turn the Acts' amendment notes into `amended_by_statute` / `repealed_by_statute` events.
7. **Status resolver** (per-jurisdiction rules; `affects_event_id` = direct reversal only, precedent handled by rules), then API, then UI. The front end can start now against mock JSON; defining the API response shape comes first.
8. **Synthetic demo filings and the filing checker.**
9. **Deploy** end to end.

Known gaps: 286 PDF-only judgments have no text; Archive coverage is ~10% of judgments; the Employment Act's eIds changed in 2022; appeals of *EG*, *Alai* and *Andama* are unchecked. Before the presentation, confirm the live Kenya Law pages still lack court notes.

Blind spots to keep in mind (details in README §9):
- **One shared Neon branch:** both teammates write to `production`, and pipeline re-runs are destructive. Agree who runs them, or use Neon branches.
- **Caches are per machine:** `cache/llm/` and `cache/embeddings/` make re-runs free. Copy them between machines, or the API calls are made (and paid for) again.
- **Neon storage:** 215 MB of ~512 MB used.
- **Paragraph numbers:** fixed 2026-09-27 ("1.", "[1]", "1)" styles; 19/19 answer-key paragraphs right). To re-derive them without losing LLM rows: `extract_citations --paragraphs-only`. ~23% of mentions have none because the judgment is unnumbered.
- **Constitution:** "section N of the Constitution" is always treated as the repealed Constitution, so 2010 Schedule sections are misattributed.
- **`act_ref` for laws we don't hold is not normalised.**
- **Not extracted:** rules, orders and regulations.

## Windows setup notes

- **Set `PYTHONUTF8=1` on Windows** (`setx PYTHONUTF8 1`, then restart the terminal). The code calls `read_text()` / `open()` without an encoding, so Windows falls back to cp1252 and crashes with `UnicodeDecodeError` on judgment files (seen in `ground_truth.check`). We chose not to patch the code; the env var is the fix. Macs default to UTF-8 and are unaffected.
- `uv` is at `C:\Users\user\.local\bin`; restart the shell if `uv` isn't found.
- `LEXHACK_DATA` in `.env` uses forward slashes (`C:/Users/user/lexhack-data`). It is machine-specific; each teammate sets their own.

## Rules for working in this repo

- Get bulk data through the Internet Archive; save individual pages by hand when it's missing them.
- Quote courts verbatim. Never paraphrase an operative order into a status.
- Never output a binary valid/invalid status.
- Keep jurisdiction in every ID.
- Data lives under `$LEXHACK_DATA`, never in git.
- Parse from stored files; never re-fetch to re-parse.
- Mark anything unverified as unverified.
