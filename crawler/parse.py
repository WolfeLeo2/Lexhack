"""Parser: WARC records -> normalised JSON in $LEXHACK_DATA/parsed/. Never touches the network.

  uv run python -m crawler.parse          re-parse every stored 200 response
"""
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from pypdf import PdfReader

from . import config
from .config import origin
from .fetcher import work_of
from .frontier import Frontier
from .storage import read_record

VERSION_RE = re.compile(r"/[a-z]{3}@(\d{4}-\d{2}-\d{2})$")


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse_html(url, kind, html):
    soup = BeautifulSoup(html, "lxml")
    for b in soup.select("button"):
        b.decompose()
    meta = {}
    dl = soup.select_one("dl.document-metadata-list")
    if dl:
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            meta[clean(dt.get_text())] = clean(dd.get_text(" ")) if dd else None
    content = soup.select_one("div.document-content")
    display = content.get("data-display-type") if content else None
    if content:
        for n in content.select("#navigation-content, nav, script, style"):
            n.decompose()
    body = content or soup
    akn = body.select_one(".akn-akomaNtoso, la-akoma-ntoso") or body

    def eid_of(tag):
        p = tag if tag.has_attr("data-eid") else tag.find_parent(attrs={"data-eid": True})
        return p["data-eid"] if p else None

    links = [urljoin(url, a["href"]) for a in body.find_all("a", href=True) if "/akn/" in a["href"]]
    h1 = soup.find("h1")
    own = m.group(1) if (m := VERSION_RE.search(urlsplit(url).path)) else None
    doc = {
        "url": url,
        "kind": kind,
        "work": work_of(url),
        "expression_date": own,
        "title": clean(h1.get_text()) if h1 else None,
        "metadata": meta,
        "display_type": display,
        "source_url": next((urljoin(url, a["href"]) for a in soup.find_all("a", href=True)
                            if re.search(r"/source(\.\w+)?$", a["href"])), None),
        "versions": sorted({m.group(1) for a in soup.find_all("a", href=True)
                            if work_of(urljoin(url, a["href"])) == work_of(url)
                            and (m := VERSION_RE.search(urlsplit(urljoin(url, a["href"])).path))} | ({own} if own else set())),
        "sections": [{"eid": s["data-eid"],
                      "heading": clean(s.find(re.compile("^h[1-6]$")).get_text()) if s.find(re.compile("^h[1-6]$")) else None,
                      "text": clean(s.get_text(" "))}
                     for s in akn.select(".akn-section[data-eid]")],
        "remarks": [{"eid": eid_of(r), "text": clean(r.get_text(" "))} for r in akn.select(".akn-remark")],
        "akn_links": links,
        "text": clean(akn.get_text(" ")) if display != "pdf" else "",
    }
    return doc


def parse_pdf(url, data):
    try:
        text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    except Exception as e:   # corrupt/encrypted PDF: record, don't crash the whole run
        return {"url": url, "kind": "source", "work": work_of(url), "error": repr(e), "text": ""}
    return {"url": url, "kind": "source", "work": work_of(url), "text": text}


def out_path(parsed, doc):
    slug = re.sub(r"[^A-Za-z0-9@._-]+", "_", urlsplit(doc["url"]).path.strip("/"))[:200] or "root"
    d = parsed / doc["kind"]
    d.mkdir(exist_ok=True)
    return d / f"{slug}.json"


def main():
    raw, parsed = config.raw_dir(), config.parsed_dir()
    frontier = Frontier(raw / "frontier.db")
    n = 0
    for r in frontier.responses():
        if r["http_status"] != 200 or r["kind"] not in ("act", "judgment", "gazette", "source"):
            continue
        _, body = read_record(raw, r["warc_file"], r["offset"])
        ctype = (r["content_type"] or "").lower()
        url = origin(r["uri"])
        if "pdf" in ctype:
            doc = parse_pdf(url, body)
        elif "html" in ctype:
            doc = parse_html(url, r["kind"], body.decode("utf-8", "replace"))
        else:
            continue
        doc["retrieved_from"] = r["uri"]      # differs from url when it came via the Wayback Machine
        doc["retrieved_at"] = r["date"]
        out_path(parsed, doc).write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        n += 1
    for p in sorted((raw / "manual").glob("*.htm*")):   # pages saved by hand in a browser (Cmd+S)
        html = p.read_text(encoding="utf-8", errors="replace")
        # URL: Chrome's "saved from url=" comment, else the page's own .../eng@date/source link
        m = re.search(r"saved from url=\(\d+\)(\S+?)\s*-->", html[:2000]) or \
            re.search(r'href="((?:https://new\.kenyalaw\.org)?/akn/[^"]+?/[a-z]{3}@\d{4}-\d{2}-\d{2})/source', html)
        url = m and urljoin("https://new.kenyalaw.org/", m.group(1))
        if not url:
            print(f"skipped {p.name}: no canonical URL in the saved page")
            continue
        doc = parse_html(url, "judgment" if "/judgment/" in url else "act", html)
        doc["retrieved_from"] = f"manual/{p.name}"
        doc["retrieved_at"] = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        out_path(parsed, doc).write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        n += 1
    print(f"parsed {n} documents into {parsed}")


if __name__ == "__main__":
    main()
