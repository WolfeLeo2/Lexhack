"""Parliament's changes to each section, from the reviser's notes in Kenya Law's text ('[Act No. 5 of 2003, s. 2.]').

  uv run python -m pipeline.statutory_events parse    # -> $LEXHACK_DATA/review/statutory/events.json + a summary
  uv run python -m pipeline.statutory_events load     # write them to citation_events (idempotent)

One event per (section, amending instrument): 'repealed_by_statute' when the note says the whole section was repealed or
deleted, else 'amended_by_statute' (a subsection-level deletion is an amendment of the section). The note itself is the
operative_quote, verbatim. They are shown by default (verified_by = 'source:…': a transcription of Kenya Law's own
note, not an inference); the parse itself is not yet benchmarked. The notes give only the amending Act's year, so effective_date is 1 January of that year
and date_precision = 'year'. Corrigenda ('Corr. No. 1 of 2008'), '[Spent]' and cross-references ('[s. 78]') are skipped.
"""
import argparse
import collections
import glob
import hashlib
import json
import re

from crawler.config import data_dir

from .db import connect

OUT = data_dir() / "review" / "statutory"
VERSION = "parser:remarks v1"

# 'Act No. 5 of 2003 , s. 2' | 'ActNo. 19 of 2015' | '[ 5 of 2003 , s. 33' | 'L.N. 427/1963' | 'L.N. 407 1961'
INSTRUMENT = re.compile(r"(?P<verb>(?:Repealed|Deleted)\s+by\s+)?"
                        r"(?:(?:Act\s*No\.?\s*|(?<=\[)\s*)(?P<act>\d+[A-Z]?)\s+of\s+(?P<act_year>\d{4})"
                        r"|L\.\s*N\.\s*(?P<ln>\d+)\s*[/ ]\s*(?P<ln_year>\d{4}))"
                        r"(?:\s*,\s*(?P<where>(?:ss?\.\s*[\w()]+(?:\s*(?:-|and|&)\s*[\w()]+)*)|(?:[\w]+\s+)?Sch\.))?")
SKIP = re.compile(r"^\[\s*(Corr|Corri|Spent|s\.\s*\d)", re.I)


def section_of(eid, eids):
    """The provision a remark belongs to: the longest section eid that the remark's eid starts with."""
    best = None
    for e in eids:
        if (eid == e or eid.startswith(e + "__")) and (best is None or len(e) > len(best)):
            best = e
    return best


def parse():
    with connect() as conn:
        act_of = dict(conn.execute("SELECT raw_path, act_id FROM act_versions").fetchall())
        date_of = dict(conn.execute("SELECT raw_path, version_date::text FROM act_versions").fetchall())
        eids = collections.defaultdict(set)
        texts = {}
        for pid, act, eid in conn.execute("SELECT provision_id, act_id, eid FROM provisions"):
            eids[act].add(eid)
        for pid, text in conn.execute("""SELECT DISTINCT ON (provision_id) provision_id, text FROM provision_texts
                                         JOIN act_versions USING (version_id) ORDER BY provision_id, version_date DESC"""):
            texts[pid] = text
    events, skipped = {}, collections.Counter()
    for f in sorted(glob.glob(str(data_dir() / "parsed" / "act" / "*.json"))):
        rel = str(f).split(str(data_dir()) + "/")[1]
        act = act_of.get(rel)
        if not act:
            skipped["file not loaded"] += 1
            continue
        for r in json.loads(open(f, encoding="utf-8").read())["remarks"]:
            note = re.sub(r"\s+", " ", r["text"]).strip()
            if SKIP.search(note):
                skipped["corrigendum / spent / cross-reference"] += 1
                continue
            sec = section_of(r["eid"], eids[act])
            if not sec:
                skipped["no section (schedule or attachment)"] += 1
                continue
            pid = f"{act}/{sec}"
            below = r["eid"][len(sec):]                     # '' | '__subsec_3__p_2' | '__p_2' | '__wrapup__p_1'
            sub = re.search(r"subsec_(\w+?)(?:__|$)", below)
            found = list(INSTRUMENT.finditer(note))
            if not found:
                skipped["no instrument recognised"] += 1
                continue
            for m in found:
                year = m["act_year"] or m["ln_year"]
                inst = f"Act No. {m['act']} of {year}" if m["act"] else f"L.N. {m['ln']}/{year}"
                repeal = bool(m["verb"]) and not sub
                key = (pid, inst)
                ev = events.get(key)
                if ev is None:
                    ev = events[key] = {
                        "provision_id": pid, "instrument": inst, "year": int(year), "where": (m["where"] or "").strip(),
                        "event_type": "repealed_by_statute" if repeal else "amended_by_statute",
                        "scope": "total" if repeal else "partial",
                        "subsection": f"{sec.rsplit('sec_', 1)[1]}({sub[1]})" if sub else None,
                        "operative_quote": note, "first_seen": date_of[rel], "section_text": texts.get(pid, "")[:300]}
                elif repeal:
                    ev.update(event_type="repealed_by_statute", scope="total", operative_quote=note)
                ev["first_seen"] = min(ev["first_seen"], date_of[rel])
    OUT.mkdir(parents=True, exist_ok=True)
    rows = sorted(events.values(), key=lambda e: (e["provision_id"], e["year"]))
    (OUT / "events.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    c = collections.Counter(e["event_type"] for e in rows)
    print(f"{len(rows)} events on {len({e['provision_id'] for e in rows})} sections: {dict(c)}; skipped {dict(skipped)}")
    return rows


def load():
    rows = json.loads((OUT / "events.json").read_text(encoding="utf-8"))
    with connect() as conn:
        conn.execute("SET lock_timeout = '20s'")
        conn.execute("ALTER TABLE citation_events ADD COLUMN IF NOT EXISTS date_precision TEXT")
        keys = []
        for e in rows:
            key = "S-" + hashlib.sha1(f"{e['provision_id']}|{e['instrument']}".encode()).hexdigest()[:12]
            keys.append(key)
            conn.execute("""
                INSERT INTO citation_events (event_key, provision_id, judgment_id, event_type, scope, subsection,
                    operative_quote, source_paragraph, effective_date, date_precision, method, verified, verified_by, notes)
                VALUES (%s,%s,NULL,%s,%s,%s,%s,%s,make_date(%s,1,1),'year','extracted',true,%s,%s)
                ON CONFLICT (event_key) DO UPDATE SET event_type=EXCLUDED.event_type, scope=EXCLUDED.scope,
                    subsection=EXCLUDED.subsection, operative_quote=EXCLUDED.operative_quote,
                    source_paragraph=EXCLUDED.source_paragraph, effective_date=EXCLUDED.effective_date,
                    date_precision='year', verified=true, verified_by=EXCLUDED.verified_by, notes=EXCLUDED.notes""",
                         (key, e["provision_id"], e["event_type"], e["scope"], e["subsection"], e["operative_quote"],
                          f"{e['instrument']}{', ' + e['where'] if e['where'] else ''}", e["year"], f"source:{VERSION}",
                          f"{VERSION}: {e['instrument']}; in Kenya Law's text from the {e['first_seen']} version"))
        conn.execute("DELETE FROM citation_events WHERE event_key LIKE 'S-%%' AND NOT (event_key = ANY(%s))", (keys,))
        conn.commit()
    print(f"loaded {len(rows)} statutory events")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["parse", "load"])
    parse() if ap.parse_args().cmd == "parse" else load()
