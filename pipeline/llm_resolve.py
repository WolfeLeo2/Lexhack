"""LLM pass for citations the regex couldn't tie to a law: a bare "section 39", or "the Act" with no Act named
before it. The model picks, for each one, a law from those named in the same judgment, or says 'unknown' /
'not_a_citation'. Resolved rows are updated in place (method='llm', llm_model = the model that answered).

  uv run python -m pipeline.llm_resolve                       # all pending judgments, highest value first
  uv run python -m pipeline.llm_resolve --limit 200           # the first 200 judgments
  0..7 | % { Start-Process uv -ArgumentList "run python -m pipeline.llm_resolve --shard $_/8" -NoNewWindow }

Backends: DeepSeek (default, BACKEND; needs DEEPSEEK_API_KEY) or Gemini (--model gemini-3.5-flash-lite; needs
GEMINI_API_KEY). Gemini's JSON mode enforces the allowed laws as an enum; DeepSeek's doesn't, so the prompt lists them
and every answer is validated (anything not on the list counts as 'unknown'). A chunk that already has a cached Gemini
answer keeps it, so the first run's Gemini work is never redone or repaid.

Every response is cached on disk by input hash ($LEXHACK_DATA/cache/llm/), so re-runs cost nothing and a stopped run
resumes where it left off. Re-running pipeline.extract_citations rebuilds all mention rows; run this afterwards to
re-apply the cached answers.
"""
import argparse
import hashlib
import json
import os
import re
import time

import psycopg
import requests

from crawler.config import data_dir, require_env

from .deepseek import call_json


def connect():
    """db.connect(), but a connection that dies silently (wifi drop) errors within ~1-2 min instead of hanging forever:
    TCP keepalives, a connect timeout, and a per-statement timeout. The retry loop in main() then takes over."""
    url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ["DATABASE_URL"]
    return psycopg.connect(url, connect_timeout=20, keepalives=1, keepalives_idle=30, keepalives_interval=10,
                           keepalives_count=3, options="-c statement_timeout=120000")
from .extract_citations import CANONICAL, NAMED_ACT, REPEALED_CONSTITUTION, canonical, pick_provision, provision_lookup

MODEL, PROMPT_VERSION = "gemini-3.5-flash-lite", 1   # call()'s defaults; classify_events reuses call() with its own
BACKEND, DEEPSEEK_VERSION = "deepseek-flash", 1      # the default resolver, and the version of its JSON_SHAPE suffix
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
CHUNK, BEFORE, AFTER = 25, 900, 150
UNRESOLVED = (None, "the Act", "the Code")
UNKNOWN, NOT_CITATION = "unknown", "not_a_citation"
ARTICLE = re.compile(r"(?i)\barts?\b|\barticles?\b")
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


def asked(m):
    """Is this mention part of the question? Rows the LLM already resolved stay in it, so a re-run builds the same
    prompt as the first run and hits the cache instead of re-asking about the leftovers."""
    return m["act_ref"] in UNRESOLVED or m.get("method") == "llm"


def options(text, mentions):
    """The laws the judgment names, canonicalised, plus both Constitutions (LLM answers excluded, for the same reason)."""
    names = {m["act_ref"] for m in mentions if not asked(m)}
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


JSON_SHAPE = """Allowed values for "law" (copy one exactly):
%s

Answer with JSON only, in exactly this shape, one entry per numbered excerpt:
{"answers": [{"id": 0, "law": "<one allowed value>", "confidence": "high|medium|low"}]}"""


def cache_key(prompt, schema, model, version):
    return hashlib.sha256(f"{model}|{version}|{json.dumps(schema, sort_keys=True)}|{prompt}".encode()).hexdigest()


def deepseek(prompt, schema, allowed, cache, model=BACKEND):
    """Same contract as call(): (response dict, whether an API call was made); cached by input hash."""
    listing = "\n".join(f"- {a}" for a in allowed + [UNKNOWN, NOT_CITATION])
    out, fresh = call_json(prompt + "\n\n" + JSON_SHAPE % listing, cache,
                           cache_key(prompt, schema, model, DEEPSEEK_VERSION), model=model)
    return ({"answers": []} if "error" in out else out), fresh


def _loose(name):
    return re.sub(r"[,\s]+\d{4}$", "", re.sub(r"^the\s+", "", re.sub(r"\s+", " ", name.strip().lower())))


def valid_law(law, allowed):
    """The allowed value an answer means, or None. DeepSeek doesn't enforce the enum, and sometimes writes a name a
    little differently ("the Penal Code", "Evidence Act, 1963"): accept that only when it matches exactly one option."""
    options = allowed + [UNKNOWN, NOT_CITATION]
    if law in options:
        return law
    if not isinstance(law, str):
        return None
    hits = [o for o in options if _loose(o) == _loose(law)]
    return hits[0] if len(hits) == 1 else None


def call(prompt, schema, api_key, cache, model=MODEL, version=PROMPT_VERSION):
    path = cache / f"{cache_key(prompt, schema, model, version)}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), False
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0}}
    for attempt in range(10):   # per-minute quotas can take a minute or two to clear
        wait = min(120, 10 * 2 ** attempt)
        try:
            r = requests.post(URL.replace(MODEL, model), json=body, headers={"x-goog-api-key": api_key}, timeout=180)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 429 and "PerDay" in r.text:
            raise SystemExit(f"Gemini daily quota exhausted for {model}. Re-run tomorrow; answers so far are cached.")
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        out = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        path.write_text(json.dumps(out), encoding="utf-8")
        return out, True
    raise RuntimeError("Gemini call failed after 10 attempts (network or rate limit)")


def resolve_judgment(title, text, mentions, api_key, cache, model=BACKEND, reuse_gemini=True, stats=None):
    """mentions: dicts with char_start, char_end, act_ref (all of the judgment's mentions, for the options).
    model: BACKEND (DeepSeek) or a Gemini model. reuse_gemini: a chunk with a cached answer from the first (Gemini) run
    keeps it instead of asking `model`; scoring turns this off to measure one model at a time.
    -> ({(char_start, char_end): (law, confidence, model that answered)} for the unresolved spans, API calls made)."""
    spans = sorted({(m["char_start"], m["char_end"]) for m in mentions if asked(m)})
    allowed, out, calls = options(text, mentions), {}, 0
    stats = stats if stats is not None else {}
    for i in range(0, len(spans), CHUNK):
        chunk = spans[i:i + CHUNK]
        prompt, schema = build_prompt(title, text, chunk, allowed)
        gemini_cached = (cache / f"{cache_key(prompt, schema, MODEL, PROMPT_VERSION)}.json").exists()
        if model.startswith("deepseek") and not (reuse_gemini and gemini_cached):
            resp, fresh, used = *deepseek(prompt, schema, allowed, cache, model), model
        else:
            gemini = MODEL if gemini_cached and reuse_gemini else model
            resp, fresh = call(prompt, schema, api_key, cache, model=gemini)
            used = gemini
        calls += fresh
        for a in resp.get("answers") or []:
            if not isinstance(a, dict) or not isinstance(a.get("id"), int) or not 0 <= a["id"] < len(chunk):
                stats["invalid_answer"] = stats.get("invalid_answer", 0) + 1
                continue
            law, conf = valid_law(a.get("law"), allowed), a.get("confidence")
            s, e = chunk[a["id"]]
            if law == REPEALED_CONSTITUTION and ARTICLE.search(text[s:e]):
                law = None   # the repealed Constitution had sections, not Articles (the same rule as the regex)
            if law is None or conf not in CONFIDENCE:   # off the list, or malformed: treat as unknown
                stats["invalid_answer"] = stats.get("invalid_answer", 0) + 1
                law, conf = UNKNOWN, "low"
            out[chunk[a["id"]]] = (law, conf, used)
    return out, calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="judgments to process")
    ap.add_argument("--shard", default="0/1", help="i/N: this worker takes every N-th judgment, offset i")
    ap.add_argument("--model", default=BACKEND, help=f"{BACKEND} (default) or a Gemini model, e.g. {MODEL}")
    args = ap.parse_args()
    shard, shards = map(int, args.shard.split("/"))
    api_key = None if args.model.startswith("deepseek") else require_env("GEMINI_API_KEY")
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
    todo = todo[shard::shards]   # shards never share a judgment, so never update the same rows
    print(f"{len(todo)} judgments with unresolved mentions (shard {args.shard}, {args.model})", flush=True)

    stats = {"calls": 0, "resolved": 0, "unknown": 0, "not_citation": 0, "invalid_answer": 0}
    try:
        for n, (jid, title, raw_path, ddate, _) in enumerate(todo, 1):
            for attempt in range(8):   # a network drop: wait and retry the same judgment (~10 min in all)
                try:
                    resolve_one(jid, title, raw_path, ddate, lookup, api_key, cache, args.model, stats)
                    break
                except psycopg.Error as e:   # dropped/idle-timed-out connections surface as several error classes
                    wait = min(120, 10 * 2 ** attempt)
                    print(f"  database error on {jid} ({str(e).splitlines()[0][:80]}); retrying in {wait}s", flush=True)
                    time.sleep(wait)
            else:   # still down: skip it; a re-run picks the judgment up again (its answers are cached)
                stats["skipped_db_error"] = stats.get("skipped_db_error", 0) + 1
            if n % 50 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} judgments, {stats}", flush=True)
    finally:
        print(f"done: {stats}")


def resolve_one(jid, title, raw_path, ddate, lookup, api_key, cache, model, stats):
    """Resolve one judgment's unresolved mentions and write the answers (only rows still unresolved change)."""
    with connect() as conn:
        rows = conn.execute("""SELECT mention_id, char_start, char_end, act_ref, section_ref, method
                               FROM citation_mentions WHERE judgment_id = %s""", (jid,)).fetchall()
    mentions = [dict(zip(("mention_id", "char_start", "char_end", "act_ref", "section_ref", "method"), r)) for r in rows]
    text = json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or ""
    answers, calls = resolve_judgment(title, text, mentions, api_key, cache, model, stats=stats)
    stats["calls"] += calls
    updates = []
    for m in mentions:
        law, conf, used = answers.get((m["char_start"], m["char_end"]), (None, None, None))
        if m["act_ref"] not in UNRESOLVED or law is None:
            continue
        if law == UNKNOWN:
            stats["unknown"] += 1
        elif law == NOT_CITATION:
            stats["not_citation"] += 1   # left unresolved; recorded in the cache
        else:
            act_ref, slug = canonical(law)
            pid = pick_provision(lookup, slug, m["section_ref"], ddate) if slug else None
            updates.append((act_ref, pid, CONFIDENCE[conf], used, m["mention_id"]))
            stats["resolved"] += 1
    if updates:
        with connect() as conn:
            conn.cursor().executemany("""UPDATE citation_mentions SET act_ref = %s, provision_id = %s,
                confidence = %s, llm_model = %s, method = 'llm' WHERE mention_id = %s""", updates)


if __name__ == "__main__":
    main()
