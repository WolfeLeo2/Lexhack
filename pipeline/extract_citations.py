"""Regex citation extraction: every "section N of the X Act" / "Article N of the Constitution" in the
judgment texts -> citation_mentions (method='regex'). Offline apart from the database; re-running replaces
all regex and LLM rows (then re-run pipeline.llm_resolve, which re-applies its cached answers for free).

  uv run python -m pipeline.extract_citations            # all judgments with text
  uv run python -m pipeline.extract_citations --dry-run  # extract + report, write nothing
  uv run python -m pipeline.extract_citations --paragraphs-only  # recompute `paragraph` in place; keeps LLM rows

Every Act is recorded (act_ref), not only the 8 we hold; provision_id is set only when the mention resolves
to a section in `provisions`. char_start/char_end index into the parsed JSON's "text" field as stored.

Confidence is about the *resolution* (which Act), not whether a citation exists:
  0.95 Act named in full / 0.9 acronym or Cap number / 0.85 bare Article -> Constitution of Kenya 2010
  0.6  "the Act"/"the Code" -> the last Act or Code named earlier in the same judgment
  0.0  unresolved: a bare "section N" (left for the LLM pass) or "the Act" with nothing named before it
"""
import argparse
import bisect
import collections
import json
import re
from datetime import date

from crawler.config import data_dir

from .db import apply_schema, connect

# --- Acts we hold: canonical name -> act slug. Keys are lower-case, whitespace-normalised. -------------
ALIASES = {
    "penal code": "cap-63",
    "sexual offences act": "cap-63a", "sexual offences act, 2006": "cap-63a", "soa": "cap-63a",
    "kenya information and communications act": "cap-411a", "kenya information and communication act": "cap-411a",
    "information and communications act": "cap-411a", "information and communication act": "cap-411a",
    "kica": "cap-411a",
    "criminal procedure code": "cap-75", "cpc": "cap-75",
    "civil procedure act": "cap-21", "cpa": "cap-21",
    "evidence act": "cap-80",
    "employment act": "cap-226", "employment act, 2007": "cap-226",
    "constitution": "constitution", "constitution of kenya": "constitution", "constitution of kenya, 2010": "constitution",
    "kenyan constitution": "constitution",
}
CAPS = {"160": "cap-160", "63": "cap-63", "63a": "cap-63a", "411a": "cap-411a", "75": "cap-75", "21": "cap-21", "80": "cap-80",
        "226": "cap-226"}
# Acts matched on the WHOLE name only: suffix matching would read "National Assembly and Presidential Elections Act"
# as the Elections Act and "Indian Succession Act" as the Law of Succession Act.
EXACT_ALIASES = {"elections act": "cap-7", "elections act, 2011": "cap-7", "elections act 2011": "cap-7",
                 "law of succession act": "cap-160", "laws of succession act": "cap-160", "succession act": "cap-160"}
COMMENCEMENT = {"cap-7": date(2011, 8, 27), "cap-160": date(1981, 7, 1)}   # before these, the name meant an older law
CANONICAL = {"cap-7": "Elections Act", "cap-160": "Law of Succession Act", "cap-63": "Penal Code", "cap-63a": "Sexual Offences Act", "cap-411a": "Kenya Information and Communications Act",
             "cap-75": "Criminal Procedure Code", "cap-21": "Civil Procedure Act", "cap-80": "Evidence Act",
             "cap-226": "Employment Act", "constitution": "Constitution of Kenya"}
REPEALED_CONSTITUTION = "Constitution (repealed)"
CONSTITUTION_2010 = date(2010, 8, 27)
EMPLOYMENT_EID_CHANGE = date(2022, 12, 31)   # Employment Act eIds gained a part_ prefix at this revision

# --- Grammar -----------------------------------------------------------------------------------------
# (?<![\w.-]): not inside a word, "sub-section", or "U.S. 288" (US Reports)
HEAD = r"(?<![\w.-])(?:[Ss]ections?|SECTIONS?|[Ss]ecs?\.|[Ss]{1,2}\.|[Aa]rticles?|ARTICLES?|[Aa]rts?\.)\s*"
SUB = r"\s?\(\s?[0-9a-zA-Z]{1,4}\s?\)"
# sub-provisions, including joined ones: "165 (6) & (7)", "259(1)(a) and (d)"
NUM = rf"\d{{1,3}}[A-Z]{{0,2}}(?:{SUB})*(?:\s*(?:&|and|,)\s*(?:{SUB})+)*"
# ";" separates items in Kenya Law's headnote lists: "articles 38(3)(c); 75; 87"
SEP = (r"\s*(?:,\s*(?:and\s+|or\s+)?|;\s*|and/or\s+|and\s+|or\s+|&\s*|to\s+|[-–—]\s*"
       r"|(?:as\s+)?read\s+(?:together\s+)?with\s+)")
# A list continuation must end the list (punctuation or a connector), so "section 4 and 5 witnesses" stops at 4.
ENDS = r"(?=\s*(?:[,;:.)\]\"”’–—-]|of\b|and\b|or\b|to\b|&|as\b|read with|under\b|in the\b|$))"
# "Article 768 of Section 9 of Halsbury's": an Article "of" something that isn't a Constitution
OF_OTHER = re.compile(r",?\s*of\s+(?!(?:(?:the|our|this|that|said|same|Kenyan?)\s+)*(?:[Cc]onstitution|CONSTITUTION))\S")
TOKEN = r"(?!(?:Act|Code|Constitution)\b)[A-Z][\w'’&-]*"
ACT_NAME = (rf"(?:{TOKEN}\s+(?:(?:{TOKEN}|of|and|for|on|to|in|the|&)\s+){{0,11}}?)?"
            r"(?:Act|Code|Constitution|Rules|Regulations|Ordinance"
            rf"|(?:Charter|Covenant|Convention)(?:\s+(?:on|of|for|against)\s+(?:the\s+)?{TOKEN}(?:\s+(?:and\s+)?{TOKEN})*)?)\b")
# An Act named anywhere in the text (not only inside a citation), for resolving a later "the Act" / "the Code".
NAMED_ACT = re.compile(rf"\b{TOKEN}\s+(?:(?:{TOKEN}|of|and|for|on|to|in|the|&)\s+){{0,11}}?(?:Act|Code)\b")
ACT = (rf"(?:(?P<cap>Cap\.?\s*(?P<capno>\d{{1,4}}[A-Z]?)\b)"
       rf"|(?P<old>former|repealed|old|retired|previous|1963|[Ii]ndependence|Lancaster)\s+Constitution\b"
       rf"|(?P<name>{ACT_NAME})"
       rf"|(?P<acro>[A-Z]{{2,6}})\b)")
CONN = r"(?:,?\s*(?:of|under|in)\s+(?:the\s+)?(?:said\s+|same\s+)?)"
# Act named first, as in Kenya Law's headnote legislation lists: "Elections Act (Cap 7), sections 34(6B), 35"
PRE = (rf"(?:(?P<pre>{ACT_NAME})(?:\s+of\s+Kenya)?(?:,?\s*\d{{4}})?(?:\s*\([^()]{{1,40}}\))*,?\s+)")
CITATION = re.compile(
    rf"{PRE}?(?P<head>{HEAD})(?P<list>{NUM}(?:{SEP}(?:{HEAD})?{NUM}{ENDS})*)(?:{CONN}{ACT})?")
ITEM = re.compile(rf"(?P<head>{HEAD})?(?P<num>{NUM})")
ACT_GROUPS = ("old", "cap", "capno", "acro", "name", "pre")
# Paragraph numbering styles: "1. The", "[1] The", "1) The". One style per judgment (see paragraph_markers).
PARA_STYLES = {
    "dot": re.compile(r"(?:^|(?<=\s))(\d{1,3})\.\s+(?=[A-Z\"“‘(])"),
    "bracket": re.compile(r"(?:^|(?<=\s))\[(\d{1,3})\]\s+(?=[A-Z\"“‘(])"),
    "paren": re.compile(r"(?:^|(?<=\s))(\d{1,3})\)\s+(?=[A-Z\"“‘(])"),
}
MIN_ALT_MARKERS = 5   # "[n]" / "n)" also number prayer lists ("1) Spent 2) An order"); a real scheme runs longer
MIN_ALT_SPAN = 0.5    # ... and runs through the judgment; footnote lists and element lists sit in one stretch
MAX_GAP = 2           # "dot" style only: a paragraph the pattern misses ("40. the …", a dropped "20.") mustn't end the sequence


def norm_ref(s):
    return re.sub(r"\s+", "", s)


def canonical(name):
    """Act name as written -> (act_ref, act slug or None)."""
    name = re.sub(r"\s+", " ", name).strip()
    if name.lower() in EXACT_ALIASES:
        slug = EXACT_ALIASES[name.lower()]
        return CANONICAL[slug], slug
    words = name.split(" ")
    for i in range(len(words)):   # "Statutes Penal Code" (a heading word run into the name) -> "Penal Code"
        slug = ALIASES.get(" ".join(words[i:]).lower())
        if slug:
            return CANONICAL[slug], slug
    return name, None


def paragraph_markers(text):
    """(offset, number) of paragraph numbers, accepting only the sequence 1, 2, 3... (skipping at most MAX_GAP missed
    numbers) so that a sentence ending "...section 204. The court" isn't taken for paragraph 204. Each style is tried; the longest sequence wins,
    "dot" on ties, and the other styles only with at least MIN_ALT_MARKERS paragraphs."""
    best = []
    for style, pattern in PARA_STYLES.items():
        out, want = [], 1
        for m in pattern.finditer(text):
            n = int(m.group(1))
            gap = MAX_GAP if out and style == "dot" else 0   # "[n]" gaps are usually footnote references
            if want <= n <= want + gap:
                out.append((m.start(), n))
                want = n + 1
        spans = bool(out) and out[-1][0] - out[0][0] >= MIN_ALT_SPAN * len(text)
        if len(out) > len(best) and (style == "dot" or (len(out) >= MIN_ALT_MARKERS and spans)):
            best = out
    return best


def paragraph_at(markers, offset):
    """The paragraph number in force at a character offset, or None before the first marker."""
    i = bisect.bisect_right([o for o, _ in markers], offset)
    return str(markers[i - 1][1]) if i else None


def is_article_head(head):
    return head.strip().lower().startswith("art")


def list_items(list_text, first_is_article):
    """-> [(number as cited, is_article)]. An item without its own head takes the previous item's kind."""
    items, kind = [], first_is_article
    for m in ITEM.finditer(list_text):
        if m.group("head"):
            kind = is_article_head(m.group("head"))
        items.append((m.group("num"), kind))
    # expand plain numeric ranges written with "to" or a dash: "sections 3 to 7" -> 3..7
    rng = re.fullmatch(rf"\s*(\d{{1,3}})\s*(?:to|[-–—])\s*(?:{HEAD})?(\d{{1,3}})\s*", list_text)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        if a < b <= a + 20:
            return [(str(n), first_is_article) for n in range(a, b + 1)]
    return items


def extract(text, decision_date=None):
    """Yield one dict per cited section. Pure function of the text, for tests and the eval."""
    # (offset, act_ref, act slug or None) of every Act/Code named in the text, for "the Act"/"the Code"
    names = []
    for n in NAMED_ACT.finditer(text):
        name = re.split(r"\b[Tt]he\s+", n.group(0))[-1]   # "Under the Employment Act" -> "Employment Act"
        if name not in ("Act", "Code"):
            names.append((n.start(), *canonical(name)))
    paras = paragraph_markers(text)
    pi = 0
    for m in CITATION.finditer(text):
        while pi < len(paras) and paras[pi][0] <= m.start():
            pi += 1
        para = str(paras[pi - 1][1]) if pi else None
        named = [(ref, slug) for off, ref, slug in names if off < m.start()]
        items = list_items(m.group("list"), is_article_head(m.group("head")))
        groups = {k: m.group(k) for k in ACT_GROUPS}
        # In a mixed list the named law belongs to the items of the kind next to it: in "article 178(1) as read
        # with section 21(1) of the Elections Act", Article 178(1) is not of the Elections Act.
        act_kind = items[-1][1]
        for num, kind in items:
            own = kind == act_kind
            act_ref, act_id, conf = resolve(groups if own else {}, kind, decision_date, named,
                                            text[m.end():m.end() + 80] if own else "")
            yield {"raw_text": m.group(0).strip(), "char_start": m.start(), "char_end": m.end(), "paragraph": para,
                   "section_ref": norm_ref(num), "act_ref": act_ref, "act_id": act_id, "confidence": conf}


def resolve(g, is_article, decision_date, named, tail):
    """g: the matched Act groups ({} = no Act named). tail: the text right after the citation.
    -> (act_ref, act slug or None, confidence)."""
    g = {k: g.get(k) for k in ACT_GROUPS}
    if g["old"]:
        return REPEALED_CONSTITUTION, None, 0.95
    if g["cap"]:
        slug = CAPS.get(g["capno"].lower())
        return (CANONICAL[slug], slug, 0.9) if slug else (f"Cap {g['capno']}", None, 0.9)
    if g["acro"]:
        slug = ALIASES.get(g["acro"].lower())
        return (CANONICAL[slug], slug, 0.9) if slug else (g["acro"], None, 0.5)
    if g["name"] or g["pre"]:
        name = re.sub(r"\s+", " ", g["name"] or g["pre"]).strip()
        name = re.split(r"\b[Tt]he\s+", name)[-1]
        if name in ("Act", "Code"):   # anaphora: the last Act (or Code) named before this point
            for ref, slug in reversed(named):
                if ref.endswith(name):
                    return ref, slug, 0.6
            return f"the {name}", None, 0.0
        if canonical(name)[1] == "constitution" and not is_article:
            # the 2010 Constitution has Articles; "section N of the Constitution" is the repealed one
            return REPEALED_CONSTITUTION, None, 0.8
        return (*canonical(name), 0.95)
    # no Act named
    if is_article:
        if (decision_date and decision_date < CONSTITUTION_2010) or OF_OTHER.match(tail):
            return None, None, 0.0
        return CANONICAL["constitution"], "constitution", 0.85
    return None, None, 0.0


def provision_lookup(conn):
    lookup = collections.defaultdict(list)
    for pid, act_id, eid, number in conn.execute("SELECT provision_id, act_id, eid, number FROM provisions"):
        lookup[(act_id.removeprefix("ke/act/"), number)].append((eid, pid))
    return lookup


def pick_provision(lookup, slug, section_ref, decision_date):
    if slug in COMMENCEMENT and decision_date is not None and decision_date < COMMENCEMENT[slug]:
        return None   # e.g. "Elections Act" in a 2008 judgment is the Act the 2011 one replaced
    number = re.match(r"\d+[A-Z]{0,2}", section_ref).group(0)
    cands = lookup.get((slug, number), [])
    if len(cands) > 1 and slug == "cap-226":   # Employment Act: eId scheme changed at the 2022-12-31 revision
        new = decision_date is not None and decision_date >= EMPLOYMENT_EID_CHANGE
        cands = [c for c in cands if c[0].startswith("part_") == new] or cands
    return cands[0][1] if len(cands) == 1 else None


def relink():
    """Link stored mentions to Acts loaded since they were extracted (act_ref names the law, provision_id is NULL),
    in place: nothing is deleted, so LLM-resolved rows keep their method and confidence."""
    with connect() as conn:
        lookup = provision_lookup(conn)
        rows = conn.execute("""SELECT m.mention_id, m.act_ref, m.section_ref, j.decision_date FROM citation_mentions m
                               JOIN judgments j USING (judgment_id)
                               WHERE m.provision_id IS NULL AND m.act_ref IS NOT NULL""").fetchall()
    changes = []
    for mid, act_ref, section_ref, ddate in rows:
        ref, slug = canonical(act_ref)
        if slug and section_ref and re.match(r"\d", section_ref):
            pid = pick_provision(lookup, slug, section_ref, ddate)
            if pid:
                changes.append((mid, ref, pid))
    with connect() as conn, conn.transaction():
        conn.execute("CREATE TEMP TABLE link_fix (mention_id INT PRIMARY KEY, act_ref TEXT, provision_id TEXT) ON COMMIT DROP")
        with conn.cursor().copy("COPY link_fix FROM STDIN") as cp:
            for r in changes:
                cp.write_row(r)
        conn.execute("""UPDATE citation_mentions m SET act_ref = f.act_ref, provision_id = f.provision_id FROM link_fix f
                        WHERE m.mention_id = f.mention_id""")
    by = collections.Counter(pid.rsplit("/", 1)[0] for _, _, pid in changes)
    print(f"{len(changes)} of {len(rows)} unlinked mentions now linked: {dict(by)}")


def update_paragraphs():
    """Re-derive `paragraph` for every stored mention from its char_start, without deleting any row."""
    with connect() as conn:
        rows = conn.execute("""SELECT m.mention_id, m.char_start, m.paragraph, j.raw_path FROM citation_mentions m
                               JOIN judgments j USING (judgment_id) ORDER BY j.raw_path""").fetchall()
    changes, markers, current = [], [], None
    for mid, start, old, raw_path in rows:
        if raw_path != current:
            current = raw_path
            markers = paragraph_markers(json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or "")
        new = paragraph_at(markers, start)
        if new != old:
            changes.append((mid, new))
    with connect() as conn:
        with conn.transaction():
            conn.execute("CREATE TEMP TABLE para_fix (mention_id INT PRIMARY KEY, paragraph TEXT) ON COMMIT DROP")
            with conn.cursor().copy("COPY para_fix FROM STDIN") as cp:
                for r in changes:
                    cp.write_row(r)
            conn.execute("""UPDATE citation_mentions m SET paragraph = f.paragraph FROM para_fix f
                            WHERE m.mention_id = f.mention_id""")
        null = conn.execute("SELECT count(*) FILTER (WHERE paragraph IS NULL), count(*) FROM citation_mentions").fetchone()
    print(f"{len(changes)} paragraphs changed; now {null[0]} of {null[1]} mentions have no paragraph")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--relink", action="store_true",
                    help="link stored mentions to newly loaded Acts, in place (keeps LLM rows); nothing else changes")
    ap.add_argument("--paragraphs-only", action="store_true",
                    help="recompute the paragraph of existing rows in place (keeps LLM rows); nothing else changes")
    ap.add_argument("--judgments", help="file of judgment ids, one per line: rebuild ONLY their rows; everyone else's "
                                         "rows (LLM ones included) are untouched")
    args = ap.parse_args()
    if args.relink:
        return relink()
    if args.paragraphs_only:
        return update_paragraphs()
    only = open(args.judgments).read().split() if args.judgments else None

    with connect() as conn:
        if not args.dry_run:
            apply_schema(conn)
        lookup = provision_lookup(conn)
        judgments = conn.execute("""SELECT judgment_id, raw_path, decision_date FROM judgments
                                    WHERE has_full_text AND (%(only)s::text[] IS NULL OR judgment_id = ANY(%(only)s))
                                    ORDER BY judgment_id""", {"only": only}).fetchall()
    if args.limit:
        judgments = judgments[:args.limit]

    rows, stats = [], collections.Counter()
    for i, (jid, raw_path, ddate) in enumerate(judgments):
        text = json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or ""
        for x in extract(text, ddate):
            pid = pick_provision(lookup, x["act_id"], x["section_ref"], ddate) if x["act_id"] else None
            stats["mentions"] += 1
            stats["resolved" if pid else ("act_known_section_missing" if x["act_id"] else
                                          "other_act" if x["act_ref"] else "bare")] += 1
            stats[f"act:{x['act_ref']}"] += 1
            rows.append((jid, pid, x["raw_text"], x["paragraph"], x["char_start"], x["char_end"], "regex",
                         x["confidence"], x["act_ref"], x["section_ref"]))
        if (i + 1) % 2000 == 0:
            print(f"  {i + 1}/{len(judgments)} judgments, {len(rows)} mentions", flush=True)

    print(f"{len(judgments)} judgments -> {stats['mentions']} mentions: {stats['resolved']} resolved to a provision, "
          f"{stats['act_known_section_missing']} in a held Act but section not found, {stats['other_act']} in other "
          f"Acts, {stats['bare']} bare (no Act)")
    print("top cited Acts:")
    for k, n in sorted(((k, n) for k, n in stats.items() if k.startswith("act:")), key=lambda kv: -kv[1])[:25]:
        print(f"  {n:7d}  {k[4:]}")
    if args.dry_run:
        return
    with connect() as conn:
        with conn.transaction():
            if only:   # just these judgments' rows
                conn.execute("DELETE FROM citation_mentions WHERE method IN ('regex', 'llm') AND judgment_id = ANY(%s)",
                             (only,))
            else:   # all rows, including the LLM pass's: re-run pipeline.llm_resolve afterwards (answers are cached)
                conn.execute("DELETE FROM citation_mentions WHERE method IN ('regex', 'llm')")
            with conn.cursor().copy("""COPY citation_mentions (judgment_id, provision_id, raw_text, paragraph,
                    char_start, char_end, method, confidence, act_ref, section_ref) FROM STDIN""") as cp:
                for r in rows:
                    cp.write_row(r)
        print(f"stored {len(rows)} mentions")


if __name__ == "__main__":
    main()
