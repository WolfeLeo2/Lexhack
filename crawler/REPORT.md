# Pilot crawl report: new.kenyalaw.org

Date: 2026-09-23. Requests made: **1**. Result: **stopped at the first request.**

## 1. What happened

Following the hard constraints, robots.txt was the first request. It was sent with the declared User-Agent `LexHackResearchBot/0.1 (student research project; contact: iansmith@gmail.com)`, one connection, and no other traffic before it.

The response, as stored in `$LEXHACK_DATA/raw/kenyalaw-00000.warc.gz` and indexed in `frontier.db`:

```
HTTP/1.1 403 Forbidden
Server: nginx
Date: Wed, 23 Sep 2026 04:35:43 GMT
Content-Type: text/html
Content-Length: 146

<html><head><title>403 Forbidden</title></head>
<body><center><h1>403 Forbidden</h1></center><hr><center>nginx</center></body></html>
```

The constraints say a 403 means stop the crawl and report, so the crawler wrote `raw/STOPPED.txt` and exited.

A re-run fails from the stored record without sending a second request. I also did not:
- retry the request,
- change the User-Agent,
- test which User-Agents are allowed,
- use any other route.

Any of those would be probing or getting around an access control.

**Relevant prior observation.** This comes from the earlier Pocket Law session, before this task, and was **not** made by this crawler:
- A browser-UA `curl` of `kenyalaw.org/pocketlaw` got HTTP 200.
- An automated fetch tool got 403 on `new.kenyalaw.org/pocketlaw`.

Together with a bare nginx 403 on robots.txt itself, this is consistent with the site **filtering declared bots by User-Agent**. That reads as a deliberate decision by the operator, not a fault. I have not verified it, and it should not be worked around.

## 2. robots.txt and terms

- **robots.txt:** could not be read (403). So the Crawl-delay, disallow rules and sitemap location are **unknown**.
- **Terms of use / copyright page:** not fetched. robots.txt comes first by rule, and the site refused it.
- **From the earlier session only** (kenyalaw.org page footer, fetched manually on 2026-09-23, not archived by this crawler): "Except for some material which is expressly stated to be under a specified Creative Commons license, the contents of this website are in the public domain and free from any copyright restrictions."
  - So **reuse of the content looks permitted**. **Automated access**, however, is currently refused at the server.
  - Those are separate questions. Public-domain content does not give a right to crawl a server that refuses crawlers.

## 3. Site size, crawl time, storage

**Not measured.** Sitemaps and listing pagination could not be fetched. The figures below are **order-of-magnitude estimates** built from public statements and the South African Pocket Law ratios. Replace them with sitemap counts once access exists.

| Item | Basis | Estimate |
|---|---|---|
| Judgments | Kenya Law states "over 275,000 judicial decisions" | ~275k HTML pages |
| Judgment PDFs (`/source`) | Assumes the SA share of PDF-only pages (~54%) holds; many HTML pages also link a source file | ~150k–275k extra requests |
| Legislation | "over 500 chapters of the Laws of Kenya", plus subsidiary legislation and point-in-time versions (SA had ~2 pages per work) | ~5k–20k pages + PDFs |
| Gazettes | Kenya Gazette issues, weekly plus specials, decades back | ~10k–30k (unknown) |
| Listing pages | Pagination (page size unknown) | ~5k–10k |
| **Total requests** | | **~450k–600k** |

- **Crawl time:** at the 2 s minimum, one connection, ~500k requests is about **11–14 days** continuous. With a 5 s Crawl-delay it is about **29–35 days**. 429 backoff adds more.
- **Storage:** SA HTML averaged ~50 KB per page and gzipped about 3.4×, so ~300k HTML pages come to about 5 GB. PDFs barely compress: ~200k judgment PDFs at ~300 KB is about 60 GB, and gazette PDFs could add tens of GB. **Plan for ~80–150 GB.**

## 4. URL patterns, pagination, filtering

**Not confirmed.** These are the Peachjam hypotheses the scope files use:

| Kind | Hypothesised pattern |
|---|---|
| Act (version) | `/akn/ke/act/{year}/{number}/eng@{YYYY-MM-DD}` |
| Judgment | `/akn/ke/judgment/{court code, e.g. kehc}/{year}/{n}/eng@{date}` |
| Source file | `…/eng@{date}/source` (may redirect to `/media/…`; the fetcher records and follows redirects) |
| Gazette | `/akn/ke/officialGazette/…` or `/gazettes/{year}` |
| Listings | `/legislation/`, `/judgments/{COURT}/{year}/`, `?page=N` |

## 5. Step 3 structure questions

None of these can be answered from Kenyan data, because nothing was fetched. Each needs the pilot run.

- **data-eid on statutes:** not determined for Kenya. KICA s.29 and Penal Code ss.194/204 eIds are unknown.
- **Point-in-time versions:** not determined. No version dates found.
- **Editorial notes on KICA s.29 / Penal Code ss.194, 204:** not determined. I can't say whether they exist.
- **Remark counts and court mentions:** not determined.
- **Judgment metadata null rates (63 judgments):** not determined.
- **HTML vs PDF-only by era:** not determined.
- **Operative orders of Andare, Okuta, Muruatetu:** not retrieved. No quotes can be given.
- **Machine-readable legislation links in judgments:** not determined.

**What was verified offline.** The parser was run against real Peachjam pages saved from the South African Pocket Law inspection (same platform). On the SA Constitution it extracted:
- 287 `akn-section` eIds (e.g. `chp_1__sec_1`),
- 93 `akn-remark` spans,
- 20 version dates,
- the source URL.

On SA judgments it read the `<dl class="document-metadata-list">` fields (Citation, Media Neutral Citation, Case number, Court, Judges, Date) and `data-display-type="html"` vs `"pdf"`. So once access exists, Step 3 is one `crawl run` plus one `parse` away.

## 6. What was built

All of it is in `crawler/`; see README.md.
- `crawl.py` CLI with run, add, status and requeue.
- SQLite frontier with the full specified schema, plus a WARC `records` index. Every write is committed immediately, so the crawl is resumable.
- Fetcher:
  - robots.txt first, with Crawl-delay and Request-rate respected,
  - ≥2 s spacing on a single connection,
  - Retry-After or exponential backoff from 60 s on 429/503,
  - conditional GETs,
  - manual redirects, so every hop is archived and fetched once,
  - hard stop on 401/403, login redirect or challenge,
  - pid lock file.
- warcio storage: gzip per record, rotation at ~1 GB, PDFs included.
- Offline parser.
- Scope files: `scope.pilot.yaml` (active via the `scope.yaml` symlink) and the draft `scope.full.yaml`.
- `test_offline.py`: a self-check with faked HTTP covering robots and Crawl-delay, the same-work follow rules, redirects, 429 backoff, the 403 stop, no double fetches, the WARC round trip, parsing and the lock. It passes, and it caught two real bugs (FRBR work extraction; a document's own version date) that are now fixed.
- Reuse note: no `warc.py` existed in this repo. The Pocket Law reader's idea (seek to an indexed offset, decompress one gzip member) is kept in `storage.read_record`, now via warcio.

## 7. Recommendation

**A full mirror is not feasible under these constraints right now.** The site refuses the declared research crawler at robots.txt, and the constraints rightly forbid getting around that.

The content looks public domain, so this is an access question, not a copyright one. It is worth asking:
1. **Email Kenya Law** (National Council for Law Reporting) through its contact page. Describe the project, send the exact User-Agent string and planned rate (1 request every ≥2 s), and ask to be allowlisted or offered a bulk export or dump. Laws.Africa's own terms for its sister site already point bulk users to email.
2. **Ask Laws.Africa,** who build and host Peachjam, about data access for Kenya. Their content API needs an account and agreement.
3. If allowlisted, run it in this order:
   1. `rm $LEXHACK_DATA/raw/STOPPED.txt`
   2. `uv run python -m crawler.crawl retry https://new.kenyalaw.org/robots.txt`
   3. the unchanged pilot
   4. fill in Sections 2–5 from real data
   5. tighten `scope.full.yaml` from the real sitemap and listing URLs
   6. only then run the full crawl

**What `scope.full.yaml` should look like:**
- Seed from sitemap children rather than paginating listings, if the sitemaps are complete.
- Follow `listing → listing/act/judgment/gazette`, `act → act/source` within the same work, and `judgment/gazette → source`.
- Exclude search, facet and filter query strings.
- Use `min_delay` ≥ the robots Crawl-delay.
- Set `max_requests` around 1M as a safety cap.
- After the first pass, keep it current with weekly `requeue --kind listing` runs, which are conditional GETs.

## 8. Alternative sources (follow-up, 2026-09-23)

### Hugging Face `endomorphosis/ipfs_kenya_laws`
Downloaded to `$LEXHACK_DATA/external/hf_ipfs_kenya_laws/` (4.6 MB, parquet + the collector scripts).

**Contents**
- 261 principal Acts plus the Constitution, as of snapshot 2026-09-10. Scraped live from new.kenyalaw.org; the manifest says `retrieval: live-official-html`.
- **Current version only.** No point-in-time history.
- **Plain text only.** No HTML, no `data-eid`, no `akn-remark` markup, so editorial notes can't be told apart from statute text.
- `laws`: one row per Act (id, title, text, source_url, date, Cap. number, section count, licence).
- `articles`: 9,802 section rows (section number, heading, text).
- 120 of 261 Acts have 0 sections. At least some of those rows are only the "Loading PDF…" placeholder, i.e. PDF-only pages with no text.

**Target Acts**
- Employment Act (2024-04-26 version, 100 sections): present.
- **Penal Code (Cap. 63): absent.**
- **KICA (Cap. 411A): absent.**
- No judgments and no gazettes.

**Verdict:** can be used as a supplementary source for current principal-Act text; the content itself is public domain per Kenya Law. It does **not** answer any Step 3 question.

**Provenance note.** The collector (`scrapers/common.py`, `collect_ke.py`) fetched new.kenyalaw.org directly around 2026-09-03 as `legal-corpora-collector/1.0 (research archive …)`. It recorded the site's robots.txt as `Allow: /`, `Disallow: /search/ /api/`, `Crawl-delay: 5`. So automated access with a descriptive UA *was* served three weeks ago. Our 403 therefore looks specific to our request (UA string or IP), not a site-wide ban on research crawling. That strengthens the case for simply asking Kenya Law to allowlist `LexHackResearchBot`. It is not a reason to change our UA to get past the filter.

### Internet Archive (Wayback Machine)
The CDX index (queried ad hoc, not yet via the crawler) lists:
- about 27,400 unique judgment pages (kehc 11k, keca 5.6k, keelc 3.4k, keelrc 3.2k, kesc 629, …),
- about 6,600 Act pages plus 907 `/source.pdf` files,
- **all three target Acts:**
  - Penal Code `/akn/ke/act/1930/10`: 2014-12-22, 2022-12-31, 2023-12-11, plus PDFs,
  - KICA `/akn/ke/act/1998/2`: 1998-11-09, 2022-12-31,
  - Employment Act `/akn/ke/act/2007/11`: 8 versions.

That confirms two URL facts: the Penal Code is Act 10 of 1930, and source files are served at `…/source.pdf`.

The crawler now has a Wayback mode (`crawler/wayback.py`, `scope.wayback-pilot.yaml`). How it works:
- It seeds from CDX captures and fetches `web.archive.org/web/<ts>id_/<original>`, which returns the unmodified archived bytes.
- It obeys IA's robots.txt (404, so allow-all) and kenyalaw's *archived* robots.txt.
- It runs at 5 s per request and stores everything in the same WARC files, with the original URL kept for parsing.
- It never contacts new.kenyalaw.org.

**It has not been run yet.** The session's permission check blocked the launch, pending the user's decision.

## 9. User-agent test, the actual terms, and API options (2026-09-23)

### User-agent test
With the user's authorisation I retried robots.txt with an honest agent name that drops only the word "Bot": `LexHack-research/0.1 (student research project; contact: …)`. robots.txt and `/terms-of-use/` both returned **200**. The earlier 403 was therefore a filter on the User-Agent string. That was 2 requests in total, stored in the WARC. Saved copies: `crawler/evidence_robots.txt`, `crawler/evidence_terms.txt`.

### robots.txt
- `User-agent: *`: Allow /, Disallow /search/ and /api/, plus six specific documents. **`Crawl-delay: 5`.**
- Fully blocked user-agents: AhrefsBot, Amazonbot, anthropic-ai, Applebot-Extended, ChatGPT-User, ClaudeBot, Claude-Web, cohere-ai, Google-Extended, GPTBot, ImagesiftBot, meta-externalagent, SemrushBot.

### Terms of use: crawling is prohibited
Verbatim:
- "**Scraping and bulk downloading from this website is strictly prohibited.** We are a donor-funded organisation and bulk and frequent scraping affects our costs, endangering the sustainability of the service. There are more efficient ways of obtaining access to our data in bulk. Please email us if you would like to access our data in bulk." (contact: info@kenyalaw.org)
- "You may access the Kenya Law service through the website, or access the data through our APIs."
- Licence: "Creative Commons Attribution-NonCommercial 4.0 … you may freely use, re-use and redistribute works from Kenya Law provided you credit Kenya Law as your source and your use is not for commercial gain." Some collections, including national caselaw and gazettes, may be more permissive. This conflicts with the site footer's "public domain" line. **Treat CC BY-NC 4.0 as binding.**

**Consequence:** the brief says "If the terms prohibit crawling, stop and report." So there will be **no direct crawl of new.kenyalaw.org, pilot or full, whatever the User-Agent.** The earlier "not feasible" verdict now rests on the terms, not on the 403.

### Laws.Africa API
Sources: developers.laws.africa pricing page, OpenAPI schema.

**Content API**
- Legislation only: works and expressions, points in time, `/timeline`, `/diff`, `/toc`, `/provision-enrichments` keyed by eId, in AKN XML, HTML, JSON or PDF.
- **No judgments or gazettes.**
- Full per-country access is on the Scale plan or above: "optional full Legislation Content API access starting at ZAR 42,000 per country per month, billed annually". The free tier's Content API covers only Cape Town by-laws.

**Knowledge Bases**
- Legislation and judgments, meant for RAG.
- Sandbox is free: one country, 100 calls per day.
- For judgments they return "summaries and metadata. They do not return the full original judgment text."

**Fit for this project**
- Good for exploring legislation structure and enrichments.
- Too expensive for a full Kenyan legislation corpus.
- **Unusable as a judgment corpus.**

### Recommendation (updated)
The terms name the legitimate route: **email info@kenyalaw.org for bulk access.** Describe the project, the non-commercial research purpose and the CC BY-NC attribution, and ask for a data export or API access. Ask Laws.Africa in parallel about academic or research terms, since Enterprise pricing is "custom".

## 10. Wayback pilot results (Step 3 answered from archived Kenya Law pages)

**How it ran**
- 126 requests to web.archive.org only, at 5 s spacing; **0 to new.kenyalaw.org**. Kenya Law's robots.txt as archived on 2026-05-01 was obeyed.
- Retrieved: 17 Act pages, 73 judgments, 11 source PDFs.
- Not in the archive, so recorded as gaps rather than fetched: 25 Act versions and 91 source files.
- One sampled judgment returned 404 from the archive (`keic/2003/26`).
- A local DNS outage mid-run exposed a bug: network errors used up per-URL retries. It is fixed (network errors now pause the whole crawl) and the run was resumed.
- Full generated tables: `$LEXHACK_DATA/parsed/analysis.md`.

**Sample:** the 3 named judgments, 11 other date-matched candidates, and 60 sampled judgments (20 pre-2005, 20 from 2010–2015, 20 from 2022+, spread across courts), minus the one 404.

### Hypotheses from the South African inspection: all confirmed for Kenya
- **Section eIds:** statutes are Akoma Ntoso HTML (`data-display-type="akn"`) with `data-eid` on every provision.
  - KICA s.29: **`part_III__sec_29`**
  - Penal Code s.194: **`part_II__chp_XVIII__sec_194`**
  - Penal Code s.204: **`part_II__chp_XVIII__subpart_nn_1__sec_204`**
  - These are stable across all fetched versions. Verbatim s.204 (2023-12-11):
    `<section class="akn-section" data-eid="part_II__chp_XVIII__subpart_nn_1__sec_204" id="part_II__chp_XVIII__subpart_nn_1__sec_204"><h3>204. Punishment of murder</h3><span class="akn-content"><span class="akn-p" data-eid="part_II__chp_XVIII__subpart_nn_1__sec_204__p_1" …>Any person convicted of murder shall be sentenced to death.</span></span></section>`
- **Point-in-time versions** appear in URLs as `eng@YYYY-MM-DD`, and every page lists all of them.
  - KICA: 13 versions (1998-11-09 → 2022-12-31); 2 fetched.
  - Penal Code: 3 versions (2014-12-22, 2022-12-31, 2023-12-11); all 3 fetched.
  - Employment Act: 13 versions (2007-11-09 → 2024-04-26); 11 fetched.
- **Source PDFs** live at `…/eng@date/source.pdf`.

### Editorial notes on judicial declarations: none
- KICA s.29, Penal Code s.194 and Penal Code s.204 carry **no `akn-remark` or other annotation in any fetched version**. That includes the Penal Code versions of 2022-12-31 and 2023-12-11, five-plus years after Okuta and Muruatetu.
- Across all 16 statute pages there are **1,038 `akn-remark` spans, and 0 mention a court, petition, unconstitutionality, a declaration, invalidity, a judgment or eKLR**. They are all amendment history, e.g. "[Act No. … s. …]".
- No Act page mentions Andare, Okuta or Muruatetu anywhere.
- Each page has an empty `content-and-enrichments` gutter, and no page component was found that would fill it. Annotations loaded live by JavaScript therefore can't be fully ruled out, but **none is present in the served HTML**.
- **Note: the statute text as published still reads as if these provisions were fully in force.**

### Judgment metadata
Source: `<dl class="document-metadata-list">`, 73 judgments.

| field | null/empty |
|---|---|
| Citation, Media Neutral Citation, Court, Case number, Judgment date | 0% |
| Judges | 30% |
| Parties | 100%: no field; parties appear only in the title |
| Legislation cited / Cases cited | 100%: no fields |

Also seen: Court station, Alternative citations, Outcome (36 of 73), Attorneys (18 of 73), Original source file.

### Text format by era
**71 of 73 judgments have full HTML text.** Pre-2005, 2010–2015 and 2016–2021 are all 100% HTML; 2022+ is 18/20 (2 are PDF-only). This is much better than South Africa's ~46%.

### Links to legislation
- 25 of 73 judgments have at least one `/akn/ke/act/…` link, all at **whole-Act level. None link to a provision** (no `#sec_…`).
- Links are auto-inserted and inconsistent:
  - **Muruatetu** has 112 links (77 to Acts) but **none to the Penal Code**, the Act it rules on.
  - **Andare** and **Okuta** have no links at all.
- Citation extraction for this research has to come from the judgment text, not the links.

### Operative orders (verbatim, all from HTML text; source PDFs not archived)

**Andare v AG** (Petition 149 of 2015) [2016] KEHC 7592 (KLR), 19 April 2016, Mumbi Ngugi J:
> "Consequently, the orders that commend themselves to me are as follows: a. I declare that section 29 of the Kenya Information and Communication Act is unconstitutional; b. I direct each party to bear its own costs of the petition."

**Jacqueline Okuta & another v AG & 2 others** [2017] KEHC 8382 (KLR), 6 February 2017, Mativo J:
> "Consequently, I allow this petition and enter judgement as prayed in the petition in terms of the following declarations:- i. A declaration be and is hereby issued that section 194 of the Penal Code, cap 63, Laws of Kenya is unconstitutional and invalid to the extent that it covers offences other than those contemplated under Article 33 (2) (a)- (d ) of the Constitution of Kenya 2010; and . ii. A declaration be and is hereby issued that any continued enforcement of Section 194 of the Penal Code, Cap 63, Laws of Kenya by the Second Respondent against the petitioners herein would be unconstitutional and/or a violation of their fundamental right to the freedom of expression guaranteed under article 33 (1) (a)-(c) of the constitution of Kenya 2010. Orders accordingly"

**Muruatetu & another v Republic** (Petitions 15 & 16 of 2015) [2017] KESC 2 (KLR), 14 December 2017:
> "a) The mandatory nature of the death sentence as provided for under section 204 of the Penal Code is hereby declared unconstitutional. For the avoidance of doubt, this order does not disturb the validity of the death sentence as contemplated under article 26(3) of the Constitution ."

The same order continues with (b) remittal to the High Court for re-sentencing, (c) a review framework with a 12-month report, and (d) placing the judgment before Parliament, the Attorney-General and the Kenya Law Reform Commission.

### What this means for a full mirror
- The archive holds about 10% of judgments, and many versions and PDFs are missing. **It is a good sample, not a mirror.**
- The structure is exactly what the crawler and parser expect, so any bulk data Kenya Law provides (see `letters/kenyalaw_bulk_request.md`) can feed this parser unchanged if it is page HTML. If it arrives as AKN XML, only a small reader needs adding.
