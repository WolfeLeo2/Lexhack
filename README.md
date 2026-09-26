# LexHack: a citator for Kenyan statutes

LexHack tells you whether a section of a Kenyan law is **still good law**: in force, amended, repealed, or limited or struck down by a court. It links court judgments to the exact statute sections they affected, and it always answers with the **court's own words and a link to the source**, never a bare yes or no. A filing checker sits on top: give it a legal document, and it flags citations that are fake, misquoted, or that rely on a section a court has struck down.

This file explains the project from scratch: what has been built, how the data flows, and how to read every file. `CLAUDE.md` holds the design brief and the working rules.

| Phase | What it covers | Status |
|---|---|---|
| **1. Data acquisition** | Get the statutes and judgments onto disk, legally and reproducibly | Done for statutes. The bulk judgment pull is running |
| **2. Ground truth** | A hand-checked answer key of what courts did to which sections | Done: 19 events, all verified |
| 3. Database | Load Acts, versions and sections into Postgres (Neon) | Done: schema + 4 Acts loaded. Embeddings 950/1,289, rest after the free-tier daily quota resets |
| 4. Judgments | Load judgment metadata into Postgres | Done: 16,419 judgments (metadata; full text stays on disk) |
| 5–9 | Extract citations, classify events, status resolver, API/UI, filing checker, deploy | Not started |

---

## Contents

1. [Why this exists](#1-why-this-exists)
2. [Where things live](#2-where-things-live)
3. [Quick start](#3-quick-start)
4. [Phase 1: data acquisition](#4-phase-1-data-acquisition)
5. [Phase 2: ground truth](#5-phase-2-ground-truth)
6. [Glossary](#6-glossary)
7. [Open items and next steps](#7-open-items-and-next-steps)

---

## 1. Why this exists

Kenya Law publishes the official consolidated text of every Act. Our Phase 1 data shows that **this text does not record court decisions that struck sections down**. For example:

- **Penal Code s.204** still reads "Any person convicted of murder shall be sentenced to death" in the 2022 and 2023 versions. That is years after the Supreme Court in *Muruatetu* (2017) declared the *mandatory* death sentence unconstitutional.
- **Penal Code s.194** (criminal defamation) has no note of *Okuta* (2017), which struck it down in part.
- None of the **1,038 editorial remarks** on the statute pages we examined mentions a court. They are all amendment history.

So anyone reading the official text, whether a lawyer, a student or an AI tool, can be wrong about the law. The US has citators (Shepard's, KeyCite) for exactly this problem. Kenya has none.

**The design rule that follows:** courts often strike a section down only *partly* ("to the extent that…"), and a section can have a history (struck down, then reversed on appeal). So the tool never outputs green/red. It outputs the status **plus the court's exact words, the paragraph and a link**. It reports what the sources say and never gives legal advice.

---

## 2. Where things live

Code and data are kept apart. **Data is never committed to git.**

```
/Users/leo/Developer/Lexhack/        ← the git repo (code only)
  README.md                          ← this file
  CLAUDE.md                          ← design brief and working rules
  .env                               ← LEXHACK_DATA, CRAWLER_CONTACT (gitignored)
  crawler/                           ← Phase 1: fetch, store, parse
    crawl.py        CLI: run / add / status / requeue / retry
    fetcher.py      polite HTTP client: robots.txt, rate limit, backoff, hard stops
    frontier.py     the SQLite queue of URLs + index of stored records
    storage.py      writes and reads WARC files
    wayback.py      Internet Archive mode (CDX lookup, playback URLs)
    parse.py        WARC → one JSON file per document
    analyze.py      pilot structure analysis → parsed/analysis.md
    config.py       reads .env and scope files
    test_offline.py self-check, no network
    scope.*.yaml    what to crawl (one file per run type)
    REPORT.md       the full Phase 1 lab notebook
    README.md       crawler operating manual
  ground_truth/                      ← Phase 2: the answer key
    events.csv      18 verified events (the main output)
    negatives.csv   6 judgments that cite a section without affecting it
    check.py        verifies every quote against the stored judgments
    audit.md, audit_blind.csv, decisions.md   ← how the table was checked
  letters/
    kenyalaw_bulk_request.md   draft letter asking Kenya Law for bulk data

$LEXHACK_DATA  (= /Users/leo/lexhack-data, outside the repo)
  raw/
    frontier.db                      ← SQLite: the queue, the WARC index, Wayback captures
    kenyalaw-00000.warc.gz           ← everything fetched, byte for byte (single-worker runs)
    kenyalaw-s{i}of3-*.warc.gz       ← same, one file set per parallel worker
    wayback-*.log / *.out            ← crawl logs
  parsed/
    act/*.json                       ← one file per Act version
    judgment/*.json                  ← one file per judgment
    source/*.json                    ← text extracted from PDFs
    analysis.md                      ← pilot statistics
  external/hf_ipfs_kenya_laws/       ← a third-party dataset we evaluated
```

Code always reads the data location from the `LEXHACK_DATA` environment variable, never a hardcoded path.

---

## 3. Quick start

```sh
uv sync                                                       # install dependencies
uv run python -m crawler.crawl status                         # queue counts by kind and status
uv run python -m crawler.parse                                # WARC → parsed JSON (offline, re-runnable)
uv run python -m crawler.test_offline                         # crawler self-check
uv run python -m ground_truth.check                           # verify the answer key against sources
uv run python -m pipeline.load_acts                           # apply pipeline/schema.sql + load Acts into Neon
uv run python -m pipeline.embed                               # gemini-embedding-2 vectors for section texts
uv run python -m pipeline.load_judgments                      # judgment metadata into Neon (text stays on disk)

# the bulk judgment pull (3 parallel workers; re-running resumes where it stopped)
for i in 0 1 2; do nohup uv run python -m crawler.crawl run \
  --scope scope.wayback-judgments.yaml --shard $i/3 > $LEXHACK_DATA/raw/s$i.out 2>&1 & done
pkill -TERM -f "crawler.crawl run"                            # stop it (background jobs ignore Ctrl-C)
```

---

## 4. Phase 1: data acquisition

### 4.1 Aim

Build a local, reproducible copy of the Kenyan statutes and judgments we need, and learn how the source pages are structured. Four questions had to be answered before anything else:

- Do statute sections have stable IDs?
- Are past versions available?
- Do the statute pages record court decisions?
- Can judgments be parsed as text?

### 4.2 What happened, in order

1. **Direct crawl of Kenya Law attempted and stopped.** A polite crawler (declared identity, one connection, robots.txt first) was built for `new.kenyalaw.org`. Its first request came back **403 Forbidden**: the site filters out user-agents containing "Bot". A test with an honest non-"Bot" name got through for robots.txt and the terms page only. Those showed:
   - robots.txt asks for a 5-second crawl delay and blocks named AI crawlers, including ClaudeBot.
   - The terms page says scraping is prohibited and points bulk users to info@kenyalaw.org. The content licence is CC BY-NC 4.0.

   The team has since received legal advice that the data can be used as public domain for non-commercial purposes. The site still actively blocks crawlers, so **all bulk data comes from the Internet Archive instead**. The evidence is saved in `crawler/evidence_robots.txt` and `crawler/evidence_terms.txt`. `letters/kenyalaw_bulk_request.md` is a draft request for official bulk access.
2. **Other sources evaluated.**
   - **A Hugging Face dataset:** current versions only, and missing both the Penal Code and KICA.
   - **Laws.Africa's API:** legislation only; for judgments it returns summaries, not full text; and full access for one country starts at ZAR 42k/month.
   - **Pocket Law:** no Kenyan edition.
   - **Common Crawl:** almost no captures.

   None was enough. Details are in `crawler/REPORT.md` §8–9.
3. **Wayback pilot (Internet Archive).** The crawler got a mode that reads the Internet Archive's copies of Kenya Law pages and never contacts Kenya Law itself. The pilot made 126 requests and fetched 17 Act pages (every captured version of the Penal Code, KICA and the Employment Act), 73 judgments and 11 PDFs. It confirmed every structural assumption (see 4.6).
4. **Sexual Offences Act added.** All 9 of its versions (2006–2024) are archived, and all were fetched.
5. **Bulk judgment pull (running).** Every archived judgment of the three courts that decide whether a statute is valid:

   | Court | Code | Archived | Status (2026-09-23, 14:47 UTC) |
   |---|---|---|---|
   | Supreme Court | `kesc` | ~640 | done |
   | Court of Appeal | `keca` | ~5,550 | 5,355 done, 165 left |
   | High Court | `kehc` | ~10,900 | queued, ~4 h at the current rate |

   It runs as 3 parallel workers at about 50 pages per minute, with no rate-limit errors so far. The Internet Archive holds only about 10% of Kenya Law's ~275k judgments, so this is a large sample, not a mirror. Pages it never captured cannot be pulled this way.

### 4.3 How the crawler works

```
                 ┌─────────────────────────────── scope.*.yaml ───────────────────────────────┐
                 │ which hosts, which URL prefixes, how deep to follow links, rate, budget    │
                 └───────────────┬────────────────────────────────────────────────────────────┘
                                 ▼
 Internet Archive CDX index ──► wayback.py ──► frontier.db: urls (the queue, status per URL)
 "which captures exist?"        picks the                    │
                                newest capture               ▼
                                of each page      fetcher.py takes the next pending URL:
                                                  - checks robots.txt (Archive + Kenya Law's archived one)
                                                  - waits ≥2 s since its last request
                                                  - GET web.archive.org/web/<timestamp>id_/<original URL>
                                                  - 429/503 → back off; 401/403/challenge → stop everything
                                                             │
                                                             ▼
                                                  storage.py appends request + response to a
                                                  WARC file, and records the byte offset in
                                                  frontier.db: records
                                                             │
                           (later, offline, as often as you like)
                                                             ▼
                                                  parse.py reads each stored response by offset
                                                  → parsed/{act,judgment,source}/*.json
```

**Key properties**

- **Fetch once, parse many times.** Raw bytes are kept exactly as received, in WARC (the web-archiving standard format). Parsing never touches the network, so the parser can be improved and re-run on the stored copies.
- **Resumable.** Every state change is written to SQLite immediately. Kill the process at any point and re-run the same command to pick up where it stopped. A `.pid` lock file stops two copies from running on the same queue.
- **Polite by construction.**
  - It enforces a 2-second floor between requests from each worker.
  - It obeys robots.txt crawl delays.
  - On a 429/503 it waits (Retry-After, or 60 s doubling) and pauses the whole worker.
  - On any access control (401/403, login redirect, bot challenge) it writes `raw/STOPPED.txt` and exits instead of trying to get around it.
- **`id_` playback URLs.** `web.archive.org/web/<ts>id_/<url>` returns the page exactly as Kenya Law served it, with no Archive toolbar and no rewritten links. The parser sees the original HTML.
- **Parallel workers.** `--shard i/N` runs N workers side by side. Each takes the URLs whose `id % N == i`, and has its own lock and its own WARC files, so workers never collide.

**Scope files** (in `crawler/`) decide what a run fetches:

| File | Used for |
|---|---|
| `scope.wayback-pilot.yaml` | The pilot: the four Acts (every captured version), 3 anchor judgments, and a 60-judgment sample spread across courts and eras |
| `scope.wayback-judgments.yaml` | The bulk pull: every archived kesc, then keca, then kehc judgment. HTML only; no PDFs, since 97% of judgments have full HTML text |
| `scope.pilot.yaml` / `scope.full.yaml` | Direct Kenya Law crawl. Not used (see 4.2) |

### 4.4 How data is stored

**`raw/frontier.db` (SQLite), three tables**

| Table | One row per | Important columns |
|---|---|---|
| `urls` | URL we know about | `url`, `kind` (act / judgment / source / listing / other), `status` (**pending** = queued, **fetched** = stored, **failed** = error such as 404, **skipped** = not in the Archive), `http_status`, `depth` (lower is fetched first; ground-truth targets were set to −1 to jump the queue), `discovered_from` |
| `records` | WARC record | `warc_file`, `offset`, `length`: where the bytes are, so any page can be read back with a single seek. Also `uri`, `record_type` (request/response), `http_status`, `content_type`, `date` |
| `snapshots` | Archive capture | `original` URL, `timestamp`. Loaded from the Archive's CDX index; this is how we know what exists before fetching |

**WARC files.** Gzip-compressed, one member per record, rotated at ~1 GB. Each fetch stores two records: the request we sent and the full response (headers and body).

**Parsed JSON.** One file per document, for example `parsed/judgment/akn_ke_judgment_kesc_2017_2_eng@2017-12-14.json`:

| Field | Meaning |
|---|---|
| `url` | The original Kenya Law URL (even when fetched through the Archive) |
| `retrieved_from`, `retrieved_at` | The Archive URL actually fetched, and when |
| `kind` | act / judgment / source |
| `work` | The document regardless of version (e.g. `/akn/ke/act/1930/10` = the Penal Code) |
| `expression_date` | This version's date (the `eng@YYYY-MM-DD` part of the URL) |
| `title` | Page heading, e.g. "Republic v Mwangi … [2024] KESC 34 (KLR) (12 July 2024) (Judgment)" |
| `metadata` | Kenya Law's metadata box: Citation, Court, Case number, Judges, Judgment date, … |
| `display_type` | `akn` (structured statute), `html` (judgment text) or `pdf` (no HTML text) |
| `versions` | Every version date the page lists (Acts) |
| `sections` | Acts only: `[{eid, heading, text}]`, one entry per section |
| `remarks` | Editorial notes (`akn-remark`) with the section they belong to |
| `akn_links` | Links to other Kenya Law documents |
| `text` | Full plain text (whitespace-normalised) |
| `source_url` | Link to the original PDF, if any |

### 4.5 What we hold now

- **Acts:** 25 parsed Act-version pages. That's every archived version of the four Acts we need, plus the pilot extras:
  - Penal Code (Cap. 63): all 3 versions.
  - Sexual Offences Act (Cap. 63A): all 9 versions.
  - KICA (Cap. 411A): 2 of 13 versions (the rest were never archived).
  - Employment Act: 11 of 13 versions.
- **Judgments:** ~6,000 fetched: all of the Supreme Court and nearly all of the Court of Appeal. About 11,000 more are coming from the High Court. The `parsed/` copy only includes what was stored the last time `crawler.parse` ran, so re-run it after the pull.

### 4.6 What Phase 1 found (the facts later phases build on)

- **Sections have stable IDs (eIds)** that don't change between versions. One exception: the Employment Act's IDs changed at its 2022-12-31 revision (`sec_45` became `part_VI__sec_45`). The Penal Code, KICA and the Sexual Offences Act are unaffected. For example:
  - Penal Code s.204 = `part_II__chp_XVIII__subpart_nn_1__sec_204`.
  - The Sexual Offences Act has flat IDs: s.8 = `sec_8`.
- **Versions** appear in URLs as `eng@YYYY-MM-DD`, and every page lists all of its versions.
- **No court decisions are noted on any struck-down section**, in any version (see §1). This is the pitch.
- **Judgments:** ~97% have full HTML text. The metadata always has citation, court, case number and date; judges ~70% of the time. **There are no fields for parties, legislation cited or cases cited.**
- **Links from judgments to Acts can't be relied on.** They point at whole Acts only, never sections, and are often missing: *Muruatetu* has none to the Penal Code. **Citations must be extracted from the judgment text.** Kenya Law's editorial "legislation cited" tags can also be wrong: *Khalid* is tagged as having "interpreted" KICA s.29, which it never does.

---

## 5. Phase 2: ground truth

### 5.1 Aim

Build an **answer key**: a small table, checked by hand, of what courts actually did to specific statute sections, with the court's exact words. It has two uses:

1. **Demo data.** The tool can show correct results for the focus sections even before automatic extraction works.
2. **Benchmark.** In step 6, the automatic event classifier is scored against this table (precision and recall).

### 5.2 How it was built

| Step | Who | Output |
|---|---|---|
| Identify the cases (web search), fetch them from the Archive, read the operative orders, draft rows | Claude | `events.csv` draft (15 rows) |
| **Blind audit**: a second model read every judgment in full *before* seeing the draft, then compared | Opus subagent | `audit_blind.csv`, `audit.md`. Found 4 wrong rows and 2 missed events |
| Apply the audit fixes; find and add 2 more judgments (*Mutiso* 2010, CA *Ayako* 2023) | Claude | 18 rows |
| **Verification**: a third model checked every row against the source, decided the open questions, and made 6 corrections | Opus subagent | `decisions.md`; 17 of 18 rows verified |
| Final call on the one ambiguous row (E11) | Leo | 18 of 18 verified |

**Safeguard:** `check.py` confirms that every quote appears **word for word** in the stored judgment (ignoring whitespace), that every section ID exists in a stored Act, and that every cross-reference points to a real row. A made-up or mistyped quote fails the check.

### 5.3 `events.csv`: column by column

One row = one thing one court did to one section. The columns follow the `citation_events` table planned for the database (see `CLAUDE.md`).

| # | Column | What it holds | Example |
|---|---|---|---|
| 1 | `event_key` | Stable row ID within this file. Gaps are deliberate: E10 was removed after the audit, and keys are never reused | `E07` |
| 2 | `provision_id` | The section affected: `{jurisdiction}/act/{act-slug}/{eid}`. Always section-level | `ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204` |
| 3 | `judgment_id` | The judgment that did it: `{jurisdiction}/judgment/{court}/{year}/{number}` | `ke/judgment/kesc/2017/2` |
| 4 | `event_type` | What the court did (see 5.4) | `declared_unconstitutional` |
| 5 | `scope` | `total` or `partial`: how much of *this section* the event bears on (see 5.5) | `partial` |
| 6 | `scope_text` | The court's own words limiting the event, word for word. Required when scope is partial | "invalid to the extent that it provides for the mandatory death sentence for murder" |
| 7 | `operative_quote` | The court's own words that make the order or holding, word for word. **This is what the tool shows users** | "The mandatory nature of the death sentence as provided for under section 204 of the Penal Code is hereby declared unconstitutional…" |
| 8 | `source_paragraph` | The paragraph(s) in the judgment, using the source's own numbering | `112(a); scope_text from 69` |
| 9 | `effective_date` | Decision date | `2017-12-14` |
| 10 | `affects_event` | The earlier row this event acts on **directly** (an appeal from it, or further directions in the same case). Never mere precedent | `E07` (on E08) |
| 11 | `method` | How the row was made: `manual` (by reading) or, later, `extracted` (by the pipeline) | `manual` |
| 12 | `verified` | `true` once checked against the source | `true` |
| 13 | `confidence` | 0–1, filled only where the classification is debatable | `0.6` |
| 14 | `case_name` | Full case name and neutral citation, for humans | "Francis Karioko Muruatetu & another v Republic [2017] eKLR …" |
| 15 | `source_url` | Link to the judgment on Kenya Law | `https://new.kenyalaw.org/akn/ke/judgment/kesc/2017/2/eng@2017-12-14` |
| 16 | `notes` | Context: related paragraphs, what the audit changed (`[audit …]`), appeal status | |
| 17 | `flag` | An open question for a human. Empty = resolved | E18: "Mwaura (2013)… missing" |
| 18 | `subsection` | Filled only when the holding is limited to part of a section | `8(2)` |
| 19 | `verified_by` | Who verified: `agent:opus 2026-09-23` or `human:leo 2026-09-23` | |

**ID formats.** Every ID starts with the jurisdiction (`ke`), so the design can extend beyond Kenya. The act slug is the Cap. number: `cap-63` = Penal Code, `cap-63a` = Sexual Offences Act, `cap-411a` = KICA. The eid comes straight from Kenya Law's page markup and stays the same across versions. It encodes where the section sits: `part_II__chp_XVIII__sec_194` means Part II, Chapter XVIII, section 194.

### 5.4 Event types: what each one means

| `event_type` | Meaning | Effect on the section | Example in the table |
|---|---|---|---|
| `declared_unconstitutional` | The court declares the section (or part of it) inconsistent with the Constitution and invalid | Invalid, wholly (`total`) or to the stated extent (`partial`) | E01 *Andare*: KICA s.29 unconstitutional, total. E06 *Okuta*: s.194 "to the extent that it covers offences other than…" |
| `read_down` | The court doesn't strike the words out, but gives them a narrower meaning to make them constitutional. The section survives, *as read* | Still in force, but not as the plain text suggests | E09 *Kilwake*: s.8's minimum sentences "must be interpreted so as not to take away the discretion of the court". E19 *Ayako* (CA): life imprisonment "translates to thirty years" |
| `severed` | The court cuts out specific words and keeps the rest | Remaining text in force | (none yet) |
| `upheld` | The section was challenged and the court found it constitutional | In force, and now tested | E04/E05 *EG*: ss.162, 165 "not unconstitutional". E16/E17 *Khalid*: ss.78, 94(1) |
| `interpreted` | The court settles what the section, or an earlier ruling on it, means, without changing its validity | In force; meaning clarified | E08: the 2021 *Muruatetu* directions limit the 2017 ruling to murder under ss.203/204 |
| `reversed_on_appeal` | A higher court sets aside an earlier event (named in `affects_event`) | The earlier event no longer counts | E13: SC *Mwangi* reverses CA *Mwangi* (E11) |
| `repealed_by_statute` / `amended_by_statute` | Parliament changed the section. There is no judgment; `judgment_id` is empty | Per the amending Act | (not yet loaded; comes from the Acts' amendment notes in Phase 3) |

**Status is never stored. It is worked out from the sequence of events.** For example, Sexual Offences Act s.8:

```
2019 E09 Kilwake (CA)      read_down        minimums "must be interpreted" as discretionary
2022 E11 Mwangi (CA)       read_down        applies Muruatetu to SOA sentences      ─┐
2023 E12 Manyeso (CA)      declared_uncon.  life sentence (8(2)) unconstitutional    ─┼┐
2023 E19 Ayako (CA)        read_down        life = 30 years (8(2))                   ─┼┼┐
2024 E13 Mwangi (SC)       reversed_on_appeal  ◄──────────────────────────────────────┘││
2025 E14 Manyeso (SC)      reversed_on_appeal  ◄───────────────────────────────────────┘│
2025 E15 Ayako (SC)        reversed_on_appeal  ◄────────────────────────────────────────┘
→ Today: s.8 in force as written. Every Court of Appeal limit has been reversed; Kilwake's reasoning is displaced by Supreme Court precedent, not by a direct appeal.
```

And Penal Code s.204:

```
2010 E18 Mutiso (CA)       declared_uncon. (partial)  "to the extent that it provides that the death penalty is the only sentence"
2013 E20 Mwaura (CA)       upheld                     Mutiso held per incuriam: death sentence mandatory again
2017 E07 Muruatetu (SC)    declared_uncon. (partial)  mandatory death sentence for murder
2021 E08 Directions (SC)   interpreted → E07          applies only to murder under ss.203/204
→ Today: s.204 limited. The death sentence remains available at the court's discretion; it is no longer mandatory.
```

The rules that turn these sequences into a status (e.g. "a reversed event stops counting", "later Supreme Court precedent displaces a Court of Appeal read-down") will be written in a per-jurisdiction module in step 7.

### 5.5 Scope, subsection and affects_event: the precise rules

- **`scope`** always answers: *how much of this section does this event bear on?*
  - For `declared_unconstitutional` / `read_down` / `severed`: the part invalidated or narrowed.
  - For `upheld` / `interpreted`: the part the court actually ruled on. *EG* is `partial` because only s.162(a) and (c) were challenged; (b) never was.
  - For `reversed_on_appeal`: how much of the earlier judgment was set aside.
- **`subsection`** is filled only when the holding is limited to a sub-provision, e.g. `8(2)` for the life-sentence cases. `provision_id` stays at section level because Kenya Law's markup gives IDs only down to sections.
- **`affects_event`** only links an event to the one it **directly** acts on: an appeal from that judgment, or later directions in the same case. When a Supreme Court ruling in one case undercuts the reasoning in another (*Kilwake*), there is no link. That is precedent, and the status resolver handles it.

### 5.6 `negatives.csv`

Six judgments that **mention** a focus section but do nothing to it: a murder trial reciting "contrary to section 203 as read with section 204", or a later case citing *Andare* as authority. These catch the most likely extractor mistake: turning "this judgment mentions s.204" into "this judgment changed s.204". Columns: `judgment_id`, `provision_id`, `why_no_event`.

### 5.7 What is in the table

| Section | Events |
|---|---|
| KICA s.29 | E01 *Andare* 2016: struck down (total) |
| Penal Code s.66 (alarming publications) | E02 *Andama* 2021: struck down (total) |
| Penal Code s.78, s.94(1) | E16, E17 *Khalid* 2019: upheld |
| Penal Code s.132 (undermining authority) | E03 *Alai* 2017: struck down (total) |
| Penal Code s.162, s.165 | E04, E05 *EG* 2019: upheld |
| Penal Code s.194 (criminal defamation) | E06 *Okuta* 2017: struck down (partial) |
| Penal Code s.204 (murder sentence) | E18 *Mutiso* 2010, E20 *Mwaura* 2013, E07 *Muruatetu* 2017, E08 Directions 2021 |
| Sexual Offences Act s.8 (defilement) | E09, E11, E12, E19 (Court of Appeal limits) → E13, E14, E15 (Supreme Court reversals) |

---

## 6. Glossary

| Term | Meaning |
|---|---|
| **AKN (Akoma Ntoso)** | The XML/HTML standard for legal documents that Kenya Law's platform (Peachjam, by Laws.Africa) uses. It is why sections have machine-readable IDs |
| **eId** | Akoma Ntoso element ID for a provision (`data-eid` in the HTML), e.g. `part_III__sec_29`. Stable across versions |
| **Work / expression** | The *work* is the Act regardless of version (`/akn/ke/act/1930/10`); an *expression* is one dated version (`…/eng@2023-12-11`) |
| **Cap.** | Chapter number in the Laws of Kenya: Cap. 63 = Penal Code |
| **Court codes** | `kesc` Supreme Court · `keca` Court of Appeal · `kehc` High Court. Also `keelc` Environment & Land, `keelrc` Employment & Labour Relations |
| **eKLR / KLR, neutral citation** | Kenya Law's citation formats: `[2017] eKLR` (older), `[2024] KESC 34 (KLR)` (newer; court + number) |
| **Operative order** | The part of a judgment that actually decides: declarations and orders, usually at the end. Distinct from the reasoning |
| **"To the extent that"** | The standard wording of a *partial* declaration. Only that part of the section is invalid |
| **Read down** | Giving a provision a narrower meaning so that it complies with the Constitution, instead of striking it out |
| **Per incuriam** | "Through lack of care": a later court's finding that an earlier decision was wrong because it overlooked binding law, so it need not be followed |
| **Stare decisis / precedent** | Lower courts are bound by higher courts' rulings. This is how a Supreme Court decision can displace a Court of Appeal reading without an appeal in that case |
| **WARC** | Web ARChive file format (ISO 28500), the standard for storing fetched web pages byte for byte |
| **CDX** | The Internet Archive's capture index: which URLs it holds, and when they were captured |
| **Frontier** | The crawler's queue of URLs and their states |
| **Ground truth** | Hand-verified rows (`method=manual`, `verified=true`) that the automatic pipeline is scored against |

---

## 7. Open items and next steps

**Open**

- **E20 (*Mwaura*, 2013)** was saved by hand into `raw/manual/`, because the Internet Archive doesn't have it. `crawler.parse` now also reads hand-saved pages from that folder.
- **Appeals of *EG*, *Alai* and *Andama*** haven't been checked. *Okuta* and *Andare*: no appeals found (absence unverified).
- **The live Kenya Law pages** should be re-checked before the presentation, to confirm they still lack court notes (our evidence is from Archive snapshots).
- **Schema changes** proposed by the verification (`ground_truth/decisions.md`), to fold into Phase 3: a `subsection` column, a `verified_by` column, the scope and `affects_event` definitions above, and possibly a `superseded_by_precedent` event type.

**Next (from `CLAUDE.md`)**

3. Load Acts, versions, sections and section texts into Postgres (+ pgvector).
4. Load the parsed judgments into the `judgments` table.
5. Citation extraction (regex first, an LLM for messy cases) → `citation_mentions`; score it on a hand-checked sample.
6. Event classification → `citation_events`; score it against this ground truth.
7. Status resolver (per-jurisdiction rules), then API (FastAPI) and UI (Next.js).
8. Synthetic demo filings (clearly labelled) and the filing checker.
9. Deploy end to end.
