"""Text for the judgments we hold only as an HTML shell ("display_type": "pdf", no text): fetch each one's source file
(PDF or DOCX) from the Internet Archive, read it (api/extract.py: text layer, OCR for scanned pages), and write the text
into its parsed JSON.

  uv run python -m pipeline.fetch_sources fetch    # Archive -> $LEXHACK_DATA/raw/sources/ (resumable, ~1 request/s)
  uv run python -m pipeline.fetch_sources parse    # files -> parsed JSON "text" + judgments.has_full_text; writes
                                                   # $LEXHACK_DATA/raw/sources/updated.txt (the judgment ids)
Then, for those judgments only:
  uv run python -m pipeline.extract_citations --judgments $LEXHACK_DATA/raw/sources/updated.txt
  uv run python -m pipeline.llm_resolve --judgments $LEXHACK_DATA/raw/sources/updated.txt
"""
import json
import sys
import time

import requests

from api import extract
from crawler.config import data_dir
from pipeline.db import connect

UA = "LexHack research crawler (contact: iansmith@gmail.com)"
CDX = "https://web.archive.org/cdx/search/cdx"
PREFER = ("application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def out_dir():
    d = data_dir() / "raw" / "sources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def todo(conn):
    return conn.execute("""SELECT judgment_id, source_url, raw_path FROM judgments
                           WHERE NOT has_full_text AND duplicate_of IS NULL ORDER BY judgment_id""").fetchall()


def slug(jid):
    return jid.replace("/", "_")


def fetch():
    index_path = out_dir() / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    with connect() as conn:
        rows = todo(conn)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for n, (jid, page_url, _) in enumerate(rows, 1):
        if jid in index:
            continue
        try:
            r = s.get(CDX, params={"url": page_url.rstrip("/") + "/source", "matchType": "prefix",
                                   "filter": "statuscode:200", "fl": "timestamp,original,mimetype", "output": "json"},
                      timeout=60)
            hits = [dict(zip(("timestamp", "original", "mimetype"), h)) for h in (r.json()[1:] if r.text.strip() else [])]
            hits = sorted((h for h in hits if h["mimetype"] in PREFER), key=lambda h: (PREFER.index(h["mimetype"]),
                                                                                      -int(h["timestamp"])))
            if not hits:
                index[jid] = {"missing": True}
            else:
                h = hits[0]
                time.sleep(1)
                body = s.get(f"https://web.archive.org/web/{h['timestamp']}id_/{h['original']}", timeout=120).content
                if not body.startswith((b"%PDF", b"PK\x03\x04")):   # the Archive sent a page of its own, not the file
                    index[jid] = {**h, "bad_download": True}
                    index_path.write_text(json.dumps(index, indent=1))
                    continue
                ext = "pdf" if h["mimetype"] == PREFER[0] else "docx"
                (out_dir() / f"{slug(jid)}.{ext}").write_bytes(body)
                index[jid] = {**h, "file": f"{slug(jid)}.{ext}", "bytes": len(body)}
        except (requests.RequestException, ValueError) as e:   # network or a bad CDX reply: retried on the next run
            print(f"  {jid}: {e!r:.100}", flush=True)
            continue
        index_path.write_text(json.dumps(index, indent=1))
        time.sleep(1)
        if n % 25 == 0:
            print(f"  {n}/{len(rows)}: {sum('file' in v for v in index.values())} fetched, "
                  f"{sum(v.get('missing', False) for v in index.values())} not archived", flush=True)
    print(f"done: {sum('file' in v for v in index.values())} fetched, "
          f"{sum(v.get('missing', False) for v in index.values())} not archived, of {len(rows)}")


def parse():
    index = json.loads((out_dir() / "index.json").read_text())
    updated, stats = [], {"text layer": 0, "ocr": 0, "unreadable": 0}
    with connect() as conn:
        rows = {jid: raw for jid, _, raw in todo(conn)}
        for jid, meta in sorted(index.items()):
            if "file" not in meta or jid not in rows:
                continue
            data = (out_dir() / meta["file"]).read_bytes()
            try:
                r = extract.read(data, meta["file"], max_bytes=len(data), max_ocr_pages=10_000)
            except extract.ExtractError as e:
                stats["unreadable"] += 1
                print(f"  {jid}: {e}", flush=True)
                continue
            if r["kind"] not in ("pdf", "docx"):   # a saved Archive page, not the judgment's file
                stats["unreadable"] += 1
                print(f"  {jid}: not a PDF or DOCX", flush=True)
                continue
            path = data_dir() / rows[jid]
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["text"] = r["text"]
            doc["text_source"] = {"file": f"raw/sources/{meta['file']}", "archived": meta["timestamp"],
                                  "kind": r["kind"], "ocr_pages": r["ocr_pages"]}
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            conn.execute("UPDATE judgments SET has_full_text = true WHERE judgment_id = %s", (jid,))
            stats["ocr" if r["ocr_pages"] else "text layer"] += 1
            updated.append(jid)
        conn.commit()
    (out_dir() / "updated.txt").write_text("\n".join(updated))
    print(f"parsed {len(updated)} judgments: {stats}")


if __name__ == "__main__":
    {"fetch": fetch, "parse": parse}[sys.argv[1]]()
