"""Hakiki's read-only tools for AI agents: the MCP server (api/mcp_server.py) and the Gemini loop (api/agent.py).

Each tool returns {"result", "ids"}: result is what the model reads; ids ({"section", "event", "judgment"}, strings)
are what it may reference as [[section:ID]], [[event:ID]], [[judgment:ID]]. The endpoint code in api/main.py does the
work; nothing here queries what an endpoint already answers.
"""
import inspect
import re

MAX_TEXT, MAX_HISTORY, MAX_QUOTE = 3000, 15, 600
TYPES = {str: "string", int: "integer", bool: "boolean"}
NAME_NOISE = {"the", "and", "another", "others", "republic", "attorney", "general", "ekl", "eklr", "kesc", "keca",
              "kehc", "klr", "ruling", "judgment", "case", "court", "summarise", "summarize", "what", "did", "hold",
              "held", "about", "ors", "anor", "petition", "appeal", "high", "supreme", "decision", "kenya", "county",
              "commissioner", "judgement"}


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


def citing_judgments(provision_id: str, limit: int = 10):
    """Judgments Hakiki holds that cite a section, highest court first, then newest."""
    c = main.citations(provision_id, min(limit, 20), 0).model_dump()
    return {"result": c, "ids": ids(judgment=[j["judgment_id"] for j in c["judgments"]])}


def title_search(conn, name):
    """Titles with every party word (whole words); only if none, titles missing one word (needs 3+ words). Judgments
    with checked rulings first, then newest. confirmed: every word matched and there are 2+ (one word, e.g. 'Mwangi',
    is in too many titles to name a case)."""
    words = [rf"\m{w}\M" for w in dict.fromkeys(re.findall(r"[A-Za-z]{3,}", name.lower())) if w not in NAME_NOISE][:6]
    if not words:
        return []
    n = len(words)
    rows = conn.execute("""SELECT * FROM (
                             SELECT judgment_id, title, court, decision_date::text AS d, neutral_citation, source_url,
                                    (SELECT count(*) FROM unnest(%s::text[]) w WHERE j.title ~* w) AS hits,
                                    EXISTS (SELECT 1 FROM citation_events e WHERE e.judgment_id = j.judgment_id
                                            AND e.verified) AS ruled
                             FROM judgments j WHERE duplicate_of IS NULL AND title ~* ANY(%s)) x
                           WHERE hits >= %s ORDER BY hits DESC, ruled DESC, d DESC NULLS LAST LIMIT 5""",
                        (words, words, n - 1 if n >= 3 else n)).fetchall()
    if rows and rows[0][6] == n:   # all-words matches exist: drop the partial ones
        rows = [r for r in rows if r[6] == n]
    return [dict(zip(("judgment_id", "title", "court", "decision_date", "neutral_citation", "source_url",
                      "words_matched"), r[:7]), words_total=n, confirmed=n >= 2 and r[6] == n) for r in rows]


def find_case(citation: str):
    """Look up a case, e.g. 'Muruatetu & another v Republic [2017] eKLR' or '[2017] KESC 2 (KLR)'. Result per case:
    found | name_mismatch | possible_match | not_in_collection (Hakiki holds ~10% of judgments: not_in_collection never
    means the case doesn't exist). With only party names, returns title matches with words_matched / words_total and
    confirmed: a title matching only some of the words, or a single party word, is not a confirmed case. Also lists
    the checked rulings Hakiki records from the judgments found by citation or by a confirmed title (none from
    unconfirmed matches, which can't be referenced). Possible matches are listed but not confirmed, and carry no
    rulings."""
    with main.db() as conn:
        cases = [f["case"] for f in filing.check(conn, citation)["findings"] if f["kind"] == "case"]
        judgments = [c["judgment"] for c in cases if c["judgment"]]   # possible_match candidates stay in cases only
        titles = [] if cases else title_search(conn, citation)
        ruled = [j["judgment_id"] for j in judgments + titles if j.get("confirmed", True)]   # citation findings: always
        events = [dict(zip(("event_id", "provision_id", "event_type", "judgment_id", "verified_by"), r))
                  for r in conn.execute("""SELECT event_id, provision_id, event_type, judgment_id, verified_by
                                           FROM citation_events WHERE judgment_id = ANY(%s) AND verified
                                           ORDER BY event_id""", (ruled,))]
    return {"result": {"cases": cases, "title_matches": titles, "events": events},
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


TOOLS = {f.__name__: f for f in (list_acts, search_sections, get_section, citing_judgments, find_case, check_text)}


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
