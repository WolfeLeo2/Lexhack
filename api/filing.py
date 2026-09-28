"""Filing checker: every citation in a pasted filing, with three checks and the evidence for each
(docs/superpowers/specs/2026-09-28-filing-checker-design.md).

  case     is the cited judgment in our collection, and is it the case the filing names?
  quote    do the quoted words appear in that judgment?
  section  what have courts done to the cited section (api.status)?

Reports what the sources say. "Not in our collection" never means "fake": we hold about 10% of published judgments.
"""
import collections
import difflib
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
