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
EKLR = re.compile(r"\[(?P<year>\d{4})\]\s*eKLR")
CASE_NO = re.compile(r"(?:No\.?\s*)?\b(?P<num>[A-Z]?\d+[A-Z]?)\s+of\s+(?P<y>(?:19|20)\d{2})\b")
V_WORD = re.compile(r"\sv(?:s)?\.?\s")
WORD = re.compile(r"[^\W_]+")
V = {"v", "v.", "vs", "vs."}
GLUE = {"and", "another", "others", "of", "the", "&"}   # lowercase words that belong inside a case name
LEAD_IN = {"in", "see", "per", "also", "cf"}
# Words that don't tell cases apart: parties half of Kenya's cases share, and lead-in words.
NOT_A_PARTY = {"and", "another", "others", "the", "of", "in", "see", "per", "also", "held", "case", "matter", "court",
               "supreme", "appeal", "high", "republic", "attorney", "general", "state", "county", "government",
               "director", "public", "prosecutions", "dpp", "ors", "anor", "ltd", "limited", "kenya", "commission",
               "national", "ex", "parte", "re", "klr", "eklr", "ag", "petition", "civil", "criminal", "application",
               "suit", "cause", "misc", "miscellaneous", "hccc", "constitutional", "election", "judicial", "review",
               "succession", "reference", "no", "consolidated", "formerly", "number"}
# No opening mark inside and a length cap: an unclosed “ must not rescan the paragraph (quadratic on hostile input).
QUOTE = re.compile(r"[“\"]([^“”\"]{1,3000})[”\"]")
MIN_QUOTE_WORDS = 8
ELLIPSIS = re.compile(r"\.\s?\.\s?\.|…")
SHINGLE = 5    # words per shingle when locating a near-miss quote
CLOSE = 0.85   # difflib ratio at or above which a quote is "close" rather than "not found"
MAX_QUOTES = 200   # per request; the rest read "not checked" (each quote is matched against a whole judgment)


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
    return [{"raw_text": m.group(0), "char_start": m.start(), "char_end": m.end(), "form": "neutral",
             "citation": f"[{m['year']}] {m['court']} {m['num']} (KLR)", "cited_name": cited_name(text, m.start())}
            for m in NEUTRAL.finditer(text)]


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


@functools.lru_cache(maxsize=8)
def text_index(text):
    """(tokens, words, {5-word run: [positions]}, paragraph markers) of a judgment, built once for all its quotes."""
    doc = tokens(text)
    words = [w for w, _, _ in doc]
    index = collections.defaultdict(list)
    for j in range(len(words) - SHINGLE + 1):
        index[tuple(words[j:j + SHINGLE])].append(j)
    return doc, words, index, paragraph_markers(text)


def match_quote(quote, text):
    """Compare words only. An ellipsis splits the quote into parts that must appear in order. Failing that, the
    passage sharing the most 5-word runs with the quote is scored with difflib: close, or not found (the nearest
    passage is still returned so the reader can compare)."""
    doc, words, index, _ = text_index(text)
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
    votes = collections.Counter(j - k for k in range(len(flat) - SHINGLE + 1)
                                for j in index.get(tuple(flat[k:k + SHINGLE]), ()))
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
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT"], region_name="auto",
                        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                        # fail fast: an R2 outage should cost a few seconds of "not checked", not minutes
                        config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}))


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


def case_text(row, texts):
    """The text of a judgments row as selected in case_findings() (raw_path at 6, has_full_text at 7), or None if
    not held, PDF-only or unreachable. texts: this request's {raw_path: text or None}, so a failure is paid once."""
    if not row or not row[7]:
        return None
    if row[6] not in texts:
        try:
            texts[row[6]] = judgment_text(row[6])
        except Exception:   # R2 or disk unreachable: its quotes are unchecked, the rest of the report still stands
            log.warning("judgment text unavailable: %s", row[6])
            texts[row[6]] = None
    return texts[row[6]]


def quote_check(quote, text):
    out = {"quote": quote, "result": "not_checked", "similarity": None, "court_text": None, "paragraph": None}
    if text is None:
        return out
    m = match_quote(quote, text)
    para = paragraph_at(text_index(text)[3], m["char_start"]) if m["char_start"] is not None else None
    return {**out, "result": m["result"], "similarity": m["similarity"], "court_text": m["court_text"],
            "paragraph": para}


def case_findings(conn, text):
    cases = find_cases(text)
    held = {r[0]: r for r in conn.execute(
        """SELECT neutral_citation, judgment_id, title, court, decision_date::text, source_url, raw_path, has_full_text
           FROM judgments WHERE neutral_citation = ANY(%s) AND duplicate_of IS NULL""",
        ([c["citation"] for c in cases],))}
    quotes = find_quotes(text, cases)
    texts, budget, out = {}, MAX_QUOTES, []
    for i, c in enumerate(cases):
        row = held.get(c["citation"])
        result = ("not_in_collection" if not row else
                  "found" if names_agree(c["cited_name"], row[2]) else "name_mismatch")
        out.append({"kind": "case", "raw_text": c["raw_text"], "char_start": c["char_start"],
                    "char_end": c["char_end"], "section": None,
                    "case": {"result": result, "cited_name": c["cited_name"],
                             "judgment": dict(zip(JUDGMENT_COLS, row[:6])) if row else None},
                    "quotes": []})
        for q in quotes.get(i, []):
            out[-1]["quotes"].append(quote_check(q, case_text(row, texts) if budget > 0 else None))
            budget -= 1
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
