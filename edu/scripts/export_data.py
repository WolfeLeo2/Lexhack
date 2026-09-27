"""Export the demo data for the edu site: the verified answer key, run through the real Kenyan status rules, in the
exact shape of the API's ProvisionStatus response (api/main.py). Re-run whenever events.csv or the rules change.

  uv run python edu/scripts/export_data.py      # from the repo root; writes edu/src/data/{provisions,judgments}.json
"""
import csv
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.main import DISCLAIMER  # noqa: E402
from api.status_ke import resolve  # noqa: E402
from crawler.config import data_dir  # noqa: E402

OUT = ROOT / "edu" / "src" / "data"
COURTS = {"kesc": "Supreme Court", "keca": "Court of Appeal", "kehc": "High Court"}
ACTS = {  # act_id -> (title, AKN work, Kenya Law work URI)
    "ke/act/cap-63": ("Penal Code", "1930_10"),
    "ke/act/cap-63a": ("Sexual Offences Act", "2006_3"),
    "ke/act/cap-411a": ("Kenya Information and Communications Act", "1998_2"),
}
EXTRA = {"ke/act/cap-63": ["203", "296"], "ke/act/cap-63a": ["11"]}   # sections with no recorded rulings, for contrast


def act_files(work):
    return sorted(glob.glob(str(data_dir() / "parsed" / "act" / f"akn_ke_act_{work}_eng@*.json")))


def judgment(jid):
    _, _, court, year, num = jid.split("/")
    path = glob.glob(str(data_dir() / "parsed" / "judgment" / f"akn_ke_judgment_{court}_{year}_{num}_eng@*.json"))[0]
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    m = d["metadata"]
    return {"judgment_id": jid, "title": m.get("Citation") or d["title"], "court": COURTS[court],
            "neutral_citation": m.get("Media Neutral Citation"), "alt_citation": m.get("Alternative citations"),
            "decision_date": d["url"].rsplit("@", 1)[1], "source_url": d["url"]}


def provision(act_id, eid):
    title, work = ACTS[act_id]
    files = act_files(work)
    texts = []
    for f in files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        sec = next((s for s in d["sections"] if s["eid"] == eid), None)
        if sec:
            texts.append((d["expression_date"], sec, d["url"],
                          [r["text"] for r in d["remarks"] if r["eid"] == eid or r["eid"].startswith(eid + "__")]))
    date, sec, url, remarks = texts[-1]
    return {"provision_id": f"{act_id}/{eid}", "act_id": act_id, "act_title": title,
            "number": sec["heading"].split(".", 1)[0], "heading": sec["heading"].split(". ", 1)[-1],
            "text": sec["text"], "version_date": date, "source_url": url,
            # extras beyond the API contract, for teaching: every version we hold, and Kenya Law's own notes
            "versions": [{"date": d, "same_text": s["text"] == sec["text"]} for d, s, _, _ in texts],
            "remarks": remarks}


def eid_for(act_id, number):
    d = json.loads(Path(act_files(ACTS[act_id][1])[-1]).read_text(encoding="utf-8"))
    return next(s["eid"] for s in d["sections"] if s["heading"].split(".", 1)[0] == number)


def main():
    key = list(csv.DictReader(open(ROOT / "ground_truth" / "events.csv", encoding="utf-8")))
    neg = list(csv.DictReader(open(ROOT / "ground_truth" / "negatives.csv", encoding="utf-8")))
    judgments = {jid: judgment(jid) for jid in sorted({r["judgment_id"] for r in key + neg})}
    by_prov = {}
    for r in key:
        by_prov.setdefault(r["provision_id"], []).append(r)
    for act_id, nums in EXTRA.items():
        for n in nums:
            by_prov.setdefault(f"{act_id}/{eid_for(act_id, n)}", [])
    out = []
    for pid, rows in by_prov.items():
        act_id, eid = pid.rsplit("/", 1)
        events = []
        for r in rows:
            j = judgments[r["judgment_id"]]
            events.append({
                "event_id": int(r["event_key"][1:]), "event_key": r["event_key"], "event_type": r["event_type"],
                "scope": r["scope"], "scope_text": r["scope_text"] or None, "subsection": r["subsection"] or None,
                "operative_quote": r["operative_quote"], "source_paragraph": r["source_paragraph"] or None,
                "effective_date": r["effective_date"],
                "affects_event_id": int(r["affects_event"][1:]) if r["affects_event"] else None,
                "court": j["court"], "title": r["case_name"], "neutral_citation": j["neutral_citation"],
                "source_url": r["source_url"], "verified": r["verified"] == "true", "notes": r["notes"]})
        res = resolve(events)
        # affects_event_id is kept (not in the API's Event model) so the site can replay the rules step by step
        out.append({"provision": provision(act_id, eid), "status": res["status"],
                    "summary_events": res["summary_events"], "history": res["history"], "disclaimer": DISCLAIMER})
    out.sort(key=lambda p: (p["provision"]["act_title"], int(p["provision"]["number"])))
    # the demo filing checker's case index: what each judgment is, plus the passages we hold from it
    quotes = {}
    for r in key:
        quotes.setdefault(r["judgment_id"], set()).update(q for q in (r["operative_quote"], r["scope_text"]) if q)
    for jid, j in judgments.items():
        j["passages"] = sorted(quotes.get(jid, []))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "provisions.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "judgments.json").write_text(json.dumps(list(judgments.values()), indent=1, ensure_ascii=False),
                                        encoding="utf-8")
    for p in out:
        print(f"{p['provision']['act_title']} s.{p['provision']['number']}: {p['status']}")


if __name__ == "__main__":
    main()
