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
