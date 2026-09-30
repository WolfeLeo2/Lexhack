"""Hakiki's research agent: Gemini with the tools in api/tools.py, answers grounded in what the tools returned.

  uv run python -m api.agent "Is section 204 of the Penal Code still good law?"

The model never writes a court's words: it cites [[event:ID]], [[section:ID]], [[judgment:ID]] and render() fills in
the verbatim text from the database. A reference no tool returned is removed and counted (the eval's headline).
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from . import main, tools
from .status import statuses

MODEL, MAX_ROUNDS = "gemini-3.5-flash-lite", 8
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REF = re.compile(r"\[\[(section|event|judgment):([^\]\s]+)\]\]")
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
   provision_id (e.g. ke/act/cap-63/part_II__chp_XVIII__sec_194), never a bare number. Never guess or shorten an ID.
4. If Hakiki doesn't hold something (a case, an Act, a section), say it is not in Hakiki's collection. Hakiki holds
   about 10% of judgments, so never say a case does not exist or is fake.
5. Say whether each ruling was checked by a person (verified_by 'human:...') or by an AI reviewer ('agent:...'); verified_by
   'source:...' means the event was transcribed from Kenya Law's reviser's notes. Never present an unverified lead as
   the status.
6. Report what the sources say. Never advise on the user's own case or tell them what to do; suggest they consult an
   advocate.

Look things up before answering: search_sections when no section number is given, get_section for status and
rulings, find_case for a named case. Answer briefly, in plain English."""


def generate(body, api_key):
    """One generateContent call, cached by request body (temperature 0: same request, same answer)."""
    cache = Path(os.environ["LEXHACK_DATA"]) / "cache" / "agent"   # resolved here: Railway has no LEXHACK_DATA
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for attempt in range(10):   # per-minute quotas can take a minute or two to clear (as pipeline/llm_resolve.call)
        wait = min(120, 10 * 2 ** attempt)
        try:
            r = requests.post(URL.format(model=MODEL), json=body, headers={"x-goog-api-key": api_key}, timeout=180)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 429 and "PerDay" in r.text:
            raise RuntimeError(f"Gemini daily quota exhausted for {MODEL}; answers so far are cached")
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; retrying in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        if ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts"):   # never cache an empty reply
            path.write_text(r.text, encoding="utf-8")
        return data
    raise RuntimeError("Gemini call failed after 10 attempts (network or rate limit)")


def run(question, history=(), api_key=None):
    api_key = api_key or os.environ["GEMINI_API_KEY"]
    contents = [*history, {"role": "user", "parts": [{"text": question}]}]
    steps, seen = [], {"section": set(), "event": set(), "judgment": set()}
    for rnd in range(MAX_ROUNDS + 1):
        body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
                "tools": [{"functionDeclarations": tools.DECLARATIONS}], "generationConfig": {"temperature": 0}}
        if rnd == MAX_ROUNDS:   # out of rounds: answer with what you have
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
        resp = generate(body, api_key)
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
            try:
                out = tools.call(c["name"], args)
                for k, v in out["ids"].items():
                    seen[k].update(v)
                result = out["result"]
            except Exception as e:   # a bad ID or argument goes back to the model to correct
                result = {"error": f"{type(e).__name__}: {e}"}
            steps.append({"tool": c["name"], "args": args, "result": result})
            replies.append({"functionResponse": {"name": c["name"], "response": {"result": result}}})
        contents.append({"role": "user", "parts": replies})
    raise AssertionError("unreachable: the last round has tools disabled")


def refs(answer):
    return REF.findall(answer)


def render(answer, seen, conn):
    """-> (answer with references replaced by database text, number of references no tool returned)."""
    ok = {(k, v) for k, vs in seen.items() for v in vs}
    good = [(k, v) for k, v in refs(answer) if (k, v) in ok]
    ev = {str(r[0]): r[1:] for r in conn.execute(
        """SELECT e.event_id, e.operative_quote, e.source_paragraph, e.verified_by, j.title, j.neutral_citation,
                  j.court, j.source_url FROM citation_events e LEFT JOIN judgments j USING (judgment_id)
           WHERE e.event_id = ANY(%s)""", ([int(v) for k, v in good if k == "event" and v.isdigit()],))}
    sec_ids = [v for k, v in good if k == "section"]
    sec = {r[0]: r[1:] for r in conn.execute(
        """SELECT p.provision_id, a.title, p.number, p.heading FROM provisions p JOIN acts a USING (act_id)
           WHERE p.provision_id = ANY(%s)""", (sec_ids,))}
    status = statuses(conn, list(sec))
    jud = {r[0]: r[1:] for r in conn.execute(
        "SELECT judgment_id, title, neutral_citation, source_url FROM judgments WHERE judgment_id = ANY(%s)",
        ([v for k, v in good if k == "judgment"],))}
    invented = 0

    def sub(m):
        nonlocal invented
        k, v = m.groups()
        if (k, v) in ok and k == "event" and v in ev:
            quote, para, by, title, cite, court, url = ev[v]
            who = next((label for prefix, label in LABELS if (by or "").startswith(prefix)), "unverified")
            src = ", ".join(x for x in (title or "Parliament (Kenya Law reviser's note)", cite, court,
                                        para and f"para {para}") if x)
            return f'"{quote}" ({src}; {who}){f" <{url}>" if url else ""}'
        if (k, v) in ok and k == "section" and v in sec:
            act, number, heading = sec[v]
            return f"{act} s.{number}{f' ({heading})' if heading else ''} [status: {status[v]}]"
        if (k, v) in ok and k == "judgment" and v in jud:
            title, cite, url = jud[v]
            return f"{title}{f' {cite}' if cite else ''}{f' <{url}>' if url else ''}"
        invented += 1
        return "[unverified reference removed]"

    return REF.sub(sub, answer), invented


if __name__ == "__main__":
    with main.POOL:
        out = run(" ".join(sys.argv[1:]))
        for s in out["steps"]:
            print(f"  -> {s['tool']}({json.dumps(s['args'])})", file=sys.stderr)
        with main.db() as conn:
            text, invented = render(out["answer"], out["seen"], conn)
    print(text)
    print(f"\n({invented} unverified references removed)" if invented else "", file=sys.stderr)
