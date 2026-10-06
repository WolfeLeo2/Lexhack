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

from . import main, tools
from .status import RULES, load_events_many, statuses, with_leads

MODEL, MAX_ROUNDS = "gemini-3.5-flash-lite", 8
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REF = re.compile(r"\[\[(section|event|judgment):([^\]\s]+)\]\]")
ACT = re.compile(r"\[\[act:\s*([^\]]+?)\s*\]\]")   # not a reference kind; naming a held Act is allowed (render_parts)
BRACKETS = re.compile(r"\[\[[^\]]*\]\]")   # anything in [[...]]: a REF, or a malformed one like [[event:1, 2]]
LABELS = [("human:", "checked by a person"), ("agent:", "checked by an AI reviewer"),
          ("source:", "from Kenya Law's reviser's note")]

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
5. Say whether each ruling was checked by a person (verified_by 'human:...') or by an AI reviewer ('agent:...'); verified_by
   'source:...' means the event was transcribed from Kenya Law's reviser's notes. Never present an unverified lead as
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
which one they mean; don't describe any of them as the case. When find_section lists
candidates for a section renumbered between versions, report both IDs and say which one carries the rulings.
Answer briefly, in plain English."""


def generate(body, api_key, attempts=10):
    """One generateContent call, cached by request body (temperature 0: same request, same answer)."""
    data_dir = os.environ.get("LEXHACK_DATA")   # unset on Railway: no disk cache there
    path = None
    if data_dir:
        cache = Path(data_dir) / "cache" / "agent"
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / f"{hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}.json"
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for attempt in range(attempts):   # per-minute quotas can take a minute or two to clear (as pipeline/llm_resolve.call)
        wait = min(120, 10 * 2 ** attempt)
        try:
            r = requests.post(URL.format(model=MODEL), json=body, headers={"x-goog-api-key": api_key}, timeout=180)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", file=sys.stderr, flush=True)
            if attempt + 1 < attempts:
                time.sleep(wait)
            continue
        if r.status_code == 429 and "PerDay" in r.text:
            raise RuntimeError(f"Gemini daily quota exhausted for {MODEL}; answers so far are cached")
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; retrying in {wait}s", file=sys.stderr, flush=True)
            if attempt + 1 < attempts:
                time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        if path and ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts"):   # never cache an empty reply
            path.write_text(r.text, encoding="utf-8")
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
            "check_text": lambda: "Checking the citations in the text"}.get(name, lambda: "Looking things up")()


def run(question, history=(), api_key=None, on_step=None, attempts=10):
    """attempts: Gemini tries per call (the chat passes fewer: it has a deadline)."""
    api_key = api_key or os.environ["GEMINI_API_KEY"]
    contents = [*history, {"role": "user", "parts": [{"text": question}]}]
    steps, seen = [], {"section": set(), "event": set(), "judgment": set()}
    for rnd in range(MAX_ROUNDS + 1):
        body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
                "tools": [{"functionDeclarations": tools.DECLARATIONS}], "generationConfig": {"temperature": 0}}
        if rnd == MAX_ROUNDS:   # out of rounds: answer with what you have
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
        resp = generate(body, api_key, attempts=attempts)
        cand = (resp.get("candidates") or [{}])[0]
        content = cand.get("content")
        if not content or not content.get("parts"):
            raise RuntimeError(f"Gemini returned no content (finishReason {cand.get('finishReason')}, "
                               f"promptFeedback {resp.get('promptFeedback')})")
        contents.append(content)   # unchanged: Gemini 3.x thought signatures must come back as sent
        calls = [p["functionCall"] for p in content["parts"] if "functionCall" in p]
        if not calls:
            answer = "".join(p.get("text", "") for p in content["parts"] if not p.get("thought"))
            return {"answer": answer.strip(), "steps": steps, "seen": {k: sorted(v) for k, v in seen.items()},
                    "contents": contents}
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


def refs(answer):
    return [ref(t) for t in BRACKETS.findall(answer)]


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
                    "checked_by": next((label for prefix, label in LABELS if (by or "").startswith(prefix)), "unverified"),
                    "state": None if st == "in effect" else st, "url": url}
        if (k, v) in ok and k == "section" and v in sec:
            act, number, heading = sec[v]
            return {"kind": "section", "provision_id": v, "act": act, "number": number, "heading": heading,
                    "status": status[v]}
        if (k, v) in ok and k == "judgment" and v in jud:
            title, cite, url = jud[v]
            return {"kind": "case", "judgment_id": v, "title": title, "citation": cite, "url": url}
        return {"kind": "removed"}

    parts, at = [], 0
    for m in BRACKETS.finditer(answer):
        if m.start() > at:
            parts.append({"kind": "text", "text": answer[at:m.start()]})
        parts.append(part(m.group()))
        at = m.end()
    if at < len(answer):
        parts.append({"kind": "text", "text": answer[at:]})
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


if __name__ == "__main__":
    with main.POOL:
        out = run(" ".join(sys.argv[1:]))
        for s in out["steps"]:
            print(f"  -> {s['tool']}({json.dumps(s['args'])})", file=sys.stderr)
        with main.db() as conn:
            text, invented = render(out["answer"], out["seen"], conn)
    print(text)
    print(f"\n({invented} unverified references removed)" if invented else "", file=sys.stderr)
