"""Hakiki's read-only tools for AI agents: the MCP server (api/mcp_server.py) and the Gemini loop (api/agent.py).

Each tool returns {"result", "ids"}: result is what the model reads; ids ({"section", "event", "judgment"}, strings)
are what it may reference as [[section:ID]], [[event:ID]], [[judgment:ID]]. The endpoint code in api/main.py does the
work; nothing here queries what an endpoint already answers.
"""
import inspect
import re
from datetime import date

from pipeline.extract_citations import canonical, pick_provision

from .status import statuses

MAX_TEXT, MAX_HISTORY, MAX_QUOTE = 3000, 15, 600
TYPES = {str: "string", int: "integer", bool: "boolean"}
NAME_NOISE = {"the", "and", "another", "others", "republic", "attorney", "general", "ekl", "eklr", "kesc", "keca",
              "kehc", "klr", "ruling", "judgment", "case", "court", "summarise", "summarize", "what", "did", "hold",
              "held", "about", "ors", "anor", "petition", "appeal", "high", "supreme", "decision", "kenya", "county",
              "commissioner", "judgement"}
# Never party words, so never in the full-name tie-break; 'Republic', 'Attorney', 'General', 'others' do count there
NOT_PARTY = {"the", "and", "for", "court", "courts", "judge", "judges", "justice", "petition", "application", "appeal",
             "high", "supreme", "magistrate", "magistrates", "tribunal", "ruling", "judgment", "judgement", "case",
             "matter", "decision", "ekl", "eklr", "kesc", "keca", "kehc", "klr", "ors", "anor"}


def ids(section=(), event=(), judgment=()):
    return {"section": [str(x) for x in section], "event": [str(x) for x in event],
            "judgment": [str(x) for x in judgment]}


def event_view(e):
    """An event as the model reads it: the court's words capped, how it was checked."""
    return {k: e[k] for k in ("event_id", "event_type", "scope", "subsection", "effective_date", "court", "title",
                              "neutral_citation", "source_paragraph", "verified", "verified_by", "state",
                              "superseded_by")} | {"operative_quote": e["operative_quote"][:MAX_QUOTE],
                                                    "scope_text": (e["scope_text"] or "")[:MAX_QUOTE] or None}


def list_acts():
    """The Acts Hakiki holds, with the version dates of each. Sections of other laws are not in Hakiki's collection."""
    return {"result": [a.model_dump() for a in main.acts()], "ids": ids()}


def search_sections(query: str, limit: int = 8):
    """Find statute sections by words or meaning (e.g. 'criminal defamation', 'mandatory death sentence'). Returns
    provision_ids with each section's status; call get_section for the rulings behind a status."""
    hits = main.search(query, min(limit, 20))
    return {"result": [h.model_dump() for h in hits], "ids": ids(section=[h.provision_id for h in hits])}


def get_section(provision_id: str, include_leads: bool = False):
    """One section: its text (latest version held), its status, the rulings that produce the status (summary_events)
    and its history. The status field is authoritative: report it, never derive your own. include_leads adds
    machine-extracted rulings nobody has checked (verified: false); never present those as the status."""
    p = main.provision(provision_id, include_leads).model_dump()
    with main.db() as conn:   # main.Event has no judgment_id; the model needs it to cite [[judgment:ID]]
        jid = dict(conn.execute("SELECT event_id, judgment_id FROM citation_events WHERE event_id = ANY(%s)",
                                ([e["event_id"] for e in p["history"] + p["summary_events"]],)).fetchall())
    events = [[event_view(e) | {"judgment_id": jid.get(e["event_id"])} for e in p[k]]
              for k in ("summary_events", "history")]
    shown = events[0] + events[1][-MAX_HISTORY:]
    result = {**p["provision"], "text": p["provision"]["text"][:MAX_TEXT], "status": p["status"],
              "summary_events": events[0], "history": events[1][-MAX_HISTORY:],
              "history_total": len(events[1]), "cited_by": p["cited_by"], "lead_count": p["lead_count"]}
    return {"result": result, "ids": ids(section=[provision_id], event=[e["event_id"] for e in shown],
                                         judgment=sorted({e["judgment_id"] for e in shown if e["judgment_id"]}))}


def act_key(name):
    """'The Penal Code Act' / 'Sexual Offences Act No. 3 of 2006' / 'KICA Act' -> 'penal code' / 'sexual offences' /
    'kica': for whole-name comparison with the held Acts' titles."""
    name = re.sub(r"\(.*?\)|\bno\.?\s*\d+\s+of\s+\d{4}|\d{4}|[^\w\s]", " ", name.lower())
    return re.sub(r"^the\s+|\s+act$", "", " ".join(name.split()))


def held_act_id(act, held):
    """An Act as the user names it -> its act_id if held ({act_id: title}), else None."""
    cap = re.search(r"\bcap\.?\s*(\d+[a-z]?)\b", act, re.I)
    name = re.sub(r"\bCode\s+Act\b", "Code", re.sub(r"\bNo\.?\s*\d+\s+of\s+\d{4}|\(.*?\)|,?\s*\d{4}\s*$", "", act,
                                                     flags=re.I), flags=re.I)
    keys = {act_key(t): a for a, t in held.items()} | {"kica": "ke/act/cap-411a"}
    slug = canonical(name)[1]   # the extractor's Act names first, then a held Cap number, then a title
    act_id = ((f"ke/act/{slug}" if slug else None) or (cap and f"ke/act/cap-{cap.group(1).lower()}")
              or keys.get(act_key(name)))
    return act_id if act_id in held else None


def find_section(act: str, section: str):
    """Use this whenever the user names an Act and a section number (e.g. act 'Penal Code' or 'Cap. 63', section
    '204', 's.8(2)', 'Article 50'), before saying anything is not held. found: true gives the provision_id and
    status (call get_section for the rulings); found with ambiguous: true lists candidates (one number in two Parts:
    ask which; or a section renumbered between versions, under two IDs with the version dates of each: report both
    and say which one has the court rulings). reason section_not_held: Hakiki holds the Act but not that section;
    act_not_recognised: the name isn't one of held_acts (retry with the matching title from held_acts, or say the Act
    isn't in Hakiki's collection if it clearly isn't one of them); no_section_number: give the section as a number."""
    with main.db() as conn:
        held = dict(conn.execute("SELECT act_id, title FROM acts ORDER BY title").fetchall())
        act_id = held_act_id(act, held)
        if not act_id:
            return {"result": {"found": False, "reason": "act_not_recognised", "held_acts": list(held.values())},
                    "ids": ids()}
        number = re.search(r"\d+[A-Z]{0,2}", section.upper())
        if not number:
            return {"result": {"found": False, "reason": "no_section_number"}, "ids": ids()}
        rows = conn.execute("SELECT provision_id, eid, number, heading FROM provisions WHERE act_id = %s AND number = %s",
                            (act_id, number.group(0))).fetchall()
        slug = act_id.removeprefix("ke/act/")   # pick_provision: the Employment Act's eId change by date
        one = pick_provision({(slug, number.group(0)): [(r[1], r[0]) for r in rows]}, slug, number.group(0),
                             date.today())
        ruled = {r[0] for r in conn.execute("""SELECT DISTINCT provision_id FROM citation_events WHERE verified
                                               AND judgment_id IS NOT NULL AND provision_id = ANY(%s)""",
                                            ([r[0] for r in rows],))}
        if one and not ruled - {one}:   # one ID by date, and no court ruling sits on another ID with this number
            rows = [r for r in rows if r[0] == one]
        status = statuses(conn, [r[0] for r in rows])
        versions = dict(conn.execute("""SELECT t.provision_id, array_agg(v.version_date::text ORDER BY v.version_date)
                                        FROM provision_texts t JOIN act_versions v USING (version_id)
                                        WHERE t.provision_id = ANY(%s) GROUP BY 1""",
                                     ([r[0] for r in rows],)).fetchall())
    if not rows:
        return {"result": {"found": False, "reason": "section_not_held", "act_id": act_id, "act_title": held[act_id]},
                "ids": ids()}
    found = [{"provision_id": p, "number": n, "heading": h, "status": status[p]} for p, _, n, h in rows]
    result = found[0] if len(found) == 1 else {"ambiguous": True, "candidates": [
        f | {"versions": versions.get(f["provision_id"], [])} for f in found]}
    return {"result": {"found": True, "act_title": held[act_id], **result}, "ids": ids(section=[f["provision_id"]
                                                                                              for f in found])}


def citing_judgments(provision_id: str, limit: int = 10):
    """Judgments Hakiki holds that cite a section, highest court first, then newest."""
    c = main.citations(provision_id, min(limit, 20), 0).model_dump()
    return {"result": c, "ids": ids(judgment=[j["judgment_id"] for j in c["judgments"]])}


def party_span(text):
    """'What did the court hold in Kimaru & 17 others v Attorney General on X?' -> 'Kimaru & 17 others v Attorney
    General': filing.cited_name drops the lead-in; the name ends at the first lowercase word after the 'v'. None
    without a 'v'. The name ends before a bracketed citation or year ('X v Y [2022] eKLR', 'X v Y (2022)')."""
    text = re.split(r"\[|\(\s*(?:19|20)\d\d\s*\)", text)[0]
    words = (filing.cited_name(text, len(text)) or "").split()
    vi = next((i for i, w in enumerate(words) if w.lower() in filing.V), None)
    if vi is None:
        return None
    end = next((i for i in range(vi + 1, len(words)) if words[i][0].islower() and words[i] not in filing.GLUE),
               len(words))
    return " ".join(words[:end]).rstrip("?.,;") or None


def title_search(conn, name):
    """Titles with every party word (whole words); only if none, titles missing one word (needs 3+ words). Up to 5,
    a year the user gave first, then judgments with checked rulings, then newest. One rule confirms: a title is
    confirmed only if it is the single title in the whole table left by these filters, applied in order until one
    remains: every party word; every word of the 'X v Y' span ('Attorney General' included); starts with the span
    as written; the year the user gave ('[2019]', '(2019)'). A filter that leaves none, or several left at the end:
    nothing confirmed ('Okuta' names a case; 'Mwangi', in hundreds of titles, doesn't). A single survivor whose
    [YYYY] and decision year both differ from the user's year gets year_mismatch, not confirmed."""
    span = party_span(name)   # 'X v Y' inside a question: only its words name the case
    words = [rf"\m{w}\M" for w in dict.fromkeys(re.findall(r"[A-Za-z]{3,}", (span or name).lower()))
             if w not in NAME_NOISE][:6]
    if not words:
        return []
    n = len(words)
    y = re.search(r"[\[(]\s*((?:19|20)\d\d)\s*[\])]", name)
    year = y and y[1]
    in_year = "(position('[' || %s || ']' in title) > 0 OR extract(year FROM decision_date)::int::text = %s)"
    rows = conn.execute(f"""SELECT * FROM (
                             SELECT judgment_id, title, court, decision_date::text AS d, neutral_citation, source_url,
                                    (SELECT count(*) FROM unnest(%s::text[]) w WHERE j.title ~* w) AS hits,
                                    EXISTS (SELECT 1 FROM citation_events e WHERE e.judgment_id = j.judgment_id
                                            AND e.verified) AS ruled,
                                    coalesce({in_year}, false) AS ym
                             FROM judgments j WHERE duplicate_of IS NULL AND title ~* ANY(%s)) x
                           WHERE hits >= %s ORDER BY hits DESC, ym DESC, ruled DESC, d DESC NULLS LAST LIMIT 5""",
                        (words, year, year, words, n - 1 if n >= 3 else n)).fetchall()
    if rows and rows[0][6] == n:   # all-words matches exist: drop the partial ones
        rows = [r for r in rows if r[6] == n]
    # the one rule: narrow the whole table (LIMIT 2: enough to tell one from several) until a single title is left
    filters = [("title ~* ALL(%s)", (words,))]
    if span:
        every = [rf"\m{w}\M" for w in dict.fromkeys(re.findall(r"[A-Za-z]{3,}", span.lower())) if w not in NOT_PARTY]
        filters += [("title ~* ALL(%s)", (every,)),   # compared by prefix: no LIKE wildcards to escape
                    ("left(lower(title), %s) = lower(%s) AND substr(title, %s, 1) IN (' ', '(', '[')",
                     (len(span), span, len(span) + 1))]
    if year:
        filters.append((in_year, (year, year)))
    left, conds, params = [], [], []
    for cond, ps in filters:
        conds.append(cond)
        params += ps
        left = conn.execute("""SELECT judgment_id, title, court, decision_date::text, neutral_citation, source_url
                               FROM judgments WHERE duplicate_of IS NULL AND """ + " AND ".join(conds) + " LIMIT 2",
                            params).fetchall()
        if len(left) != 2:
            break
    # ponytail: a name unique in our ~10% sample confirms that case even if the user meant another;
    # upgrade: confirm with the user instead.
    one = left[0] if len(left) == 1 else None
    if one and not any(r[0] == one[0] for r in rows):
        rows = [(*one, n, False, False)] + rows[:4]
    out = []
    for r in rows:
        t = dict(zip(("judgment_id", "title", "court", "decision_date", "neutral_citation", "source_url",
                      "words_matched"), r[:7]), words_total=n, confirmed=bool(one) and r[0] == one[0])
        if year and r[6] == n and year not in re.findall(r"\[(\d{4})\]", t["title"]) + [(t["decision_date"] or "")[:4]]:
            t |= {"confirmed": False, "year_mismatch": True}
        out.append(t)
    return out


def find_case(citation: str):
    """Look up a case, e.g. 'Muruatetu & another v Republic [2017] eKLR' or '[2017] KESC 2 (KLR)'. Result per case:
    found | name_mismatch | possible_match | not_in_collection (Hakiki holds ~10% of judgments: not_in_collection never
    means the case doesn't exist). With only party names, returns title matches with words_matched / words_total and
    confirmed: a title matching only some of the words, or a single party word in several titles, is not a confirmed
    case (ambiguous: several matches, none confirmed: ask the user which case they mean). Also lists
    the checked rulings Hakiki records from the judgments found by citation or by a confirmed title (none from
    unconfirmed matches, which can't be referenced), each with its Act title and section number. Possible matches are
    listed but not confirmed, and carry no rulings; when a citation isn't confirmed, the party names are searched too.
    A title match with year_mismatch has the names but not the year the user gave: say so and ask."""
    with main.db() as conn:
        cases = [f["case"] for f in filing.check(conn, citation)["findings"] if f["kind"] == "case"]
        judgments = [c["judgment"] for c in cases if c["judgment"]]   # possible_match candidates stay in cases only
        # no judgment confirmed by citation (possible_match, not_in_collection, none parsed): try the party names too;
        # a confirmed title wins over the unconfirmed candidates, which stay in cases for transparency
        titles = [] if judgments else title_search(conn, citation)
        ruled = [j["judgment_id"] for j in judgments + titles if j.get("confirmed", True)]   # citation findings: always
        events = [dict(zip(("event_id", "provision_id", "event_type", "judgment_id", "verified_by", "act_title",
                            "section_number", "heading"), r))
                  for r in conn.execute("""SELECT e.event_id, e.provision_id, e.event_type, e.judgment_id, e.verified_by,
                                                  a.title, p.number, p.heading
                                           FROM citation_events e JOIN provisions p USING (provision_id)
                                           JOIN acts a ON a.act_id = p.act_id
                                           WHERE e.judgment_id = ANY(%s) AND e.verified
                                           ORDER BY e.event_id""", (ruled,))]
    ambiguous = len(titles) > 1 and not any(t["confirmed"] for t in titles)
    return {"result": {"cases": cases, "title_matches": titles, "ambiguous": ambiguous, "events": events},
            "ids": ids(section=sorted({e["provision_id"] for e in events}), event=[e["event_id"] for e in events],
                       judgment=ruled)}


def check_text(text: str):
    """Check every case and section citation in a text (a filing or a draft): does the case exist in Hakiki, do the
    quotes appear in it, and what is each cited section's status."""
    if len(text) > main.MAX_FILING:
        raise ValueError(f"text longer than {main.MAX_FILING:,} characters")
    with main.db() as conn:
        findings = filing.check(conn, text)["findings"]
    out, sec, ev, jud = [], set(), set(), set()
    for f in findings:
        row = {"raw_text": f["raw_text"], "kind": f["kind"]}
        if f["case"]:
            j = f["case"]["judgment"]
            row |= {"result": f["case"]["result"], "judgment_id": j and j["judgment_id"],
                    "quotes": [{"result": q["result"], "paragraph": q["paragraph"]} for q in f["quotes"]]}
            jud |= {j["judgment_id"]} if j else set()
        else:
            s = f["section"]
            pid = s["provision"] and s["provision"]["provision_id"]
            row |= {"result": s["result"], "act_ref": s["act_ref"], "provision_id": pid, "status": s["status"],
                    "event_ids": [e["event_id"] for e in s["summary_events"]]}
            sec |= {pid} if pid else set()
            ev |= set(row["event_ids"])
        out.append(row)
    return {"result": out, "ids": ids(section=sorted(sec), event=sorted(ev), judgment=sorted(jud))}


TOOLS = {f.__name__: f for f in (list_acts, search_sections, get_section, find_section, citing_judgments, find_case,
                                  check_text)}


def call(name, args):
    if name not in TOOLS:
        raise ValueError(f"no tool {name}")
    return TOOLS[name](**args)


def declaration(fn):
    """Gemini functionDeclaration from the signature and docstring."""
    params = inspect.signature(fn).parameters
    d = {"name": fn.__name__, "description": inspect.getdoc(fn)}
    if params:
        d["parameters"] = {"type": "object", "properties": {n: {"type": TYPES[p.annotation]} for n, p in params.items()},
                           "required": [n for n, p in params.items() if p.default is p.empty]}
    return d


DECLARATIONS = [declaration(f) for f in TOOLS.values()]

# Last, so `import api.tools` works on its own: main imports mcp_server, which reads TOOLS (defined above) from this
# partly loaded module. main's names are used only inside functions.
from . import filing, main   # noqa: E402
