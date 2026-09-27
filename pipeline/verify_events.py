"""Second-pass check of extracted events: is each one THIS court's own holding, on THIS section? One DeepSeek call per
event, thinking mode ON (a narrow question the classifier gets wrong most often). Cached on disk.

  uv run python -m pipeline.verify_events            # check every extracted event not yet checked by this version

Writes citation_events.check_verdict ('pass' | 'fail' | 'unsure') and check_reason. The API hides 'fail' events.
Scored against the blind reviews with `uv run python -m ground_truth.eval_checker`.
"""
import concurrent.futures
import hashlib
import json

from crawler.config import data_dir

from .db import apply_schema, connect
from .deepseek import call_json

MODEL, CHECK_VERSION = "deepseek-flash", 1
BEFORE, AFTER, TAIL = 5000, 3000, 8000

INSTRUCTIONS = """You are checking one claim made about a Kenyan court judgment, for a citator that records what courts
DID to statute sections. Answer two questions strictly from the judgment text.

1. own_holding: Is the quoted passage THIS court's own ruling on the section's validity or meaning, reached by its own
   reasoning or stated as its own declaration or order?
   - "yes": the court itself decides the point (e.g. "we hold…", "I declare…", a formal order declaring the
     section unconstitutional, a reasoned conclusion that the section is valid, or how it must be read).
   - "no": the court applies, follows, restates or is bound by another court's ruling ("guided by…", "as held in…",
     "we are bound by…", re-sentencing in light of an earlier decision), convicts or sentences under the section,
     recites a party's argument or a lower court's finding, or makes a generic order that does not decide the
     section's validity or meaning. An appeal outcome (appeal allowed, sentence set aside) is not by itself a ruling
     on the section.
   - "unsure": genuinely ambiguous.
2. right_section: Is the ruling about the claimed section of the claimed Act? "no" if it is about a different Act
   (e.g. "the Act" refers to another statute with a same-numbered section), a different section, a schedule, or if
   the claimed section is only cited as a procedural basis for the application.

Answer with JSON only: {"own_holding": "yes|no|unsure", "right_section": "yes|no|unsure", "reason": "<one sentence,
citing the paragraph>"}"""


def context(text, quote):
    """The text around the quote (where it sits) plus the end of the judgment (the orders)."""
    at = text.find(quote[:80]) if quote else -1
    parts = []
    if at >= 0:
        parts.append(text[max(0, at - BEFORE):at + len(quote) + AFTER])
    if at < 0 or at + len(quote) + AFTER < len(text) - TAIL:
        parts.append(text[-TAIL:])
    return "\n[...]\n".join(parts)


def check(claim, cache):
    """claim: dict with raw_path, title, court, section, event_type, operative_quote, scope_text.
    -> ('pass'|'fail'|'unsure', reason, whether an API call was made)."""
    text = json.loads((data_dir() / claim["raw_path"]).read_text(encoding="utf-8"))["text"] or ""
    quote = claim["operative_quote"].split(" [...] ")[0]
    prompt = (f"{INSTRUCTIONS}\n\nCLAIM: {claim['title']} ({claim['court']}) did [{claim['event_type']}] to "
              f"[{claim['section']}]" + (f", scope: \"{claim['scope_text']}\"" if claim.get("scope_text") else "")
              + f".\nQuoted as the court's words: \"{claim['operative_quote']}\"\n\nJUDGMENT (excerpts):\n"
              + context(text, quote))
    key = hashlib.sha256(f"verify|{MODEL}|{CHECK_VERSION}|{prompt}".encode()).hexdigest()
    out, fresh = call_json(prompt, cache, key, model=MODEL, thinking=True)
    own, sec = out.get("own_holding"), out.get("right_section")
    verdict = "pass" if own == "yes" and sec == "yes" else "fail" if "no" in (own, sec) else "unsure"
    return verdict, out.get("reason", out.get("error", "")), fresh


def check_many(claims, workers=8):
    cache = data_dir() / "cache" / "llm"
    cache.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda c: check(c, cache), claims))


def main():
    with connect() as conn:
        apply_schema(conn)
        rows = conn.execute("""
            SELECT e.event_id, j.raw_path, j.title, j.court,
                   a.title || ' s.' || p.number || ' (' || coalesce(p.heading, '') || ')', e.event_type,
                   e.operative_quote, coalesce(e.scope_text, '')
            FROM citation_events e JOIN judgments j USING (judgment_id) JOIN provisions p USING (provision_id)
            JOIN acts a USING (act_id)
            WHERE e.method = 'extracted' AND (e.check_version IS DISTINCT FROM %s)""", (CHECK_VERSION,)).fetchall()
    keys = ["event_id", "raw_path", "title", "court", "section", "event_type", "operative_quote", "scope_text"]
    claims = [dict(zip(keys, r)) for r in rows]
    print(f"{len(claims)} extracted events to check", flush=True)
    results = check_many(claims)
    with connect() as conn:
        conn.cursor().executemany("""UPDATE citation_events SET check_verdict = %s, check_reason = %s, check_version = %s
                                     WHERE event_id = %s""",
                                  [(v, r, CHECK_VERSION, c["event_id"]) for c, (v, r, _) in zip(claims, results)])
    counts = {v: sum(r[0] == v for r in results) for v in ("pass", "fail", "unsure")}
    print(f"checked {len(claims)} ({sum(r[2] for r in results)} API calls): {counts}")


if __name__ == "__main__":
    main()
