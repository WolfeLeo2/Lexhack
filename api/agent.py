"""Hakiki's research agent: Gemini with the tools in api/tools.py, answers grounded in what the tools returned.

  uv run python -m api.agent "Is section 204 of the Penal Code still good law?"

The model never writes a court's words: it cites [[event:ID]], [[section:ID]], [[judgment:ID]] and render() fills in
the verbatim text from the database. A reference no tool returned is removed and counted (the eval's headline).
"""
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests

from . import filing, main, tools
from .status import RULES, load_events_many, statuses, with_leads

MODEL, MAX_ROUNDS = "gemini-3.5-flash-lite", 8
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
STREAM_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
REF = re.compile(r"\[\[(section|event|judgment):([^\]\s]+)\]\]")
ACT = re.compile(r"\[\[act:\s*([^\]]+?)\s*\]\]")   # not a reference kind; naming a held Act is allowed (render_parts)
BRACKETS = re.compile(r"\[\[(?:(?!\[\[)[^\n])*?\]\]")   # anything in [[...]]: a REF, a grouped [[event:1], [judgment:x]], or junk
GROUP = re.compile(r"\]\s*,?\s*\[")   # between the references of a grouped one
LEFTOVER = re.compile(r"\[\[\S*|\S*\]\]")   # an unclosed or stray bracket pair: never shown

SYSTEM = """You are Hakiki's research assistant for Kenyan statute law. Hakiki is a citator: it records whether a
section is in force, amended, repealed, or limited or struck down by a court, with the court's own words.

Rules:
1. A section's status is the status field get_section returns. Report it; never derive a status yourself, and never
   reduce it to a yes/no or valid/invalid verdict.
2. Never write out, quote or paraphrase a court's order yourself (no quotation marks or block quotes around a court's
   words). Cite every ruling you mention as [[event:ID]] and Hakiki shows the verbatim quote; [[judgment:ID]] only
   names the case and never replaces the [[event:ID]]. Cite every section you discuss as [[section:ID]]. These three
   are the only reference kinds. Write each reference whole and on its own, e.g. [[event:12]] [[event:13]]; never
   group IDs inside one pair of brackets or add a label inside them.
3. Only use IDs that a tool returned in this conversation, copied character for character: a section ID is the full
   provision_id (shaped like ke/act/<act>/<eid>), never a bare number. Never guess or shorten an ID.
4. Say something (a case, an Act, a section) is not in Hakiki's collection only after list_acts, find_section or
   find_case said so; when the user names an Act and a section, call find_section first. find_section's
   act_not_recognised means the name didn't match the held Acts it lists: if the user's Act is one of those titles
   under another name, retry with that title; say the Act is not in Hakiki's collection only if it clearly isn't one
   of them. Hakiki holds about 10% of judgments, so never say a case does not exist or is fake.
5. Say how each ruling was checked, in the words of its checked_by field ("checked by a person", "checked by an AI
   reviewer", "from Kenya Law's reviser's note", "unverified"). Never present an unverified lead as
   the status. Describe a ruling's state as its state field says: "displaced by a later ruling" means a later court
   took a different view (say displaced or overtaken, never reversed); only "reversed on appeal" means reversed.
6. Report what the sources say. Never advise on the user's own case or tell them what to do; suggest they consult an
   advocate. For an advice question, still look the section up (find_section or search_sections, then get_section)
   and report its status and rulings before saying Hakiki can't advise on their case. Don't skip the lookup.

Look things up before answering: find_section when an Act and section are named, search_sections when no section
number is given, get_section for status and rulings, find_case for a named case. Pass case names to find_case as the
user wrote them: never add a year, "eKLR" or a neutral citation the user didn't give (a year in brackets after the
name may be passed as written, but don't turn it into a citation). When find_case says ambiguous, list the possible
cases by their titles in plain text (not as [[judgment:ID]], which works only for a confirmed case) and ask the user
which one they mean; don't describe any of them as the case. When a section was
renumbered between versions (renumbered_from in find_section or get_section), its rulings cover every numbering: say
when a ruling was made under the older one.
Answer briefly, in plain English."""

DRAFT = """

Draft mode: the user wants a short draft (for example a submission paragraph) for an advocate to review. All six
rules above still apply.
- Research first with the tools, then write only the draft: plain, formal, short prose an advocate could adapt, with
  the references inline. No preamble, no notes to the user.
- Cite cases only as [[judgment:ID]] or [[event:ID]]. Never type a case name with a citation, an eKLR or neutral
  citation, or quoted words yourself: Hakiki fills them in from the database.
- When a section you cite has court rulings, cite them ([[event:ID]]) so the draft says what the court did.
- If a case the user named can't be confirmed (find_case found no single case), say so plainly in the draft.
- The draft is for an advocate's review. Don't advise the user on their own case or tell them what to do."""
DRAFT_LABEL = "Draft for an advocate's review. Hakiki reports what sources say; this is not legal advice."
CASE_NOTES = {"not_in_collection": "Not in Hakiki's collection — check before relying on it",
              "possible_match": "Fits more than one case in Hakiki's collection, so Hakiki can't say which",
              "name_mismatch": "The citation belongs to a different case in Hakiki's collection"}
QUOTE_NOTES = {"close": "Close to the judgment, but not word for word",
               "not_found": "The quoted words are not in the judgment",
               "not_checked": "Not checked: Hakiki doesn't hold the cited judgment's text"}
COURT_LIMITS = {"declared_unconstitutional", "read_down", "severed"}   # a court's limiting ruling (status_ke LIMITING)
NO_FIX = {"not_checked", "not_covered", "revision_skipped", "references_removed"}   # reported, never sent for revision
QUOTED = re.compile(r'["“]([^"“”]+)["”]')
REVISE_AFTER = 35   # seconds into the chat run: later than this, skip the revision (the chat's deadline is 55)


def answer_text(data):
    """A reply's answer text (thoughts left out); '' when it calls a tool."""
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "" if any("functionCall" in p for p in parts) else "".join(
        p.get("text", "") for p in parts if not p.get("thought"))


def post(body, api_key, stream=False):
    return requests.post((STREAM_URL if stream else URL).format(model=MODEL), json=body,
                         headers={"x-goog-api-key": api_key}, timeout=180, stream=stream)


def read_stream(r, on_text):
    """SSE chunks -> one generateContent-shaped reply. Parts are kept as received (thought signatures go back
    unchanged); text goes to on_text as it arrives, until a function call shows up."""
    parts, cand, feedback, call = [], {}, None, False
    for line in r.iter_lines():
        if not line.startswith(b"data:"):
            continue
        chunk = json.loads(line[5:])
        feedback = chunk.get("promptFeedback") or feedback
        cand = (chunk.get("candidates") or [{}])[0]
        for p in (cand.get("content") or {}).get("parts") or []:
            parts.append(p)
            call = call or "functionCall" in p
            if not call and p.get("text") and not p.get("thought"):
                on_text(p["text"])
    data = {"candidates": [{**cand, "content": {"role": "model", "parts": parts}}]}
    return {**data, "promptFeedback": feedback} if feedback else data


def generate(body, api_key, attempts=10, on_text=None):
    """One Gemini call, cached by request body (temperature 0: same request, same answer). on_text: stream the reply
    and pass its answer text on as it arrives (a cache hit passes it on whole); retried only before any text went."""
    data_dir = os.environ.get("LEXHACK_DATA")   # unset on Railway: no disk cache there
    path = None
    if data_dir:
        cache = Path(data_dir) / "cache" / "agent"
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / f"{hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}.json"
    if path and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if on_text and (t := answer_text(data)):
            on_text(t)
        return data
    sent = []

    def forward(t):
        sent.append(t)
        on_text(t)
    for attempt in range(attempts):   # per-minute quotas can take a minute or two to clear (as pipeline/llm_resolve.call)
        wait = min(120, 10 * 2 ** attempt)
        try:
            with post(body, api_key, stream=bool(on_text)) as r:
                if r.status_code == 429 and "PerDay" in r.text:
                    raise RuntimeError(f"Gemini daily quota exhausted for {MODEL}; answers so far are cached")
                if r.status_code == 429 or r.status_code >= 500:
                    print(f"  HTTP {r.status_code}; retrying in {wait}s", file=sys.stderr, flush=True)
                    if attempt + 1 < attempts:
                        time.sleep(wait)
                    continue
                r.raise_for_status()
                data = read_stream(r, forward) if on_text else r.json()
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            if sent:   # the reader has part of this reply: a retry would repeat it
                raise
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", file=sys.stderr, flush=True)
            if attempt + 1 < attempts:
                time.sleep(wait)
            continue
        if path and ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts"):   # never cache an empty reply
            path.write_text(json.dumps(data), encoding="utf-8")
        return data
    raise RuntimeError(f"Gemini call failed after {attempts} attempts (network or rate limit)")


def history_from_turns(turns):
    """[{question, answer}] (earlier turns, answers as rendered) -> Gemini contents."""
    return [c for t in turns for c in ({"role": "user", "parts": [{"text": t["question"]}]},
                                       {"role": "model", "parts": [{"text": t["answer"]}]})]


def step_label(name, args):
    """What a tool call is doing, in plain English, for the chat's progress line."""
    def arg(k):
        s = str(args.get(k) or "")
        return s if len(s) <= 80 else s[:80] + "…"
    return {"find_section": lambda: f"Looking up {arg('act')} s.{arg('section')}" if arg("act") and arg("section")
            else "Looking up the section",
            "search_sections": lambda: f"Searching sections for “{arg('query')}”",
            "get_section": lambda: "Reading the section and its rulings",
            "find_case": lambda: f"Looking for the case “{arg('citation')}”",
            "citing_judgments": lambda: "Finding judgments that cite it",
            "list_acts": lambda: "Checking which Acts Hakiki holds",
            "check_text": lambda: "Checking the citations in the text",
            "check": lambda: "Checking the draft's citations",
            "revise": lambda: "Fixing what the check found"}.get(name, lambda: "Looking things up")()


def run(question, history=(), api_key=None, on_step=None, attempts=10, system=SYSTEM, on_text=None, on_reset=None):
    """attempts: Gemini tries per call (the chat passes fewer: it has a deadline). on_text: the answer's raw text as the
    model writes it; on_reset: forget the text sent so far (a round that streamed text turned out to call a tool)."""
    api_key = api_key or os.environ["GEMINI_API_KEY"]
    contents = [*history, {"role": "user", "parts": [{"text": question}]}]
    steps, seen = [], {"section": set(), "event": set(), "judgment": set()}
    for rnd in range(MAX_ROUNDS + 1):
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "tools": [{"functionDeclarations": tools.DECLARATIONS}], "generationConfig": {"temperature": 0}}
        if rnd == MAX_ROUNDS:   # out of rounds: answer with what you have
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
        sent = []

        def forward(t):
            sent.append(t)
            on_text(t)
        resp = generate(body, api_key, attempts=attempts, on_text=forward if on_text else None)
        cand = (resp.get("candidates") or [{}])[0]
        content = cand.get("content")
        if not content or not content.get("parts"):
            raise RuntimeError(f"Gemini returned no content (finishReason {cand.get('finishReason')}, "
                               f"promptFeedback {resp.get('promptFeedback')})")
        contents.append(content)   # unchanged: Gemini 3.x thought signatures must come back as sent
        calls = [p["functionCall"] for p in content["parts"] if "functionCall" in p]
        if not calls:
            return {"answer": answer_text(resp).strip(), "steps": steps, "seen": {k: sorted(v) for k, v in seen.items()},
                    "contents": contents}
        if sent and on_reset:
            on_reset()
        replies = []
        for c in calls:
            args = c.get("args") or {}
            if on_step:
                on_step(c["name"], args)
            try:
                out = tools.call(c["name"], args)
                for k, v in out["ids"].items():
                    seen[k].update(v)
                result = out["result"]
            except Exception as e:   # the model sees the type only: a message could carry internals into a public answer
                logging.warning("tool %s failed: %s: %s", c["name"], type(e).__name__, e)
                result = {"error": f"tool failed: {type(e).__name__}"}
            steps.append({"tool": c["name"], "args": args, "result": result})
            replies.append({"functionResponse": {"name": c["name"], "response": {"result": result}}})
        contents.append({"role": "user", "parts": replies})
    raise AssertionError("unreachable: the last round has tools disabled")


def ref(text):
    """'[[kind:ID]]' -> (kind, ID); '[[act:X]]' -> ('act', X); a malformed reference -> (None, text): no tool returned
    it, so it is invented."""
    m = REF.fullmatch(text) or ACT.fullmatch(text)
    return (m.groups() if m.re is REF else ("act", m.group(1))) if m else (None, text)


def held_acts(conn):
    """{lower-cased act_id or title: title} for the Acts Hakiki holds."""
    return {k.lower(): title for a, title in conn.execute("SELECT act_id, title FROM acts") for k in (a, title)}


def is_invented(k, v, ok, acts):
    """A reference no tool returned. Naming a held Act ([[act:Penal Code]]) is not a claim about rulings, so not one."""
    return (k, v) not in ok and not (k == "act" and v.lower() in acts)


def pieces(token):
    """'[[event:1], [judgment:x]]' (the model grouped them) -> ['[[event:1]]', '[[judgment:x]]']; a single one as is."""
    return [f"[[{x}]]" for x in GROUP.split(token[2:-2])]


def refs(answer):
    return [ref(t) for m in BRACKETS.findall(answer) for t in pieces(m)]


class RefStrip:
    """Streamed text with [[...]] references taken out, holding back one split across chunks: no raw ID is shown."""
    def __init__(self):
        self.buf = ""

    def feed(self, delta):
        head, nl, tail = BRACKETS.sub("", self.buf + delta).rpartition("\n")
        text = LEFTOVER.sub("", head) + nl + tail   # a [[ before a line break can't close any more
        i = text.find("[[")
        i = len(text) - text.endswith("[") if i < 0 else i
        self.buf = text[i:]
        return text[:i]


def render_parts(answer, seen, conn):
    """-> (the answer as Parts: text, and each reference filled in from the database; number of references no tool
    returned). The /api/chat contract's Part shapes; render() joins them into plain text."""
    ok = {(k, v) for k, vs in seen.items() for v in vs}
    good = [(k, v) for k, v in refs(answer) if (k, v) in ok]
    ev = {str(r[0]): r[1:] for r in conn.execute(
        """SELECT e.event_id, e.operative_quote, e.source_paragraph, e.verified_by, j.title, j.neutral_citation,
                  j.court, j.source_url, e.provision_id FROM citation_events e LEFT JOIN judgments j USING (judgment_id)
           WHERE e.event_id = ANY(%s)""", ([int(v) for k, v in good if k == "event" and v.isdigit()],))}
    # each cited ruling's state from the resolver (leads included, so an unverified one has a state too)
    state = {str(e["event_id"]): e["state"]
             for p, es in load_events_many(conn, {r[-1] for r in ev.values()}, include_unverified=True).items()
             for e in with_leads(RULES[p.split("/", 1)[0]].resolve, es)["history"]}   # one query, as statuses()
    sec_ids = [v for k, v in good if k == "section"]
    sec = {r[0]: r[1:] for r in conn.execute(
        """SELECT p.provision_id, a.title, p.number, p.heading FROM provisions p JOIN acts a USING (act_id)
           WHERE p.provision_id = ANY(%s)""", (sec_ids,))}
    status = statuses(conn, list(sec))
    acts = held_acts(conn)
    jud = {r[0]: r[1:] for r in conn.execute(
        "SELECT judgment_id, title, neutral_citation, source_url FROM judgments WHERE judgment_id = ANY(%s)",
        ([v for k, v in good if k == "judgment"],))}

    def part(text):
        k, v = ref(text)
        if k == "act" and v.lower() in acts:
            return {"kind": "text", "text": acts[v.lower()]}
        if (k, v) in ok and k == "event" and v in ev:
            quote, para, by, title, cite, court, url, _ = ev[v]
            st = state.get(v, "in effect")
            return {"kind": "ruling", "event_id": int(v), "quote": quote, "case": title, "citation": cite,
                    "court": court, "paragraph": para,
                    "checked_by": tools.checked_by(by),
                    "state": None if st == "in effect" else st, "url": url}
        if (k, v) in ok and k == "section" and v in sec:
            act, number, heading = sec[v]
            return {"kind": "section", "provision_id": v, "act": act, "number": number, "heading": heading,
                    "status": status[v]}
        if (k, v) in ok and k == "judgment" and v in jud:
            title, cite, url = jud[v]
            return {"kind": "case", "judgment_id": v, "title": title, "citation": cite, "url": url}
        return {"kind": "removed"}

    def text(t):
        if t := LEFTOVER.sub("", t):
            parts.append({"kind": "text", "text": t})

    parts, at = [], 0
    for m in BRACKETS.finditer(answer):
        text(answer[at:m.start()])
        for k, t in enumerate(pieces(m.group())):
            if k:
                parts.append({"kind": "text", "text": " "})
            parts.append(part(t))
        at = m.end()
    text(answer[at:])
    return parts, sum(p["kind"] == "removed" for p in parts)


def in_title(cite, title):
    """The citation, or None when the title already carries it ('… [2017] KEHC 8382 (KLR)')."""
    return None if cite and title and cite in title else cite


def part_text(p):
    """One Part as plain text (the agent's CLI, the eval and the chat's `text`)."""
    if p["kind"] == "ruling":
        src = ", ".join(x for x in (p["case"] or "Parliament (Kenya Law reviser's note)", in_title(p["citation"], p["case"]),
                                    p["court"],
                                    p["paragraph"] and f"para {p['paragraph']}") if x)
        who = p["checked_by"] + (f"; {p['state']}" if p["state"] else "")
        return f'"{p["quote"]}" ({src}; {who}){f" <{p['url']}>" if p["url"] else ""}'
    if p["kind"] == "section":
        return f"{p['act']} s.{p['number']}{f' ({p['heading']})' if p['heading'] else ''} [status: {p['status']}]"
    if p["kind"] == "case":
        cite = in_title(p["citation"], p["title"])
        return f"{p['title']}{f' {cite}' if cite else ''}{f' <{p['url']}>' if p['url'] else ''}"
    if p["kind"] == "removed":
        return "[unverified reference removed]"
    return p["text"]


def render(answer, seen, conn):
    """-> (answer with references replaced by database text, number of references no tool returned)."""
    parts, removed = render_parts(answer, seen, conn)
    return "".join(map(part_text, parts)), removed


def item(raw, kind, result, note, flagged=False, cite=()):
    return {"raw_text": raw[:200], "kind": kind, "result": result, "note": note, "flagged": flagged, "cite": list(cite)}


def named_in(name, question):
    """The user's question names this case (find_case gets names as the user wrote them; the first party will do)."""
    n, q = name.lower().strip(), question.lower()
    first = re.split(r"\s+v\.?\s+", n)[0].strip()
    return bool(n) and (n in q or (len(first) >= 3 and first in q))


UNCONFIRMED = re.compile(r"(could ?n[o'’]t|cannot|can['’]t|unable to|did not|was not able to)\s+(be\s+)?confirm|"
                         r"not (been )?confirmed|not in hakiki['’]s collection", re.I)


def says_unconfirmed(name, text, near=200):
    """The draft already says, near the case's name (or its first party), that it couldn't be confirmed."""
    t, n = text.lower(), name.lower().strip()
    first = re.split(r"\s+v\.?\s+", n)[0].strip()
    return any(UNCONFIRMED.search(t[max(0, m.start() - near):m.end() + near])
               for w in {n, first} if len(w) >= 3 for m in re.finditer(re.escape(w), t))


def dropped_cases(parts, question, steps):
    """find_case lookups for a case the user named that confirmed no single case, and that the draft neither cites nor
    already says couldn't be confirmed (a revision would change nothing)."""
    text = "".join(p["text"] for p in parts if p["kind"] == "text")
    in_draft = {p["judgment_id"] for p in parts if p["kind"] == "case"} | {p["case"] for p in parts if p["kind"] == "ruling"}
    out = []
    for s in steps:
        r, name = s["result"], str(s["args"].get("citation") or "")
        if s["tool"] != "find_case" or not named_in(name, question) or name in {i["raw_text"] for i in out}:
            continue
        cases, titles = r.get("cases", []), r.get("title_matches", [])
        confirmed = ({c["judgment"]["judgment_id"] for c in cases if c["result"] == "found" and c["judgment"]} |
                     {t["judgment_id"] for t in titles if t["confirmed"]})
        cands = ({x for c in cases if c["judgment"] for x in (c["judgment"]["judgment_id"], c["judgment"].get("title"))} |
                 {x for t in titles for x in (t["judgment_id"], t["title"])})
        if len(confirmed) != 1 and not in_draft & cands and not says_unconfirmed(name, text):
            out.append(item(name, "case", "not_confirmed",
                            f"You named {name}. Hakiki could not confirm it, so the draft does not cite it.", True))
    return out


def draft_check(conn, parts, question="", steps=()):
    """The rendered draft through the filing checker. -> every judged item [{raw_text, kind, result, note, flagged,
    cite}], flagged first (cite: event IDs the model should reference for a section). Only what the model wrote is
    judged: a case or section inside a reference Hakiki rendered from the database is not, nor a ruling's own words."""
    spans, at = [], 0
    for p in parts:
        n = len(part_text(p))
        spans.append((at, at + n, p["kind"]))
        at += n
    text = "".join(map(part_text, parts))
    kind_at = lambda i: next((k for s, e, k in spans if s <= i < e), "text")
    rulings = [p for p in parts if p["kind"] == "ruling"]
    cited = {p["event_id"] for p in rulings}
    section_parts = {p["provision_id"] for p in parts if p["kind"] == "section"}
    items, sections, judged = [], set(), set()
    for f in filing.check(conn, text)["findings"]:
        where = kind_at(f["char_start"])
        if f["kind"] == "case":
            c = f["case"]
            if where == "text":
                items.append(item(f["raw_text"], "case", c["result"], "typed in the draft; found in Hakiki's collection")
                             if c["result"] == "found" else
                             item(f["raw_text"], "case", c["result"], CASE_NOTES.get(c["result"], c["result"]), True))
            # quotes the checker hung on the citation inside a ruling Hakiki rendered: the model attached no case to
            # them (the scan below reports them as not checked), and the ruling's own words are from the database
            for q in f["quotes"] if where != "ruling" else ():
                judged.add(q["quote"])
                if not any(q["quote"] in r["quote"] for r in rulings):
                    items.append(item(q["quote"], "quote", "verbatim", "matches the judgment word for word")
                                 if q["result"] == "verbatim" else
                                 item(q["quote"], "quote", q["result"], QUOTE_NOTES.get(q["result"], q["result"]), True))
            continue
        if where == "ruling":
            continue
        s = f["section"]
        key = s["provision"]["provision_id"] if s["provision"] else s["act_ref"]
        if not key or key in sections:   # a bare "section 12" with no Act: nothing to look up
            continue
        sections.add(key)
        if s["provision"]:   # "sections 203 and 204 of the Penal Code" is two findings: name the one judged
            f = dict(f, raw_text=f"{s['provision']['act_title']} s.{s['provision']['number']}")
        if not s["provision"]:
            items.append(item(f["raw_text"], "section", "not_covered",
                              "Hakiki doesn't hold this Act; check it before relying on it", True))
        elif s["status"] == "repealed":
            ids = [e["event_id"] for e in s["summary_events"]]
            items.append(item(f["raw_text"], "section", "limit_mentioned", "the draft says it is repealed")
                         if key in section_parts or cited & set(ids) else
                         item(f["raw_text"], "section", "limit_not_mentioned",
                              "Hakiki records this section as repealed; the draft doesn't say so", True, ids))
        elif ids := [e["event_id"] for e in s["summary_events"] if e["event_type"] in COURT_LIMITS]:
            items.append(item(f["raw_text"], "section", "limit_mentioned", "the draft cites the court's ruling that "
                              "limits it") if cited & set(ids) else
                         item(f["raw_text"], "section", "limit_not_mentioned",
                              f"Hakiki records this section as “{s['status']}”; the draft cites none of the court "
                              "rulings that limit it", True, ids))
        else:
            items.append(item(f["raw_text"], "section", "in_force", f"Hakiki records this section as “{s['status']}”"))
    for p in parts:   # quoted words the model typed with no case attached: the filing checker can't judge them
        for m in QUOTED.finditer(p["text"] if p["kind"] == "text" else ""):
            q = m[1].strip()
            if len(q.split()) >= 5 and not any(q in j or j in q for j in judged):
                items.append(item(q, "quote", "not_checked",
                                  "quoted words with no case attached; Hakiki couldn't check them", True))
    items += dropped_cases(parts, question, steps)
    return sorted(items, key=lambda i: not i["flagged"])


def fixable(items):
    return [i for i in items if i["flagged"] and i["result"] not in NO_FIX]


def revise_message(flags):
    lines = [f"- {f['raw_text'][:200]}: {f['note']}" + (" (cite " + " ".join(f"[[event:{i}]]" for i in f["cite"]) + ")"
                                                         if f.get("cite") else "") for f in flags]
    return ("Hakiki's citation check found these problems in your draft:\n" + "\n".join(lines) +
            "\nFix these or state them plainly in the draft. Reply with the full revised draft only.")


def draft(question, history=(), api_key=None, on_step=None, attempts=10, started=None, on_text=None, on_reset=None):
    """Draft mode: research and write, check the rendered draft with the filing checker, one revision turn if anything
    the model can fix is flagged, then a second check. started: the run's time.monotonic() start; past REVISE_AFTER
    seconds the revision is skipped. -> {parts, removed, check} (check: every judged item, flagged first)."""
    started = time.monotonic() if started is None else started
    step = on_step or (lambda name, args: None)
    out = run(question, history, api_key, on_step, attempts, system=SYSTEM + DRAFT, on_text=on_text, on_reset=on_reset)
    seen, steps = {k: set(v) for k, v in out["seen"].items()}, out["steps"]
    step("check", {})
    with main.db() as conn:
        parts, removed = render_parts(out["answer"], seen, conn)
        items = draft_check(conn, parts, question, steps)
    notes = []
    if (fix := fixable(items)) and time.monotonic() - started > REVISE_AFTER:
        notes.append(item("", "note", "revision_skipped", "Hakiki ran out of time to revise the draft, so this is its "
                          "first draft with what the check found", True))
    elif fix:
        step("revise", {})
        if on_reset:   # the first draft's streamed text gives way to the revision's
            on_reset()
        for f in fix:   # the check told the model these IDs, so they count as returned to it
            seen["event"].update(str(i) for i in f["cite"])
        out = run(revise_message(fix), out["contents"], api_key, on_step, attempts, system=SYSTEM + DRAFT,
                  on_text=on_text, on_reset=on_reset)
        for k, v in out["seen"].items():
            seen[k].update(v)
        steps = steps + out["steps"]
        with main.db() as conn:
            parts, removed = render_parts(out["answer"], seen, conn)
            items = draft_check(conn, parts, question, steps)
    if removed:
        notes.append(item("", "note", "references_removed", f"{removed} reference{'s' if removed > 1 else ''} the model "
                          "wrote couldn't be traced to Hakiki's records and were removed", True))
    items = sorted(notes + items, key=lambda i: not i["flagged"])
    return {"parts": parts, "removed": removed,
            "check": [{k: i[k] for k in ("raw_text", "kind", "result", "note", "flagged")} for i in items]}


if __name__ == "__main__":
    with main.POOL:
        out = run(" ".join(sys.argv[1:]))
        for s in out["steps"]:
            print(f"  -> {s['tool']}({json.dumps(s['args'])})", file=sys.stderr)
        with main.db() as conn:
            text, invented = render(out["answer"], out["seen"], conn)
    print(text)
    print(f"\n({invented} unverified references removed)" if invented else "", file=sys.stderr)
