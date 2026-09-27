"""Event classification (step 6): what did the court DO to each of our sections it cites? -> citation_events
(method='extracted'). One Gemini call per candidate judgment; cached on disk, so re-runs are free.

  uv run python -m pipeline.classify_events --answer-key   # only the answer-key + negatives judgments (for scoring)
  uv run python -m pipeline.classify_events --limit 100    # the first 100 candidates
  uv run python -m pipeline.classify_events                # every candidate judgment not yet classified
  for i in 0 1 2 3 4 5 6 7; do uv run python -m pipeline.classify_events --shard $i/8 & done   # 8 in parallel

Candidates: judgments that cite one of our sections (not Constitution articles: those aren't struck down) and contain
ruling language anywhere (TRIGGER). The model sees the full text and may only name sections the judgment cites (a JSON
enum). Every quote it returns must appear verbatim in the judgment, or the event is dropped; the paragraph is
computed from where the quote sits. Rows are replaced per judgment, so re-running a judgment never duplicates.
Definitions follow README §5.4-5.5. Needs GEMINI_API_KEY.
"""
import argparse
import collections
import csv
import hashlib
import json
import re
import time
from pathlib import Path

import requests

from crawler.config import data_dir, require_env

from .db import apply_schema, connect
from .extract_citations import paragraph_at, paragraph_markers
from .llm_resolve import call

MODEL, PROMPT_VERSION = "deepseek-flash", 5   # "gemini-3.5-flash-lite" also works (via llm_resolve.call)
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
WINDOW, TAIL = 1500, 12_000   # chars kept around each relevant spot, and from the end (the orders)
GT = Path(__file__).resolve().parent.parent / "ground_truth"
TRIGGER = re.compile(
    r"(?i)unconstitutional|null and void|inconsistent with the (?:letter and spirit of the )?constitution|read (?:down|so as)"
    r"|interpreted so as|constitutional validity|constitutionality of|per incuriam|we declare|I declare"
    r"|declaration (?:is|be) (?:hereby )?issued|life imprisonment (?:translates|means)|mandatory (?:nature|minimum)"
    r"|minimum (?:mandatory )?sentence")
EVENT_TYPES = ["declared_unconstitutional", "read_down", "severed", "upheld", "interpreted", "reversed_on_appeal"]
CONFIDENCE = {"high": 0.9, "medium": 0.7, "low": 0.5}

INSTRUCTIONS = """You are building a citator for Kenyan law. Read this judgment and record what THIS court DID to any of the
listed statute sections. Most judgments merely apply or mention sections: then return no event for them.

Record an event only when this court itself makes a holding or order about a section's validity or meaning:
- declared_unconstitutional: the court declares the section (or part of it) unconstitutional / invalid / void.
  A declaration "to the extent that…" is declared_unconstitutional with scope "partial", NOT read_down.
- read_down: the court does not strike the words but holds they must be read more narrowly to be constitutional
  (e.g. a mandatory sentence "must be interpreted so as not to take away the discretion of the court",
  or "life imprisonment translates to thirty years"). A read_down is always scope "partial"; scope_text is the
  court's words saying how the section must be read.
- severed: the court cuts specific words out of the section and keeps the rest.
- upheld: the section's constitutionality was challenged and the court found it constitutional, including holding
  an earlier court's contrary decision per incuriam, and dismissing a challenge to the section ("the allegations
  of unconstitutionality of the impugned sections are without merit").
- interpreted: the court authoritatively settles what the section, or an earlier ruling on it, means or covers,
  without changing its validity (e.g. further directions limiting an earlier ruling).
- reversed_on_appeal: this court, on appeal, sets aside a lower court's decision that had ITSELF declared the section
  unconstitutional, read it down, or ruled on its meaning. An ordinary appeal outcome ("appeal allowed", "conviction
  quashed", "sentence set aside", "award reduced") is NOT a reversal unless the lower court's ruling on the section's
  validity or meaning is what is set aside. Put the lower court's case (name, case number, date) in appeal_from. Record it
  on that section even when the order itself doesn't name the section (e.g. "the judgment of the Court of Appeal is
  set aside and the 20-year sentence reinstated", where the Court of Appeal had held the section's minimum sentence
  not binding). If the court also holds the section valid, record upheld as well.
NOT events — these are the most common mistakes, so check each candidate against them:
- FOLLOWING or APPLYING another court's ruling, even when it changes the outcome. A sentencing appeal that re-sentences
  because Muruatetu, Kilwake, Mwangi, Ayako or any other decision says the sentence is discretionary (or mandatory)
  is not an event on the section: the ruling belongs to that other court. Record an event only if THIS court gives
  its own reasoned holding on the section's validity or meaning, beyond citing and applying the earlier case.
- Generic appellate orders ("all the other findings of the trial court are upheld", "the judgment is affirmed"):
  never an "upheld" event on a section, unless the court itself decided the section's constitutionality.
- A section that is only quoted, recited or used as the basis of a charge, claim or award.
Also not events: convicting or sentencing under a section; quoting or following another court's ruling without making
its own; reciting a party's argument; the court's reasoning that ends in no holding on the section; describing what
an earlier ruling in a DIFFERENT case did or did not cover (e.g. "Muruatetu only considered section 204"). The
exception is further directions in the SAME case, which are "interpreted" events on the sections they limit to.
A holding about a section the court is not asked to rule on (a passing list of other offences) is not an event.

For each event:
- operative_quote: the court's own words that make the order or holding, copied EXACTLY, character for character,
  from the judgment (one to three sentences). Prefer the formal order or the "we hold / we declare" sentence.
- scope: "partial" if the court limits it ("to the extent that…", only one aspect, only a subsection), else "total".
  For upheld/interpreted: the part the court actually ruled on.
- scope_text: the court's exact limiting words when scope is partial, copied EXACTLY; else "".
- subsection: e.g. "8(2)" when the holding is limited to a sub-provision, else "".
- confidence: high if the words are an explicit order or holding, medium if clearly implied, low otherwise."""


def candidates(conn, only):
    rows = conn.execute("""
        SELECT j.judgment_id, j.title, j.court, j.decision_date, j.raw_path,
               array_agg(DISTINCT m.provision_id) AS pids
        FROM judgments j JOIN citation_mentions m USING (judgment_id)
        WHERE m.provision_id IS NOT NULL AND m.provision_id NOT LIKE 'ke/act/constitution/%%'
          AND (%(only)s::text[] IS NULL OR j.judgment_id = ANY(%(only)s))
        GROUP BY 1, 2, 3, 4, 5
        ORDER BY array_position(ARRAY['Supreme Court', 'Court of Appeal', 'High Court'], j.court), j.judgment_id""",
                        {"only": only}).fetchall()
    labels = {pid: (act, num, head) for pid, act, num, head in conn.execute(
        "SELECT p.provision_id, a.title, p.number, p.heading FROM provisions p JOIN acts a USING (act_id)")}
    return rows, labels


def excerpt(text, spots):
    """What the model reads: the opening (parties, what's appealed), WINDOW chars around every citation of a listed
    section and every ruling phrase, and the last TAIL chars (the orders). A small model misses rulings buried in
    a 100k-character judgment; the quotes it returns are still checked against the FULL text."""
    spots = sorted(spots + [m.start() for m in TRIGGER.finditer(text)])
    ranges = [(0, 2000), (max(0, len(text) - TAIL), len(text))] + [(max(0, o - WINDOW), o + WINDOW) for o in spots]
    merged = []
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return "\n[...]\n".join(text[a:b] for a, b in merged)


def build(title, court, ddate, text, sections, spots=()):
    prompt = (f"{INSTRUCTIONS}\n\nJudgment: {title}\nCourt: {court}\nDate: {ddate}\n\nSections this judgment cites "
              "(use these labels exactly):\n" + "\n".join(f"- {s}" for s in sections)
              + f"\n\nJUDGMENT TEXT (excerpts; [...] marks omitted text):\n{excerpt(text, list(spots))}")
    schema = {"type": "OBJECT", "required": ["events"], "properties": {"events": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "required": ["section", "event_type", "scope", "scope_text", "subsection", "operative_quote", "appeal_from",
                     "confidence"],
        "properties": {"section": {"type": "STRING", "enum": sections},
                       "event_type": {"type": "STRING", "enum": EVENT_TYPES},
                       "scope": {"type": "STRING", "enum": ["total", "partial"]},
                       "scope_text": {"type": "STRING"}, "subsection": {"type": "STRING"},
                       "operative_quote": {"type": "STRING"}, "appeal_from": {"type": "STRING"},
                       "confidence": {"type": "STRING", "enum": list(CONFIDENCE)}}}}}}
    return prompt, schema


JSON_SHAPE = """Answer with JSON only, in exactly this shape (an empty list if there are no events):
{"events": [{"section": "<one of the labels above>", "event_type": "<one of: %s>", "scope": "total|partial",
  "scope_text": "", "subsection": "", "operative_quote": "", "appeal_from": "", "confidence": "high|medium|low"}]}"""


def deepseek(prompt, schema, cache):
    """Same contract as llm_resolve.call: (response dict, whether an API call was made); cached by input hash."""
    key = hashlib.sha256(f"{MODEL}|{PROMPT_VERSION}|{json.dumps(schema, sort_keys=True)}|{prompt}".encode()).hexdigest()
    path = cache / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), False
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt + "\n\n" + JSON_SHAPE % ", ".join(EVENT_TYPES)}],
            "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}, "temperature": 0}
    for attempt in range(8):
        wait = min(120, 10 * 2 ** attempt)
        try:
            r = requests.post(DEEPSEEK_URL, json=body, timeout=300,
                              headers={"Authorization": f"Bearer {require_env('DEEPSEEK_API_KEY')}"})
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 402:
            raise SystemExit("DeepSeek balance is empty (HTTP 402): top up; answers so far are cached.")
        if r.status_code in (429, 500, 502, 503):
            print(f"  HTTP {r.status_code}; retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]["content"]
        try:
            out = json.loads(msg)
        except json.JSONDecodeError:
            out = {"events": [], "error": "unparseable", "raw": msg[:2000]}
        path.write_text(json.dumps(out), encoding="utf-8")
        return out, True
    raise RuntimeError("DeepSeek call failed after 8 attempts")


def valid(e, sections):
    """DeepSeek's JSON mode doesn't enforce the schema; Gemini's does. Check every answer the same way."""
    return (isinstance(e, dict) and e.get("section") in sections and e.get("event_type") in EVENT_TYPES
            and e.get("scope") in ("total", "partial") and e.get("confidence") in CONFIDENCE
            and isinstance(e.get("operative_quote"), str))


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def locate(quote, text):
    """(start, end) in norm(text) of the LAST occurrence of quote, ignoring whitespace entirely (models tidy spacing:
    "(a)- (d )" comes back as "(a)-(d )"), or None. Last, because orders restate earlier summaries of the same words.
    Callers store text[start:end], the source's own characters, so stored quotes stay verbatim."""
    t = norm(text)
    keep = [i for i, ch in enumerate(t) if not ch.isspace()]
    q = re.sub(r"\s+", "", quote or "")
    at = "".join(t[i] for i in keep).rfind(q) if q else -1
    return (keep[at], keep[at + len(q) - 1] + 1) if at >= 0 else None


def quote_from_source(quote, text):
    """The source's own words for a quote, or None. A quote shortened with "..." is accepted only if every part is
    verbatim and they appear in order; the parts are rejoined with " [...] ". -> (stored quote, start offset)."""
    parts = [p for p in re.split(r"\s*(?:\.\.\.|…)\s*", quote or "") if p.strip()]
    t, spans = norm(text), []
    for part in parts:
        span = locate(part, text)
        if span is None or (spans and span[0] < spans[-1][1]):
            return None
        spans.append(span)
    return (" [...] ".join(t[a:b] for a, b in spans), spans[0][0]) if spans else None


def classify(row, labels, api_key, cache, stats):
    jid, title, court, ddate, raw_path, pids = row
    text = json.loads((data_dir() / raw_path).read_text(encoding="utf-8"))["text"] or ""
    by_label = {}
    for pid in sorted(pids):
        act, num, head = labels[pid]
        by_label.setdefault(f"{act} s.{num} ({head})", pid)
    with connect() as conn:
        spots = [s for (s,) in conn.execute("SELECT char_start FROM citation_mentions WHERE judgment_id = %s AND "
                                            "provision_id = ANY(%s)", (jid, list(pids)))]
    prompt, schema = build(title, court, ddate, text, list(by_label), spots)
    short = collections.Counter(label.split(" (")[0] for label in by_label)   # models often drop the "(heading)"
    by_label |= {label.split(" (")[0]: pid for label, pid in list(by_label.items()) if short[label.split(" (")[0]] == 1}
    if MODEL.startswith("deepseek"):
        resp, fresh = deepseek(prompt, schema, cache)
    else:
        resp, fresh = call(prompt, schema, api_key, cache, model=MODEL, version=PROMPT_VERSION)
    stats["calls"] += fresh
    ntext, markers = norm(text), paragraph_markers(norm(text))
    out = []
    for e in resp.get("events") or []:
        if not valid(e, by_label):
            stats["dropped_invalid_answer"] += 1
            continue
        for k in ("scope_text", "subsection", "appeal_from"):
            e[k] = e.get(k) or ""
        found = quote_from_source(e["operative_quote"], text)
        if found is None:
            stats["dropped_quote_not_verbatim"] += 1
            continue
        quote, start = found
        scope, scope_span = e["scope"], locate(e["scope_text"], text)
        scope_text = ntext[scope_span[0]:scope_span[1]] if scope_span else ""
        if e["scope_text"].strip() and not scope_span:
            stats["scope_text_not_verbatim"] += 1
        notes = f"{MODEL} v{PROMPT_VERSION}" + (f"; appeal from: {e['appeal_from']}" if e["appeal_from"] else "")
        out.append((by_label[e["section"]], jid, e["event_type"], scope, scope_text or None, e["subsection"] or None,
                    quote, paragraph_at(markers, start), ddate,
                    CONFIDENCE[e["confidence"]], notes))
        stats[e["event_type"]] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answer-key", action="store_true", help="only the judgments in events.csv and negatives.csv")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--shard", default="0/1", help="i/N: this worker takes every N-th candidate, offset i")
    ap.add_argument("--redo", action="store_true", help="also re-run judgments already classified by this model+prompt")
    args = ap.parse_args()
    shard, shards = map(int, args.shard.split("/"))
    api_key = None if MODEL.startswith("deepseek") else require_env("GEMINI_API_KEY")
    cache = data_dir() / "cache" / "llm"
    cache.mkdir(parents=True, exist_ok=True)
    only = None
    if args.answer_key:
        only = sorted({r["judgment_id"] for f in ("events.csv", "negatives.csv")
                       for r in csv.DictReader(open(GT / f, encoding="utf-8"))})
    with connect() as conn:
        apply_schema(conn)
        rows, labels = candidates(conn, only)
    if not args.answer_key:   # the answer-key judgments are always classified, trigger or not, so scoring is fair
        rows = [r for r in rows if TRIGGER.search(
            json.loads((data_dir() / r[4]).read_text(encoding="utf-8"))["text"] or "")]
    rows = rows[:args.limit] if args.limit else rows
    rows = rows[shard::shards]
    if not (args.redo or args.answer_key):
        with connect() as conn:
            done = {j for (j,) in conn.execute("SELECT judgment_id FROM event_runs WHERE model = %s AND prompt_version = %s",
                                               (MODEL, PROMPT_VERSION))}
        rows = [r for r in rows if r[0] not in done]
    print(f"{len(rows)} candidate judgments", flush=True)
    stats = collections.Counter()
    try:
        for n, row in enumerate(rows, 1):
            events = classify(row, labels, api_key, cache, stats)
            with connect() as conn, conn.transaction():
                conn.execute("DELETE FROM citation_events WHERE method = 'extracted' AND judgment_id = %s", (row[0],))
                conn.cursor().executemany("""INSERT INTO citation_events (provision_id, judgment_id, event_type, scope,
                    scope_text, subsection, operative_quote, source_paragraph, effective_date, confidence, notes, method)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'extracted')""", events)
                conn.execute("""INSERT INTO event_runs (judgment_id, model, prompt_version, events) VALUES (%s,%s,%s,%s)
                    ON CONFLICT (judgment_id) DO UPDATE SET model=EXCLUDED.model, prompt_version=EXCLUDED.prompt_version,
                    events=EXCLUDED.events, run_at=now()""", (row[0], MODEL, PROMPT_VERSION, len(events)))
            if n % 25 == 0 or n == len(rows):
                print(f"  {n}/{len(rows)} judgments, {dict(stats)}", flush=True)
    finally:
        print(f"done: {dict(stats)}")


if __name__ == "__main__":
    main()
