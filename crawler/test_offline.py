"""Offline self-check of fetcher/frontier/storage/parser. No network: HTTP is faked.
    uv run python -m crawler.test_offline
"""
import tempfile
import time
from pathlib import Path

from requests.structures import CaseInsensitiveDict

from . import fetcher as F
from .config import load_scope
from .frontier import Frontier
from .parse import parse_html
from .storage import WarcStore, read_record

H = "https://new.kenyalaw.org"
ACT = f"{H}/akn/ke/act/1930/63/eng@2024-01-01"
PAGES = {
    f"{H}/robots.txt": (200, {"Content-Type": "text/plain"}, b"User-agent: *\nCrawl-delay: 5\nDisallow: /search/\n"),
    ACT: (200, {"Content-Type": "text/html", "ETag": '"abc"'},
          f'<h1>Penal Code</h1><dl class="document-metadata-list"><dt>Date</dt><dd>1 Jan 2024</dd></dl>'
          f'<a href="/akn/ke/act/1930/63/eng@2020-01-01">old</a><a href="/akn/ke/act/1930/63/eng@2024-01-01/source">pdf</a>'
          f'<a href="/akn/ke/act/1998/2/eng@2020-01-01">other act</a><a href="/search/?q=x">search</a>'
          f'<div class="document-content" data-display-type="akn"><section class="akn-section" data-eid="sec_194">'
          f'<h3>194. Defamation</h3><span class="akn-remark">[declared unconstitutional]</span></section></div>'.encode()),
    f"{ACT}/source": (302, {"Location": "/media/penal.pdf"}, b""),
    f"{H}/media/penal.pdf": (200, {"Content-Type": "application/pdf"}, b"%PDF-1.4 fake"),
    f"{H}/akn/ke/act/1930/63/eng@2020-01-01": (429, {"Retry-After": "120"}, b""),
    f"{H}/akn/ke/judgment/kehc/2016/1/eng@2016-01-01": (403, {"Content-Type": "text/html"}, b"Forbidden"),
}


class FakeResp:
    def __init__(self, url):
        self.status_code, h, self._body = PAGES[url]
        self.headers, self.reason = CaseInsensitiveDict(h), "X"
        self.raw = self

    def read(self, decode_content=True):
        return self._body


class FakeSession:
    def __init__(self):
        self.headers, self.calls = {}, []

    def get(self, url, **kw):
        self.calls.append(url)
        return FakeResp(url)


def check():
    F.time.sleep = lambda s: None
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d)
        scope = load_scope("scope.pilot.yaml")
        scope.seeds = [{"url": ACT}]
        fr = Frontier(raw / "frontier.db")
        f = F.Fetcher(scope, fr, WarcStore(raw, fr), raw, "TestBot", log=lambda *a: None)
        f.session = FakeSession()
        f.load_robots()
        assert f.delay == 5, "Crawl-delay must raise the delay"
        fr.add(ACT, "act", 0, "seed")
        while (row := fr.next_pending(time.time())) is not None:
            f.fetch_one(row)
        st = {r["url"]: r for r in fr.db.execute("SELECT * FROM urls")}
        assert st[ACT]["etag"] == '"abc"' and st[ACT]["status"] == "fetched"
        assert f"{H}/akn/ke/act/1998/2/eng@2020-01-01" not in st, "other works must not be followed"
        assert f"{H}/search/?q=x" not in st
        assert st[f"{H}/media/penal.pdf"]["status"] == "fetched", "redirect target fetched"
        old = st[f"{H}/akn/ke/act/1930/63/eng@2020-01-01"]
        assert old["status"] == "pending" and old["retries"] == 1 and old["not_before"] > time.time() + 100
        assert len(f.session.calls) == len(set(f.session.calls)), "no URL fetched twice"
        # robots disallow is honoured
        fr.add(f"{H}/search/?q=y", "other")
        f.fetch_one(fr.get(f"{H}/search/?q=y"))
        assert fr.get(f"{H}/search/?q=y")["status"] == "skipped"
        # 403 stops the crawl
        j = f"{H}/akn/ke/judgment/kehc/2016/1/eng@2016-01-01"
        fr.add(j, "judgment")
        try:
            f.fetch_one(fr.get(j))
            raise AssertionError("403 must raise StopCrawl")
        except F.StopCrawl:
            pass
        # WARC round trip + parser from storage
        rec = fr.latest_response(ACT)
        _, body = read_record(raw, rec["warc_file"], rec["offset"])
        doc = parse_html(ACT, "act", body.decode())
        assert doc["sections"][0]["eid"] == "sec_194" and doc["remarks"][0]["eid"] == "sec_194"
        assert doc["versions"] == ["2020-01-01", "2024-01-01"] and doc["expression_date"] == "2024-01-01"
        # lock: second instance refused
        with F.Lock(raw):
            try:
                with F.Lock(raw):
                    raise AssertionError("second lock must fail")
            except SystemExit:
                pass
    print("offline self-check OK")


if __name__ == "__main__":
    check()
