"""LLM pass for citations the regex couldn't tie to a law: a bare "section 39", or "the Act" with no Act named
before it. Gemini picks, for each one, a law from those named in the same judgment (a JSON enum, so it can't invent
one), or says 'unknown' / 'not_a_citation'. Resolved rows are updated in place (method='llm').

  uv run python -m pipeline.llm_resolve               # all pending judgments, highest value first
  uv run python -m pipeline.llm_resolve --limit 200   # the first 200 judgments

Every response is cached on disk by input hash ($LEXHACK_DATA/cache/llm/), so re-runs cost nothing and a run stopped
by the daily quota resumes where it left off. Re-running pipeline.extract_citations rebuilds all mention rows; run
this afterwards to re-apply the cached answers. Needs GEMINI_API_KEY in .env.
"""
import argparse
import hashlib
import json
import re
import time

import requests

from crawler.config import data_dir, require_env

from .db import connect
from .extract_citations import CANONICAL, NAMED_ACT, REPEALED_CONSTITUTION, canonical, pick_provision, provision_lookup

MODEL, PROMPT_VERSION = "gemini-3.5-flash-lite", 1
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
CHUNK, BEFORE, AFTER = 25, 900, 150
UNRESOLVED = (None, "the Act", "the Code")
UNKNOWN, NOT_CITATION = "unknown", "not_a_citation"
CONFIDENCE = {"high": 0.8, "medium": 0.6, "low": 0.4}

INSTRUCTIONS = """You are resolving legal citations in a judgment of a Kenyan court.
Each numbered excerpt below contains one citation marked ⟦like this⟧ that does not name its law. Using the excerpt,
decide which law it is a section or article of, and choose exactly one option from the allowed list.
- "the Act", "the said Act", "the Code" or a bare "section N" means the law the passage is discussing: look for where
  it was named or defined (e.g. "the Arbitration Act (the Act)").
- In a judgment applying the pre-2010 Constitution, "section N of the Constitution" is "Constitution (repealed)".
- Choose "not_a_citation" if the marked text does not cite a law at all (a section of a report, book, contract,
  judgment, or a sum of money).
- Choose "unknown" if the excerpt does not make the law clear. Do not guess.
- confidence: "high" if the excerpt names or defines the law, "medium" if it is clearly implied, "low" otherwise."""


def options(text, mentions):
    """The laws the judgment names, canonicalised, plus both Constitutions."""
    names = {m["act_ref"] for m in mentions if m["act_ref"] not in UNRESOLVED}
    for n in NAMED_ACT.finditer(text):
        name = re.split(r"\b[Tt]he\s+", n.group(0))[-1]
        if name not in ("Act", "Code"):
            names.add(canonical(name)[0])
    names |= {CANONICAL["constitution"], REPEALED_CONSTITUTION}
    return sorted(names)


def build_prompt(title, text, spans, allowed):
    parts = [INSTRUCTIONS, f"\nJudgment: {title}\n"]
    for i, (s, e) in enumerate(spans):
        ctx = text[max(0, s - BEFORE):s] + "⟦" + text[s:e] + "⟧" + text[e:e + AFTER]
        parts.append(f"[{i}] ..." + re.sub(r"\s+", " ", ctx) + "...")
    return "\n".join(parts), {
        "type": "OBJECT", "required": ["answers"],
        "properties": {"answers": {"type": "ARRAY", "items": {
            "type": "OBJECT", "required": ["id", "law", "confidence"],
            "properties": {"id": {"type": "INTEGER"},
                           "law": {"type": "STRING", "enum": allowed + [UNKNOWN, NOT_CITATION]},
                           "confidence": {"type": "STRING", "enum": list(CONFIDENCE)}}}}}}


def call(prompt, schema, api_key, cache):
    key = hashlib.sha256(f"{MODEL}|{PROMPT_VERSION}|{json.dumps(schema, sort_keys=True)}|{prompt}".encode()).hexdigest()
    path = cache / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), False
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0}}
    for attempt in range(10):   # per-minute quotas can take a minute or two to clear
        wait = min(120, 10 * 2 ** attempt)
        try:
            r = requests.post(URL, json=body, headers={"x-goog-api-key": api_key}, timeout=180)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 429 and "PerDay" in r.text:
            raise SystemExit(f"Gemini daily quota exhausted for {MODEL}. Re-run tomorrow; answers so far are cached.")
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        out = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        path.write_text(json.dumps(out), encoding="utf-8")
        return out, True
    raise RuntimeError("Gemini call failed after 10 attempts (network or rate limit)")


def resolve_judgment(title, text, mentions, api_key, cache):
    """mentions: dicts with char_start, char_end, act_ref (all of the judgment's mentions, for the options).
    -> ({(char_start, char_end): (law, confidence)} for the unresolved spans, number of API calls made)."""
    spans = sorted({(m["char_start"], m["char_end"]) for m in mentions if m["act_ref"] in UNRESOLVED})
    allowed, out, calls = options(text, mentions), {}, 0
    for i in range(0, len(spans), CHUNK):
        chunk = spans[i:i + CHUNK]
        prompt, schema = build_prompt(title, text, chunk, allowed)
        resp, fresh = call(prompt, schema, api_key, cache)
        calls += fresh
        for a in resp.get("answers", []):
            if 0 <= a.get("id", -1) < len(chunk):
                out[chunk[a["id"]]] = (a["law"], a["confidence"])
    return out, calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="judgments to process")
    args = ap.parse_args()
    api_key = require_env("GEMINI_API_KEY")
    cache = data_dir() / "cache" / "llm"
    cache.mkdir(parents=True, exist_ok=True)

    with connect() as conn:   # don't hold a connection open while calling the API (Neon drops idle ones)
        lookup = provision_lookup(conn)
        # judgments with unresolved mentions; those that also cite a held Act (not the Constitution) first
        todo = conn.execute("""
            SELECT j.judgment_id, j.title, j.raw_path, j.decision_date,
                   bool_or(m.provision_id IS NOT NULL AND m.provision_id NOT LIKE 'ke/act/constitution/%') AS held
            FROM judgments j JOIN citation_mentions m USING (judgment_id)
            GROUP BY 1, 2, 3, 4
            HAVING bool_or(m.method = 'regex' AND (m.act_ref IS NULL OR m.act_ref IN ('the Act', 'the Code')))
            ORDER BY held DESC, j.judgment_id""").fetchall()
    todo = todo[:args.limit] if args.limit else todo
    print(f"{len(todo)} judgments with unresolved mentions", flush=True)

    stats = {"calls": 0, "resolved": 0, "unknown": 0, "not_citation": 0}
    try:
        for n, (jid, title, raw_path, ddate, _) in enumerate(todo, 1):
            with connect() as conn:
                rows = conn.execute("""SELECT mention_id, char_start, char_end, act_ref, section_ref FROM citation_mentions
                                       WHERE judgment_id = %s""", (jid,)).fetchall()
            mentions = [dict(zip(("mention_id", "char_start", "char_end", "act_ref", "section_ref"), r)) for r in rows]
            text = json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or ""
            answers, calls = resolve_judgment(title, text, mentions, api_key, cache)
            stats["calls"] += calls
            updates = []
            for m in mentions:
                law, conf = answers.get((m["char_start"], m["char_end"]), (None, None))
                if m["act_ref"] not in UNRESOLVED or law is None:
                    continue
                if law == UNKNOWN:
                    stats["unknown"] += 1
                elif law == NOT_CITATION:
                    stats["not_citation"] += 1   # left unresolved; recorded in the cache
                else:
                    act_ref, slug = canonical(law)
                    pid = pick_provision(lookup, slug, m["section_ref"], ddate) if slug else None
                    updates.append((act_ref, pid, CONFIDENCE[conf], m["mention_id"]))
                    stats["resolved"] += 1
            if updates:
                with connect() as conn:
                    conn.cursor().executemany("""UPDATE citation_mentions SET act_ref = %s, provision_id = %s,
                        confidence = %s, method = 'llm' WHERE mention_id = %s""", updates)
            if n % 50 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} judgments, {stats}", flush=True)
    finally:
        print(f"done: {stats}")


if __name__ == "__main__":
    main()
