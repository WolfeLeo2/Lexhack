"""Filing checker: every citation in a pasted filing, with three checks and the evidence for each
(docs/superpowers/specs/2026-09-28-filing-checker-design.md).

  case     is the cited judgment in our collection, and is it the case the filing names?
  quote    do the quoted words appear in that judgment?
  section  what have courts done to the cited section (api.status)?

Reports what the sources say. "Not in our collection" never means "fake": we hold about 10% of published judgments.
"""
import collections
import difflib
import functools
import json
import logging
import os
import re
from datetime import date
from pathlib import Path

import crawler.config  # noqa: F401  (loads .env: LEXHACK_DATA, R2_*)
from pipeline.extract_citations import extract, paragraph_at, paragraph_markers, pick_provision, provision_lookup

from .status import provision_status

log = logging.getLogger(__name__)

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
QUOTE = re.compile(r"[“\"]([^”\"]+)[”\"]")
MIN_QUOTE_WORDS = 8
ELLIPSIS = re.compile(r"\.\s?\.\s?\.|…")
SHINGLE = 5    # words per shingle when locating a near-miss quote
CLOSE = 0.85   # difflib ratio at or above which a quote is "close" rather than "not found"


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


JUDGMENT_COLS = ("neutral_citation", "judgment_id", "title", "court", "decision_date", "source_url")


def quote_check(quote, row):
    """row: a judgments row as selected in case_findings() (raw_path at 6, has_full_text at 7), or None if not held."""
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
