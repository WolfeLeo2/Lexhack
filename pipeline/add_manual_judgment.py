"""Add one judgment we hold only as a hand-saved file (PDF or DOCX) because the Internet Archive lacks it: read it
(api/extract.py: text layer, OCR for scans), write the parsed JSON, upsert the judgments row. source_url stays the
official Kenya Law page; where this copy of the text came from goes in the JSON's text_source.

  uv run python -m pipeline.add_manual_judgment $LEXHACK_DATA/raw/manual/FILE.pdf --id ke/judgment/keca/2026/778 \\
      --title "..." --citation "[2026] KECA 778 (KLR)" --court "Court of Appeal" --case-number "Civil Appeal E029 of 2022" \\
      --date 2026-04-24 --judges "A, B, C" --text-url https://where-the-copy-was-downloaded

Then, for that judgment only: extract_citations --judgments FILE, llm_resolve --judgments FILE, and
scripts/sync.sh push (the API reads judgment text from R2).
"""
import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from api import extract
from crawler.config import data_dir, parsed_dir
from crawler.parse import out_path

from .db import apply_schema, connect
from .load_judgments import UPSERT, row

FOOTER = re.compile(r"^\s*Page \d+ of \d+\s*$", re.M)   # page furniture, not the court's words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--id", required=True, help="e.g. ke/judgment/keca/2026/778 (Kenya Law's work URI minus /akn/)")
    ap.add_argument("--title", required=True)
    ap.add_argument("--citation", help="neutral citation, e.g. '[2026] KECA 778 (KLR)'")
    ap.add_argument("--court", required=True)
    ap.add_argument("--case-number", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--judges", default="")
    ap.add_argument("--text-url", help="where this copy of the text was downloaded")
    a = ap.parse_args()

    src = a.file.resolve()
    manual = data_dir() / "raw" / "manual"
    assert src.parent == manual.resolve(), f"keep hand-saved files in {manual}"
    data = src.read_bytes()
    r = extract.read(data, src.name, max_bytes=len(data), max_ocr_pages=60)
    text = re.sub(r"\s+", " ", FOOTER.sub("", r["text"])).strip()
    day = date.fromisoformat(a.date)
    url = f"https://new.kenyalaw.org/akn/{a.id}/eng@{a.date}"
    doc = {"url": url, "kind": "judgment", "work": "/akn/" + a.id, "expression_date": a.date, "title": a.title,
           "metadata": {"Citation": a.title, "Media Neutral Citation": a.citation, "Court": a.court,
                        "Case number": a.case_number, "Judges": a.judges, "Judgment date": f"{day.day} {day:%B %Y}",
                        "Language": "English", "Type": "Judgment"},
           "display_type": "pdf", "source_url": url + "/source", "versions": [a.date], "sections": [], "remarks": [],
           "akn_links": [], "text": text, "retrieved_from": f"manual/{src.name}",
           "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "text_source": {"file": f"raw/manual/{src.name}", "kind": r["kind"], "ocr_pages": r["ocr_pages"],
                           "copy_from": a.text_url, "note": "page footers removed; whitespace collapsed"}}
    path = out_path(parsed_dir(), doc)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    with connect() as conn:
        apply_schema(conn)
        conn.execute(UPSERT, row(doc))
    print(f"{a.id}: {len(text):,} characters, {len(r['ocr_pages'])} OCR pages -> {path.relative_to(data_dir())}")


if __name__ == "__main__":
    main()
