# LexHack: a citator for Kenyan statutes

LexHack tells you whether a section of a Kenyan law is **still good law**: in force, amended, repealed, or limited or struck down by a court. It links court judgments to the exact statute sections they affected, and it always answers with the **court's own words and a link to the source**, never a bare yes or no. A filing checker sits on top: give it a legal document, and it flags citations that are fake, misquoted, or that rely on a section a court has struck down.

This file explains the project from scratch: what has been built, how the data flows, and how to read every file. `CLAUDE.md` holds the design brief and the working rules.

| Phase | What it covers | Status |
|---|---|---|
| **1. Data acquisition** | Get the statutes and judgments onto disk, legally and reproducibly | Done: 8 Acts, 16,824 judgments |
| **2. Ground truth** | A hand-checked answer key of what courts did to which sections | Done: 19 events, all verified |
| **3. Database** | Load Acts, versions and sections into Postgres (Neon), with embeddings | Done: 8 Acts, 1,862 sections, 4,592 section texts, all embedded |
| **4. Judgments + answer key** | Load judgment metadata and the answer key into Postgres | Done: 16,419 judgments; 19 answer-key events in `citation_events` |
| **5. Citation extraction** | Find every "section N of the X Act" / "Article N" in the judgments → `citation_mentions` | Done: 304,310 mentions in 13,098 judgments; 182,571 linked to our sections. Held-out score: precision 98.1%, recall 98.1%, law right 97.8% with the LLM pass (DeepSeek; Gemini for the first ~400 judgments) |
| 6–9 | Classify events, status resolver, API/UI, filing checker, deploy | Not started |

---

## Contents

1. [Why this exists](#1-why-this-exists)
2. [Where things live](#2-where-things-live)
3. [Quick start](#3-quick-start)
4. [Phase 1: data acquisition](#4-phase-1-data-acquisition)
5. [Phase 2: ground truth](#5-phase-2-ground-truth)
6. [Phases 3–4: the database](#6-phases-34-the-database)
7. [Phase 5: citation extraction](#7-phase-5-citation-extraction)
8. [Glossary](#8-glossary)
9. [What's left, and blind spots](#9-whats-left-and-blind-spots)

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
  pipeline/                          ← Phases 3–4: load everything into Postgres (Neon)
    schema.sql      all tables; idempotent, applied by every loader
    db.py           connection (direct/unpooled URL) + apply_schema
    load_acts.py    Acts → acts, act_versions, provisions, provision_texts
    embed.py        gemini-embedding-2 vectors for section texts (disk-cached)
    load_judgments.py   judgment metadata → judgments
    load_ground_truth.py  ground_truth/events.csv → citation_events
    extract_citations.py  Phase 5: regex citation extraction → citation_mentions
    test_extract.py       offline regression cases for the citation grammar
    llm_resolve.py        Phase 5: DeepSeek (or Gemini) resolves bare mentions ("section 39", "the Act"); disk-cached, --shard i/N
  ground_truth/                      ← Phase 2 (+ Phase 5): the answer keys
    events.csv      19 verified events (the main output)
    negatives.csv   6 judgments that cite a section without affecting it
    check.py        verifies every quote against the stored judgments
    audit.md, audit_blind.csv, decisions.md   ← how the table was checked
    mentions_README.md    Phase 5 answer key: labelling rules and how it was verified
    mention_sample.py     draws the 30-judgment sample → mentions_candidates.csv
    mentions_gold.csv     the verified labels (711 rows, 581 citations)
    mentions_review_*.csv the three verifiers' verdicts, one per court
    eval_mentions.py      scores the extractor (and, with --llm [--llm-model M], the LLM pass)
    show_candidate.py     prints judgment text around a candidate, for labelling
    mentions_heldout_*.csv   held-out sample (never tuned on) and its double-labelled answer key
    heldout_labels/       the two independent labellings per court, disagreements, adjudications
    heldout_merge.py      merges the two labellings into mentions_heldout_gold.csv
  letters/
    kenyalaw_bulk_request.md   draft letter asking Kenya Law for bulk data

$LEXHACK_DATA  (outside the repo; per machine: /Users/leo/lexhack-data on Leo's Mac, C:/Users/user/lexhack-data on Windows)
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
  cache/embeddings/*.json           ← one vector per unique text (keyed by model + text hash)
  cache/llm/*.json                  ← one LLM answer per prompt (keyed by model + prompt version + prompt hash)
  external/hf_ipfs_kenya_laws/       ← a third-party dataset we evaluated
```

`.env` also holds `DATABASE_URL` / `DATABASE_URL_UNPOOLED` (Neon, written by `neon link`) and `GEMINI_API_KEY`.

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
uv run python -m pipeline.load_ground_truth                   # ground_truth/events.csv -> citation_events (method='manual')
uv run python -m pipeline.test_extract                        # citation grammar self-check (offline)
uv run python -m pipeline.extract_citations                   # regex → citation_mentions (rebuilds ALL mention rows)
uv run python -m pipeline.llm_resolve                         # DeepSeek for bare mentions; run after every extraction (cached)
uv run python -m ground_truth.eval_mentions --llm             # score extraction against the verified sample
uv run python -m pipeline.classify_events --answer-key        # step 6 on the answer-key judgments (then: no flag = all)
uv run python -m ground_truth.eval_events                     # score event classification
uv run python -m pipeline.verify_events                       # second-pass check of extracted events
uv run python -m ground_truth.eval_checker                    # score the checker on the blind reviews
uv run python -m api.test_status                              # status rules, offline
uv run uvicorn api.main:app --reload                          # the API; spec at /docs

# the bulk judgment pull (3 parallel workers; re-running resumes where it stopped)
for i in 0 1 2; do nohup uv run python -m crawler.crawl run \
  --scope scope.wayback-judgments.yaml --shard $i/3 > $LEXHACK_DATA/raw/s$i.out 2>&1 & done
pkill -TERM -f "crawler.crawl run"                            # stop it (background jobs ignore Ctrl-C)
```

**On Windows,** set `PYTHONUTF8=1` first (`setx PYTHONUTF8 1`, then open a new terminal). Much of the code reads files without naming an encoding, and Windows would otherwise read them as cp1252 and crash on judgment text. `uv` installs to `C:\Users\<you>\.local\bin`.

### Sharing `$LEXHACK_DATA` between machines (Cloudflare R2)

The data folder (~880 MB: WARCs, parsed JSON, LLM and embedding caches) is shared through a Cloudflare R2 bucket
(`lexhack-data`, free tier 10 GB, no download fees) with rclone. Each person keeps a normal local copy, so the pipeline
stays fast; the bucket is the shared master.

```sh
scripts/sync.sh pull                  # get what the other person added   (Windows: .\scripts\sync.ps1 pull)
scripts/sync.sh push                  # upload what you added            (Windows: .\scripts\sync.ps1 push)
scripts/sync.sh push --dry-run        # show what would be copied
scripts/sync.sh push --with-frontier  # also raw/frontier.db: ONLY the person who crawls
```

- **Copies only; never deletes** on either side. Files are compared by checksum, so re-parsing doesn't re-upload unchanged files.
- **Safe both ways:** cache files are named by a hash of their input, so two people's LLM and embedding caches merge without overwriting each other.
- **Not synced by default:** `raw/frontier.db` (the crawler's live database; one writer only), logs, lock files.
- **Don't sync while a pipeline job is running.** Pull before starting work; push after a run.
- **Setup, once per machine:** install rclone and run `rclone config` to add an S3 remote named `lexhack-data`: provider Cloudflare, your R2 **Access Key ID (32 characters)** and **Secret Access Key**, endpoint `https://<account-id>.r2.cloudflarestorage.com` (**without** the bucket name). Check with `rclone lsd lexhack-data:`. A different remote or bucket: set `LEXHACK_R2=remote:bucket`.

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
5. **Bulk judgment pull (finished 2026-09-23).** Every archived judgment of the three courts that decide whether a statute is valid:

   | Court | Code | Fetched | Missing from the Archive |
   |---|---|---|---|
   | Supreme Court | `kesc` | 625 | 0 |
   | Court of Appeal | `keca` | 5,520 | 34 |
   | High Court | `kehc` | 10,679 | 220 |

   It ran as 3 parallel workers at about 50 pages per minute and hit the Archive's rate limit only 3 times. The fetched pages parse to 16,419 distinct judgments: some judgments were fetched more than once and collapse into one. 286 of them are PDF-only, so they have no text. The Internet Archive holds only about 10% of Kenya Law's ~275k judgments, so this is a large sample, not a mirror. Pages it never captured cannot be pulled this way.
6. **One judgment saved by hand.** CA *Mwaura* (2013), needed for the answer key, isn't in the Archive. It was saved from Kenya Law through Chrome into `raw/manual/`; `crawler.parse` reads that folder too.
7. **Four more Acts (2026-09-26).** The judgments cite these far more than our focus Acts, so step 5 needs them to link citations to sections: the Constitution (cited in 6,730 judgments), the Civil Procedure Act (5,033), the Evidence Act (2,234) and the Criminal Procedure Code (2,162). All four came from the Archive.

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

- **Acts:** 31 versions of 8 Acts, every version the Archive holds:

  | Act | ID | Versions | Sections |
  |---|---|---|---|
  | Penal Code (Cap. 63) | `ke/act/cap-63` | 3 of 3 | 416 |
  | Sexual Offences Act (Cap. 63A) | `ke/act/cap-63a` | 9 of 9 | 52 |
  | KICA (Cap. 411A) | `ke/act/cap-411a` | 2 of 13 | 198 |
  | Employment Act (Cap. 226) | `ke/act/cap-226` | 11 of 13 | 190 |
  | Constitution of Kenya, 2010 | `ke/act/constitution` | 1 | 264 articles |
  | Civil Procedure Act (Cap. 21) | `ke/act/cap-21` | 2 | 116 |
  | Evidence Act (Cap. 80) | `ke/act/cap-80` | 1 | 199 |
  | Criminal Procedure Code (Cap. 75) | `ke/act/cap-75` | 2 | 427 |

  The Constitution has no Cap. number, so its ID comes from its Kenya Law address. Its articles use `sec_` IDs like everything else, e.g. Article 50 is `chp_Four__part_2__sec_50`.
- **Judgments:** 16,419 distinct judgments, all parsed.

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

## 6. Phases 3–4: the database

### 6.1 Aim

Put everything into one Postgres database (Neon, with pgvector), so the later steps (extraction, the status resolver, the API) query one place.

### 6.2 What's in it

| Table | Rows | Loaded by | What it holds |
|---|---|---|---|
| `acts` | 8 | `load_acts.py` | One row per Act: ID, title, Cap. number, Kenya Law work URI |
| `act_versions` | 31 | `load_acts.py` | One row per dated version; `raw_path` points at the parsed JSON |
| `provisions` | 1,862 | `load_acts.py` | One row per section (ID stable across versions), with its number and heading |
| `provision_texts` | 4,592 | `load_acts.py`, `embed.py` | A section's text in one version, plus a full-text index (`tsv`) and a 1,536-number meaning vector (`embedding`) |
| `judgments` | 16,419 | `load_judgments.py` | Metadata only: citation, title, court, case number, date, judges, Kenya Law link, path to the full text on disk |
| `citation_events` | 19 | `load_ground_truth.py` | The answer key (`method = 'manual'`). Step 6 will add extracted rows |
| `citation_mentions` | 304,310 | `extract_citations.py`, `llm_resolve.py` | Every citation found in a judgment: span, paragraph, cited law (`act_ref`), section (`section_ref`), and `provision_id` when it's one of our 8 Acts. See §7 |

The full schema, with a comment on every column, is `pipeline/schema.sql`. It includes the verifier's additions: `subsection`, `verified_by`, `notes`, and a list of allowed event types.

### 6.3 Design decisions

- **The full text of judgments stays on disk, not in Postgres.** It's ~360 MB, and Neon's free plan caps storage at ~0.5 GB. The database is 215 MB (Sept 27), most of it `citation_mentions`. Every judgment row has `raw_path` to its text file.
- **Loaders are re-runnable.** Each applies the schema first, then updates rows in place. Re-running `load_acts` keeps a section's embedding unless its text changed.
- **Loaders use the direct (unpooled) connection,** as Neon recommends for bulk writes and schema changes. The app will use the pooled one.
- **Embeddings:** `gemini-embedding-2` at 1,536 dimensions, chosen over `gemini-embedding-001` because it reads up to 8,192 tokens (001 reads 2,048) and returns normalised vectors. Each unique text is embedded once and cached on disk, so identical sections across versions cost one call.
  - **Limit:** Google's free tier allows 1,000 texts per day per model. `embed.py` stops with a clear message when that's hit; re-running resumes from the cache.
  - **Don't mix models:** vectors from different models can't be compared. Changing the model means re-embedding everything.
- **Search check.** Search by meaning finds Penal Code s.194 for "publishing false statements that damage someone's reputation" and s.204 for "sentence for killing a person". It missed Sexual Offences Act s.8 for "sex with a child under eighteen", which is why the plan combines it with word search (hybrid).

## 7. Phase 5: citation extraction

### 7.1 Aim

Find every place a judgment cites a section or Article of a law, and link it to our provisions where we hold that law. Links from Kenya Law's metadata are whole-Act only and often missing (§4.6), so citations come from the judgment text.

### 7.2 How it works

1. **Regex** (`pipeline/extract_citations.py`) reads each judgment's text from disk and finds citations in two shapes: "section 204 of the Penal Code" (law after) and Kenya Law's headnote lists "Elections Act (Cap 7), sections 34(6B), 35" (law first). It handles lists ("sections 203 and 204", "articles 38(3)(c); 75; 87"), ranges ("sections 3 to 7"), "as read with", sub-provisions ("165 (6) & (7)"), acronyms (SOA, CPC, KICA), Cap numbers, and "the Act"/"the Code" (→ the last Act named earlier in the judgment).
2. **Every law is recorded** in `act_ref`, not only our 8 Acts, so mentions of other Acts show what to load next. `provision_id` is set only when the citation resolves to a section we hold.
3. **LLM pass** (`pipeline/llm_resolve.py`) takes the citations the regex couldn't tie to a law (a bare "section 39") and asks which law is meant, choosing only from the laws that judgment names, or `unknown` / `not_a_citation`. Resolved rows become `method = 'llm'`, with the answering model in `llm_model`.
   - **Models:** the first ~400 judgments were done with `gemini-3.5-flash-lite` (its JSON mode enforces the list as an enum). The rest used `deepseek-flash` (thinking off), which is far cheaper and faster than Gemini's free tier. DeepSeek's JSON mode doesn't enforce the list, so the prompt spells it out and every answer is validated in code: off-list or malformed answers count as `unknown`. A name written slightly differently ("the Penal Code") is accepted only if it matches exactly one option. An Article is never attributed to the repealed Constitution.
   - **Re-runs are free:** a judgment's prompt is always rebuilt as it was first asked, including rows already resolved, so a re-run hits the cache. A chunk with a cached Gemini answer keeps it.
   - **Parallel:** `--shard i/N`. Each worker updates only its own judgments' rows. Database connections use keepalives and timeouts, and a dropped connection is retried.

**Rules the extractor applies:**
- "section N of the Constitution" is the **repealed** (pre-2010) Constitution; the 2010 Constitution has Articles.
- A bare "Article N" is the 2010 Constitution (confidence 0.85), unless the judgment predates it or the text says "Article N of" something else.
- In a mixed list ("article 178(1) as read with section 21(1) of the Elections Act"), the named law applies only to the items of the same kind as the one next to it.
- The Employment Act's two eId schemes are picked by decision date (§4.6).

`confidence` describes how the law was identified: 0.95 named in full, 0.9 acronym or Cap, 0.85 bare Article, 0.6 "the Act", 0.4–0.8 LLM (low/medium/high), 0 unresolved.

### 7.3 Results (2026-09-27, LLM pass complete)

| | Mentions |
|---|---|
| Total | 304,310 in 13,098 judgments |
| Resolved to one of our sections | 182,571 (173,014 before the LLM pass) |
| Resolved by the LLM | 41,382: 38,366 by `deepseek-flash`, 3,016 by `gemini-3.5-flash-lite` |
| Still unresolved (no law) | 5,186 (the LLM said `unknown` or `not_a_citation`; the verdicts are in the cache) |
| In one of our Acts, but the section number doesn't exist | 366 (before the LLM pass) |

The LLM pass made 200 more judgments eligible for step 6 (they now cite one of our non-Constitution sections at confidence ≥ 0.8). The DeepSeek run took ~5 h with 8 workers on an unstable connection, at a cost of roughly $1.50–2 (off-peak).

### 7.4 How it was scored

`ground_truth/mentions_README.md` has the details. In short: 30 random judgments (10 per court), 551 candidates found by a deliberately broader pattern than the extractor's, 581 citations labelled by Claude, then checked against the full judgments by three independent subagents that never saw the extractor (544 ok, 7 proposed fixes, 1 accepted).

| | Score |
|---|---|
| Precision | 99.5% (572/575) |
| Recall | 98.5% (572/581) |
| Law right / wrong / unresolved (regex only) | 93.5% / 0% / 6.5% |
| Law right / wrong / unresolved (with Gemini) | 99.3% / 0% / 0.7% |
| Law right / wrong / unresolved (with DeepSeek) | 99.0% / 0% / 1.0% |

**Caveat:** the regex was fixed using this same sample (recall was 90.2% before), so its scores are optimistic. The LLM prompt was not tuned on it. The held-out sample below gives numbers to quote.

**Held-out score (2026-09-27), the numbers to quote.** A second, disjoint sample of 30 judgments (seed 777, none from the tuning sample; `mentions_heldout_*`). Two independent labellers per court, each blind to the extractor and to the other: they agreed on 469 of 471 candidates; the 2 disagreements were settled by the rule above (`heldout_labels/resolved.csv`). The regex was **not** changed after scoring.

| Regex only, held-out | Score |
|---|---|
| Precision | 98.1% (410/418) |
| Recall | 98.1% (410/418) |
| Law right / wrong / unresolved | 88.8% / 0.5% / 10.7% |
| … with the Gemini LLM pass | 98.3% / 1.0% / 0.7% |
| … with the DeepSeek LLM pass (used for the full run) | **97.8% / 1.0% / 1.2%** |

The two LLMs make the same 2 mistakes (ss.1A and 1B attributed to the Appellate Jurisdiction Act instead of the Civil Procedure Act, in one judgment); DeepSeek leaves 2 more citations unresolved. Score one model at a time with `eval_mentions --set heldout --llm [--llm-model gemini-3.5-flash-lite]`.

What the regex gets wrong: "sections 25 A (1)" (a space inside the number); a list ending "…50 and 51 were violated"; sections of a private document ("Section 1" of an insurance policy); treaty articles taken for the Constitution ("article 13" of the ICCPR); "Article 21(A)" of the Supreme Court Act taken for the Constitution. `uv run python -m ground_truth.eval_mentions --set heldout --errors` lists them all.

## 7b. Phase 6: event classification (in progress)

**Aim:** decide what each court DID to each of our sections it cites (README §5.4 types) → `citation_events` with `method = 'extracted'`.

**How** (`pipeline/classify_events.py`):
- **Candidates:** 2,048 judgments that cite one of our non-Constitution sections and contain ruling language anywhere ("unconstitutional", "we declare", "read down", "per incuriam", "minimum sentence", …). The phrase is searched at judgment level, not next to the citation, because rulings often don't repeat the section number (CA *Ayako*: "life imprisonment translates to thirty years").
- **One LLM call per judgment**, now `deepseek-flash` (DeepSeek V4.1 Flash, thinking off, JSON mode). `gemini-3.5-flash-lite` still works by changing `MODEL`. The model reads excerpts: the opening, 1,500 characters around every citation of a listed section and every ruling phrase, and the last 12,000 characters (the orders). It may only name sections the judgment cites (JSON enum).
- **Quotes are checked against the full text.** Spacing differences are ignored, but the stored quote is always the source's own characters. A quote shortened with "..." is accepted only if every part is verbatim and in order. Quotes that don't match are dropped, never stored paraphrased. The paragraph is computed from where the quote sits.
- Answers are cached (`cache/llm/`, keyed by model + prompt version). `event_runs` records which judgments have been classified. Re-running a judgment replaces its rows.

**Score on the answer key** (`uv run python -m ground_truth.eval_events`):

| Prompt | Events found | Type right | Scope right | False alarms (negatives) |
|---|---|---|---|---|
| v2 (full text) | 13/19 | 11/13 | 9/13 | 0/6 |
| v4, gemini-3.5-flash-lite | 17/19 | 15/17 | 13/17 | 0/6 |
| **v4, deepseek-flash (used for the full run)** | **19/19** | **18/19** | **16/19** | **0/6** |

**Caveat:** the prompt was refined against these same 19 events, so this is optimistic. An honest number needs a review of a random sample of the full run. Known weaknesses: the SC reversals of *Manyeso* and *Ayako* are still missed; partial declarations are sometimes called `read_down`; and some "extras" are sections the court only applied (CPC s.333) or a holding assigned to the wrong section.

**Honest precision (2026-09-27): about 53%.** 40 random extracted events outside the answer key (`events_review_sample.py`, seed 7), reviewed blind by two independent reviewers (`events_review_A/B.csv`; `uv run python -m ground_truth.eval_events_review`): 20 of the 38 they agreed on are right, 17 are not events, 1 is on the wrong section, 2 are split. Real events are well labelled: the type is right every time, and 19 of 20 carry the court's own operative words. The errors are false positives:
1. **Following another court's ruling** counted as the court's own event (12–15 of 17): sentencing appeals applying *Muruatetu* / *Kilwake* / SC *Mwangi*.
2. **`reversed_on_appeal`: 0 of 5 right.** Every ordinary "appeal allowed / sentence set aside" was labelled a reversal.
3. **Generic orders** ("all other findings are upheld") read as upholding a section. In *CORD* (Evidence Act s.20A) this inverts the real outcome.

**Prompt v5 (2026-09-27)** adds explicit rules for those three patterns. The answer key still scores 18/19 found, 18/18 right type, 0/6 false alarms. The full re-run left 189 events in 122 judgments (read_down 68 → 16, reversed_on_appeal 15 → 6).

**Round 2 (fresh sample: seed 11, 40 events from judgments round 1 never saw; `eval_events_review --round 2`): 28 of 36 agreed events right, about 78%** (70–78% counting the 4 split cases either way). Remaining errors: courts restating the *Muruatetu* directions or SC *Mwangi* without reasoning of their own, recorded as upheld/interpreted (6); two wrong types; `upheld` scope defaulting to total when one subsection was argued. Also, one judgment (*Kahinga*, Petition 618 of 2010) exists under two judgment IDs, so its events are double-counted.

**How they're used:** the API returns only verified events by default (`include_unverified=false`). Extracted events are machine-found leads, shown as unverified, never as a section's status.

**Prompt v6 and round 3 (fresh sample, seed 13).** v6 adds: restating a higher court is not an event; read_down vs interpreted; scope for upheld. Round 3 scored 17/37 (46%); 9 of its 20 errors were real rulings pinned on the **wrong Act** ("sections 22, 23… of the Act" in a Computer Misuse Act case linked to KICA by the step-5 "last named Act" rule). Fix: the classifier is only offered sections linked at confidence ≥ 0.8 (`MIN_LINK_CONFIDENCE`; "the Act" guesses are 0.6). Re-run: 143 events.

**Second-pass checker (`pipeline/verify_events.py`).** One DeepSeek call per extracted event, **thinking mode on**, asking only: is this the court's OWN holding, and on the claimed section of the claimed Act? Verdict in `citation_events.check_verdict`; the API never returns `fail` events. Scored on all 111 reviewed events where the two reviewers agreed (`uv run python -m ground_truth.eval_checker`):

| | Before the check | After the check |
|---|---|---|
| Precision, all 3 rounds | 65/111 (59%) | **61/76 (80%)** |
| Wrong events caught | | 31/46 (67%) |
| Right events kept | | 61/65 (94%) |

Caveat: the checker's rules were written (as general rules) after reading the reviewers' reports, so 80% may be slightly generous; call it 75–80%. What still slips through: courts *stating* a sentencing rule while applying higher-court law. On the live data: 119 pass, 23 fail, 1 unsure → **120 extracted events shown as unverified leads** (60 declared, 34 upheld, 16 interpreted, 6 read down, 4 reversed).

**DeepSeek:** its JSON mode doesn't enforce a schema, so every answer is checked in code (section must be one the judgment cites; type, scope and confidence must be allowed values). Labels without the "(heading)" are accepted when unambiguous. Key: `DEEPSEEK_API_KEY` in `.env`. The full run (2026-09-27): 2,051 judgments in ~37 min with 8 workers (`--shard i/8`; finished judgments are skipped on re-run), 271 events in 196 judgments; about $3–4 off-peak.

**Gemini cost, for reference:** `gemini-3.5-flash` has a free limit of 20 requests a day; `3.5-flash-lite`'s is higher. For all 2,048 judgments with v4's excerpts: ~14M input tokens, about $12 if billing is on; on the free tier, several days at the daily limit.

## 7c. Phase 7: status resolver and API

### Status resolver (`api/status_ke.py`, `api/status.py`)

Turns a section's events into a status plus the events behind it. Rules for Kenya (pure functions, `api/test_status.py` checks them on the answer key):
1. **Direct reversal:** an event named in a later `reversed_on_appeal`'s `affects_event` is "reversed on appeal".
2. **Precedent:** an event is "displaced by a later ruling" when a later event from a court of **equal or higher rank** points the other way (limits vs validates). So *Mwaura* (CA 2013) displaces *Mutiso* (CA 2010), *Muruatetu* (SC 2017) displaces *Mwaura*, and the Supreme Court's 2024–25 rulings displace *Kilwake* (CA 2019), which was never appealed.
3. `interpreted` events never displace anything; they travel with the events they qualify.
4. Status labels: "declared unconstitutional", "limited by a court", "in force; its validity has been tested in court", "in force; earlier court limits were reversed", "in force; interpreted by a court", "in force; no recorded court rulings", "repealed". **Always shown with the events and quotes behind it.**
5. Where the answer key and the extractor record the same ruling, the verified row wins. Extracted rows are returned with `verified: false`.
6. **Renumbered sections** (2026-10-07; `api/status.py` `renumbering`, the one lookup every caller uses): two IDs in one Act whose versions don't overlap (one ID's versions all before the other's) and whose **headings match** (case, punctuation and small slips ignored, difflib ratio ≥ 0.9; s.71's Industrial Court → Employment and Labour Relations Court as an alias; `[Spent]`/`[Deleted…]` headings match only a placeholder with the same number) are one section that Kenya Law renumbered, whatever the numbers: the match must be unique (same number breaks a tie between two later "Interpretation" sections). That gives the Employment Act's 2022-12-31 revision (`sec_45` → `part_VI__sec_45`; old ss.83–91 moved down one place (new ss.82–90), so old s.85 "Security in foreign contract of service" is new s.84; old ss.92–93 and new ss.91–92 `[Spent]` stay apart; 92 pairs) and Law of Succession s.43 (Part V → Part VI in 2021). `api.test_tools` checks every merged pair's headings. Status, history, summary, `cited_by`, leads and citing judgments merge across both IDs (each event keeps its own `provision_id`); the provision response adds `renumbered_from` / `renumbered_to` (`{provision_id, number, versions}`; the page names both numbers when they differ); the Acts list shows the pair once, by the current ID; `find_section` returns the current ID with `renumbered_from`, and both sections when a number moved ("s.85": old s.85 = new s.84, and new s.85). Overlapping versions stay two sections. So *Momanyi* (event 925, made on `sec_45`) now limits `part_VI__sec_45` too.

Results: s.204 → "limited by a court" (*Muruatetu* + the 2021 directions in effect; *Mutiso* and *Mwaura* displaced). s.8 → in force; every Court of Appeal limit reversed or displaced. s.194 → "limited by a court" (*Okuta*).

### API (`api/main.py`, FastAPI)

`uv run uvicorn api.main:app --reload`, then http://127.0.0.1:8000/docs for the live OpenAPI spec. **The Pydantic models in `api/main.py` are the contract the UI builds against.**

| Endpoint | Returns |
|---|---|
| `GET /api/acts` | The 8 Acts with their version dates |
| `GET /api/acts/{act_id}/provisions` | Sections of an Act, in number order |
| `GET /api/provisions/{provision_id}` | The section's latest text, `status`, `summary_events`, full `history`, and a disclaimer. `?include_unverified=false` hides extracted events |
| `GET /api/stats` | Counts for the UI: Acts, sections, judgments, verified events and sections, leads, cited sections |
| `GET /api/provisions/{provision_id}/citations` | Judgments that cite the section (highest court first, then newest), each with its first citation as written. `?limit=&offset=` |
| `GET /api/search?q=` | Hybrid search: Postgres full-text + meaning (pgvector), merged by reciprocal rank fusion; each hit carries its status. Falls back to words only if the embedding call fails |

Each event carries the court's verbatim `operative_quote`, `scope_text`, paragraph, date, court, case name, citation, Kenya Law link, `verified`, and `state` / `superseded_by`. CORS allows `http://localhost:3000` (set `CORS_ORIGINS` to change).

**Known limit:** search matches the statute's own words, so colloquial names miss: "criminal defamation" ranks s.194 fourth (its text says "libel"), and "sex with a child" misses SOA s.8 ("defilement"). A synonym list or citation-based ranking would fix it.

**Unverified leads never change the status** (`api/status.py` `with_leads`): with `include_unverified=true`, status, summary and the states of verified events come from verified events alone; leads are only added to the history. Before this fix a lead could flip s.8's status. `api/test_status.py` checks it.

Sections in lists, search hits and the provision response also carry `cited_by` (distinct citing judgments) and `lead_count` (unverified leads hidden by default).

### Agent review of extracted events (`pipeline/review_events.py`)

Turns unverified leads into checked rulings. Code exports each case (claim, section text, judgment text on disk, and a verbatim check of the quote); reviewer agents follow `pipeline/review_brief.md` (same event definitions as §5.4) and write verdicts to `$LEXHACK_DATA/review/<set>/verdicts/`.
- **Benchmark** (`export --set benchmark`, `score`): the 111 events two blind reviewers agreed on. Agents accepted 59, all right (precision 100%); kept 59 of 63 real events; 3 unsure. The 4 misses are Court of Appeal "we declare" orders resting only on "emerging jurisprudence", rejected as following.
- **Applied** (`apply`, idempotent, 2026-09-27): 90 accepts, 35 rejects, 6 unsure on live events → 108 verified events on 59 sections. 8 operative quotes replaced by the reviewer's better quote, only where code found it verbatim.
- Accepts get `verified_by = 'agent:claude-opus-5-5 review v1'`; rejects get `check_verdict = 'fail'`. Re-run `apply` after `classify_events`/`verify_events`.

### Duplicate judgments (`pipeline/dedupe_judgments.py`)

219 groups share court, case number and date; 181 copies have matching text (word 5-gram overlap ≥ 0.7; copies score ≥ 0.78, different rulings ≤ 0.52) and get `judgments.duplicate_of`. The API skips their events and counts citations once. E.g. *Kahinga* (Petition 618 of 2010) was stored three times.

### Web UI (`web/`, Next.js): **Hakiki**

The product is called **Hakiki** (Swahili for "verify"); LexHack is the hackathon.

`cd web && pnpm dev` (with the API running), then http://localhost:3000. Routes and design notes: `web/README.md`. Server components call the API directly (`API_URL`, default `http://127.0.0.1:8000`).
- **Section page** (`/p/{provision_id}`): the statute text as Kenya Law publishes it, a status stamp (words, never a flag), the rulings behind the status in the court's words, a **lineage chart** (one lane per court rank, an arrow from each ruling to the one it reversed or displaced), and every ruling in full. `?leads=1` adds unverified leads, drawn dashed.
- **Home**, **Acts** (versions + filterable sections, with statuses, citation counts and leads), **search** and **About** (how to use it, what each status means, where the data comes from).
- **Display-only tidying** (`web/lib/text.ts`, `pnpm check`): subsections and paragraphs split back onto their own lines, amendment notes (`[Act No. … ]`) set apart, extraction spacing fixed (`( Cap. 245 )`), shouting case names title-cased, answer-key locators in words. Stored text is never changed (embeddings and citation offsets depend on it). Court quotes get spacing fixes only.
- **Check a filing** (`/check`): see below.

### Filing checker, slice 1 (`api/filing.py`, `POST /api/check`, `web/app/check/`)

Paste a filing; every citation in it comes back with evidence. Design and plan: `docs/superpowers/specs/2026-09-28-filing-checker-design.md`, `docs/superpowers/plans/2026-09-28-filing-checker-slice-1.md`.
- **Case** (neutral citations, `[2017] KESC 2 (KLR)`): `found`; `name_mismatch` (the case name before the citation shares no party with our title: a real number under someone else's name); `not_in_collection`. We hold about 10% of published judgments, so `not_in_collection` never means fake.
- **Quote** (8+ words, in the same paragraph as a cited case, given to the nearest citation): `verbatim` (words only: case, quote marks, dashes and spacing ignored; an ellipsis splits the quote into parts that must appear in order), `close` (difflib ratio ≥ 0.85 on the passage sharing the most 5-word runs; the court's words are shown), `not_found` (the nearest passage is shown if there is one), `not_checked` (judgment not held, PDF-only, or text unreachable). Paragraph numbers as in §7.
- **Section**: `extract_citations.extract` + `pick_provision`, then the status and the court's words from `api/status.py`; `not_covered` for laws we don't hold.
- **Judgment text** comes from `$LEXHACK_DATA` when the machine has it, else the same key in R2 (`R2_ENDPOINT` without the bucket name, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, optional `R2_BUCKET`; a read-only token). The API host (Railway) has no data folder, so it always reads R2; `scripts/sync.sh push` keeps the bucket current.
- Filings are not stored or logged; limit 200,000 characters (413). The web page posts through a server action, so CORS stays GET-only.
- **Demo filings** (synthetic, labelled as such): `web/public/demo/clean.txt`, `hallucinated.txt`, `stale_law.txt`.
- **Tests:** `uv run python -m api.test_filing` (pure checks, then the demo filings end to end against Neon); `cd web && pnpm check` for highlighting offsets (code points, not UTF-16).
- **Slice 2a (done 2026-09-28): eKLR citations and the benchmark.** Spec/plan: `docs/superpowers/specs/2026-09-28-filing-checker-2a-eklr-design.md`, `docs/superpowers/plans/2026-09-28-filing-checker-2a-eklr.md`.
  - `Name [YYYY] eKLR` gives only a year. `find_eklr` reads the case name and any case number between it and the citation; `rank_eklr` scores that year's judgments by shared party words weighted by rarity (IDF over all titles), over the better-covered side (our titles drop first names), with a floor (`MIN_SHARED`) and a minimum share of the filing's names (`MIN_CITED`); a matching case number scores 1. `decide`: `found` (clear winner), `possible_match` (up to 3 candidates), `not_in_collection`. A quote found word for word in exactly one candidate settles a possible match (`match_basis: quote`). Thresholds tuned on dev: `FOUND_SCORE 0.6`, `FOUND_MARGIN 0.4`, `POSSIBLE_SCORE 0.3`, `MIN_SHARED 2.0`, `MIN_CITED 0.5`.
  - **Benchmark** (`ground_truth/filing_*`): 80 judgments with 2+ eKLR citations (demo and mention-benchmark judgments excluded), split dev 40 (265 citations) / test 40 (224). `filing_sample.py` writes items, per-year title lists and batches; agent type `.claude/agents/citation-labeler.md`; two Sonnet labellers blind (agreement dev 247/265, test 207/224), an Opus tiebreaker on disagreements, then an Opus **audit of every `not_held`** with a better search brief (it found 9 + 7 held judgments the first labellers missed, mostly capitalised titles and dropped first names; an audit can only turn not_held into a judgment). Two gold items list alternatives (`a|b`): one ruling published twice; one appeal held only as the judges' separate opinions. `filing_merge.py` (refuses to write gold with an item missing or unsure), `eval_filing.py --set dev|test`, `--tune`, `--planted`.
  - **Test v1, scored once** (`filing_test_results.txt`, first matcher): found precision 71/77 (92%), wrong case 6/224 (2.7%), coverage 71/161 (44%). A fresh-eyes code review then found a single common surname could be "found" and that names/case numbers leaked across citations; the fixes (a single shared word must be rare, `SINGLE_MIN_IDF`; names and numbers stop at a sentence or citation; court/kind abbreviations before a case number are read; a unique case-number match settles a name tie) were re-tuned on dev only.
  - **Test2, the number to quote** (`filing_test2_results.txt`): a fresh held-out set of 40 judgments / 301 citations (`filing_sample.py test2`), labelled the same way (A/B agreement 280/301, Opus tiebreak on 21, Opus audit of all 89 not_held found 1 miss), scored once after the fixes: **found precision 132/139 (95.0%), wrong case 7/301 (2.3%), coverage 132/213 (62%)**, possible-match hit 9/12, false found on not-held 6/88. Wrong cases read after scoring: a shared institutional party alone (county government, tax commissioner, KRA), a shared first name, the same dispute in another court, one truncated name. Dev after the fixes: 110/114, 4/265, 110/175.
  - **Planted errors** (`filing_planted_results.txt`): wrong name caught 46/50 (control 50/50), altered quotes 69/70, invented numbers 30/30; false alarms 1/146 real neutral citations (an anonymised title: "Nyale" vs "RN").
- **Slice 2b (done 2026-09-29): upload.** `api/extract.py` + `POST /api/extract` (raw bytes, `X-Filename`; up to 10 MB; not stored): PDF via `pypdf` (pages joined by a blank line), DOCX via zipfile/XML (one paragraph per blank-line block, so quotes are attributed within a paragraph), UTF-8 text. A PDF where most pages carry no text is refused as a scan (no OCR); old `.doc`, encrypted PDFs and binaries get plain messages. The web page (`readFiling` server action; drop zone and "Upload PDF or DOCX" tab) fills the paper with what was read, so the reader sees it before checking; it takes files up to 4 MB (Vercel's ~4.5 MB function body cap; `next.config.ts` `serverActions.bodySizeLimit`). Tests: `uv run python -m api.test_upload` (PDF and DOCX fixtures built in the test). PDFs are read in `pypdf` layout mode (plain mode split Google Docs exports into one word per line) and ligatures become letters (`ﬁ` → `fi`, also in the quote matcher). **Scans:** pages without a text layer are read by OCR on our server (Tesseract, via `pypdfium2` page images; up to 30 pages); the result lists `ocr_pages`, and the page and the quote labels say an OCR slip can look like a misquote. Railway builds with **Railpack**: Tesseract comes from `railpack.json` (`deploy.aptPackages`, with `...` to keep the defaults); locally `brew install tesseract`.
- **Text for PDF-only judgments (2026-09-29):** `pipeline/fetch_sources.py fetch|parse`. Of the 286 judgments held only as an HTML shell, 157 had a source file in the Internet Archive (129 not archived); 22 were blank placeholder PDFs and 12 downloads were the Archive's own page (now rejected), leaving **123 judgments with text** (all from a real text layer; none needed OCR). `extract_citations --judgments` / `llm_resolve --judgments` (touch only those judgments): 2,454 mentions, 1,711 linked to our sections. Parsed JSON records `text_source` (file, capture, kind, `ocr_pages`); raw files in `$LEXHACK_DATA/raw/sources/`. 163 judgments still have no text.
- **Next (2c):** quotes away from their citation. Also: court words in the context ("the Court of Appeal held") as a matching signal, "estate"/"deceased" as generic words, anonymised titles (initials).
- **Tools for AI agents (MCP).** `api/tools.py` wraps the API in six read-only tools (`list_acts`, `search_sections`, `get_section`, `citing_judgments`, `find_case`, `check_text`); `api/mcp_server.py` serves them over MCP. Remote (deployed 2026-10-02): `https://api-production-0506.up.railway.app/mcp` (streamable HTTP, 60 requests a minute per IP). Local, for Claude Desktop (`claude_desktop_config.json`):

  ```json
  {"mcpServers": {"hakiki": {"command": "uv", "args": ["run", "--directory", "/path/to/Lexhack", "python", "-m", "api.mcp_server"]}}}
  ```

  Tests: `uv run python -m api.test_tools`, `uv run python -m api.test_mcp`.
- **Research agent** (`api/agent.py`, `gemini-3.5-flash-lite`). The model writes `[[section|event|judgment:ID]]` references and `render()` fills in the database text; references no tool returned are removed and counted. **Held-out, the number to quote** (`ground_truth/agent_questions_heldout.csv`, 30 questions, scored once at commit 1ae7f5d): 3 invented references in 30 answers (all removed before display); 3 model-written quotes; section found 21/26; key rulings 16/22; not-held wording 4/4; grader pass 30/30. The answer-grader (agent type `answer-grader`) first passed a planted benchmark: 10/10 faults caught, 0 false fails. An audit of the 4 close calls agreed with all 4 passes but found faults outside the grader's four: one false "not in Hakiki's collection" (h20, repealed Penal Code s.189, which search didn't surface), two answers that don't say a ruling was displaced (h16, h18), and one unverified ruling cited without its label (h18). The weak spot is case questions: 3 of 4 held-out case questions missed their section, because `find_case` now confirms only multi-word party-name matches. Dev (20 questions, used for tuning): 2 invented in 20 (13 before tuning); 0 model quotes; section found 16/17; key rulings 14/15; not-held 3/3; grader 20/20. The scorer changed in between (per-metric denominators; invented references earn no credit). Run: `uv run python -m ground_truth.eval_agent --set dev`; tests `api.test_agent`; `ground_truth.eval_agent --selftest`.
- **Research agent, round 2 (2026-10-02).** Fixes measured on a fresh held-out set: `find_section(act, section)` (the extractor's Act resolver; held Acts never reported as not held; duplicate or renumbered sections such as Law of Succession s.43 and Employment Act s.45 come back with every candidate), a single party word confirms a case only when exactly one held title has it (else `ambiguous`, ask the user), a full "X v Y" name breaks ties, and `render()` appends a cited ruling's state when it isn't in effect. The grader gained a fifth fault, `misattributes` (a displaced ruling as current, a wrong "checked by"); its new planted benchmark: 10/10 caught, 0 false fails. **Fresh held-out, the number to quote** (`ground_truth/agent_questions_heldout2.csv`, 30 questions, scored once at commit 5b34915): 1 invented reference in 30 answers (removed); 2 model-written quotes; section found 21/26; key rulings 15/22; not-held wording 4/4; grader 29/30 (n11 names the wrong Act for *Mbuti*). By kind: case questions found their section 4/6 (was 1/4), repealed 2/2 (was 1/2), advice 0/3 (the agent declines without looking the section up). The audit of the fail and 4 close calls found one false "not held" again, for a case: n14, *Wachira & 12 others v Republic* — the model added "[2022] eKLR", the eKLR matcher returned three unrelated one-word candidates and the exact-title match never ran. Prose still often omits that a ruling was displaced (the rendered label says it). Dev: 1 invented in 20; section 15/17; key rulings 13/15; not-held 3/3; grader 20/20. Run: `ground_truth.eval_agent --set heldout2` (already scored; write a fresh set after changes).
- **Research agent, round 3 (2026-10-04).** `find_case` now tries the party-name search when a citation isn't confirmed (the *Wachira* false "not held"), and confirms a title by one rule over the whole collection: the single held title with every party and span word, then (if several) starting with the name as written, then (if a year was given) of that year; a year that doesn't match is `year_mismatch`, never confirmed. Adversarial reviews found and closed four wrong-case routes on the way (*Otieno v Republic [2019]* → a 2008 case; *Peter Mwangi v Republic* → unrelated cases; *Okuta v Republic* → *Okuta v AG*; *Republic v Ibrahim* → *Republic v Ibrahim Busolo*). Rulings from `find_case` carry their Act and section; the prompt keeps case names as written and still looks the section up on advice questions. False "not held" is measured twice: a code count (`false_not_held`, an upper bound) and grader fault 6 (planted bench3: 10/10 caught, 0 false fails). **Third held-out set, the number to quote** (`ground_truth/agent_questions_heldout3.csv`, 30 questions, scored once at commit a9d9a7b): 6 invented references in 30 answers (all removed; 5 are one answer listing ambiguous *Lumbasi* candidates as references, which can't be referenced); 3 model-written quotes; section found 24/26; key rulings 18/22; not-held wording 4/4; **0 false not-held claims**; grader 30/30. Audit of the 3 closest calls agreed; prose still often calls displaced High Court rulings "reversed" or doesn't say they were displaced (the rendered label does). Dev: 1 invented; section 16/17; key rulings 13/15; 0 false not-held.
- **Ask Hakiki: chat and drafts (2026-10-06).** `POST /api/chat` (FastAPI) streams NDJSON: one `step` per lookup, then the answer as structured parts (text, ruling quoted verbatim from the database with its checker and state, section with status, case), then `done` with the disclaimer. Limits: 2,000-character questions, 6 earlier turns, 10 questions a minute per user (behind the web proxy, via `CHAT_PROXY_SECRET`, set on Railway and Vercel), 30 a minute and 4 at once overall, a 55 s deadline that also stops the agent when the reader leaves, 2 Gemini tries per call, tool errors passed to the model as their type only. `mode: "draft"` writes a short draft for an advocate's review, then checks it with the filing checker and gives the model one revision turn for anything it can fix: a case it typed that isn't held, a quote that doesn't match, a section relied on without its limiting ruling or repeal, a case the user named that couldn't be confirmed; quoted words with no case and sections of Acts Hakiki doesn't hold are reported, not revised. The answer carries every judged item (`flagged` first) and the label "Draft for an advocate's review…". The web page is `/ask` (Answer | Draft). Contract: `api/main.py` `ChatRequest` and the chat section of `web/lib/answer.ts`. Tests: `uv run python -m api.test_chat`. Not measured on a benchmark yet (the agent's held-out sets above measure answers, not drafts).
- Not built yet: the review queue for extracted events (needs a write endpoint).

## 8. Glossary

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
| **Mention** | One place a judgment cites a section (`citation_mentions`). Says nothing about what the court did to it; that is an *event* |
| **Bare mention** | A citation that doesn't name its law in the citation itself ("section 39", "the said section"). Left for the LLM pass |
| **Precision / recall** | Of what the extractor found, the share that is right / of what's really there, the share it found |

---

## 9. What's left, and blind spots

### Finish step 5

- **The LLM pass: done** (2026-09-27, §7.3).
- ~~Held-out sample~~ done (§7.4): precision 98.1%, recall 98.1% on unseen judgments.
- ~~Embeddings~~ done: all 4,592 section texts.

### Steps 6–9 (from `CLAUDE.md`)

6. **Event classification:** decide which mentions are actual rulings (struck down, read down, upheld…) → `citation_events` with `method = 'extracted'`. Score it against the 19 answer-key events and the 6 no-effect cases.
7. **Status resolver** (per-jurisdiction rules: reversals cancel earlier events; later Supreme Court precedent displaces a Court of Appeal read-down), then the API (FastAPI) and the UI (Next.js).
8. **Synthetic demo filings** (clearly labelled) and the filing checker: does the case exist, is the quote in it, is the section still good law.
9. **Deploy** end to end.

For the front end (step 7): the UI can start now against mock JSON shaped like the future API response, since the data shapes are fixed by `pipeline/schema.sql`. The API response shape isn't defined yet; defining it is the first shared task.

### Blind spots (noted during step 5)

- **Shared database, destructive re-runs.** Both teammates' `.env` point at the same Neon `production` branch. `extract_citations` deletes and rebuilds *every* mention row, and `llm_resolve` must then be re-run. Agree who runs pipeline steps, or give each person a Neon branch.
- **Caches are shared through R2** (§3, `scripts/sync.sh`). Pull before re-running an LLM step, or the calls are made (and paid for) again.
- **Neon storage:** 215 MB of ~512 MB. Step 6's events are small, but embedding *judgments* (for search over judgments) would not fit on the free plan.
- **Paragraph numbers (fixed 2026-09-27).** Detection now reads "1.", "[1]" and "1)" numbering, tolerates up to 2 missed "1." numbers, and rejects footnote and element lists (the "[n]"/"n)" styles must run strictly in order, have 5+ paragraphs and span half the judgment). It matches the hand-recorded paragraph for all 19 answer-key events (16/19 before). Applied in place with `extract_citations --paragraphs-only`, which keeps the LLM rows. 23% of mentions still have no paragraph, mostly because the judgment isn't numbered at all (older judgments especially).
- **Character offsets depend on the parsed text.** `char_start`/`char_end` index the stored JSON's `text`. If `crawler.parse` is re-run and the text changes, re-run extraction.
- **"section N of the Constitution" is always treated as the repealed Constitution.** The 2010 Constitution's Schedules do have sections (e.g. the Sixth Schedule's transitional provisions); those are misattributed.
- **Other laws' names are not normalised.** `act_ref` for Acts we don't hold is the name as written: "Retirement Benefits Authority Act", "CDF Act" and misspellings are separate values. Normalise before using them to choose which Acts to load next.
- **What the extractor ignores:** rules, orders and regulations ("Order 42 rule 6 of the Civil Procedure Rules"), and schedule paragraphs. The filing checker won't recognise those either.
- **Weaker spots not measured separately:** "the Act" resolved to the last named Act (confidence 0.6), and bare "Article N" → 2010 Constitution (~95% in a 40-mention spot check; treaty articles are the usual error).
- **Unresolved rows stay in the table.** Mentions the LLM called `not_a_citation` or `unknown` (5,186) are left with no law (the verdict is in the cache).
- **Database connections have no timeout (`pipeline/db.py`).** On a flaky network a connection can die silently and the worker hangs forever (it happened 4 times in the step-5 run). `llm_resolve` now opens its own connections with keepalives, a connect timeout and a 2-minute statement timeout; `classify_events` / `verify_events` still use `db.connect()` and can hang the same way. 366 citations name one of our Acts with a section number that doesn't exist there: typos, sections from versions we lack, or fake. Worth a look for the filing checker.
- **Windows needs `PYTHONUTF8=1`** (§3), because the code reads files without naming an encoding.
- **Free-tier Gemini:** Google may use free-tier prompts to improve its products. The judgments are public, so this is acceptable, but don't send anything private through the free key.

### Known gaps (not blocking)

- **Parliament's changes aren't events yet.** The Acts carry over 1,000 amendment notes ("[Act No. 7 of 2007, Sch.]"). Turning them into `amended_by_statute` / `repealed_by_statute` events belongs with step 6 or 7.
- **286 PDF-only judgments have no text** (1.7%). The Archive may hold some of their PDFs; fetching them is about 300 requests. None are in the answer key.
- **Coverage:** the Archive holds about 10% of Kenya's judgments, KICA has 2 of 13 versions, and 254 listed judgment pages were missing.
- **Employment Act IDs changed in 2022:** mentions are linked by decision date (§4.6); the API merges the two IDs of a renumbered section (§7c, status resolver rule 6).
- **Unchecked appeals:** *EG*, *Alai* and *Andama*. *Okuta* and *Andare*: no appeals found (absence unverified).

### Housekeeping

- **Before the presentation:** confirm the live Kenya Law pages still lack court notes (our evidence is from Archive snapshots).
- **Commit and push** the step 5 work so both machines have it.
- **Neon API key:** the one created during setup (`neon api-keys revoke 3363955`) can go if the Neon MCP server isn't used.
- **The bulk-request letter** (`letters/`) is unsent. It's optional now.
