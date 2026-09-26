"""Polite single-connection fetcher: robots.txt, rate limit, backoff, conditional GETs, hard stops."""
import hashlib
import os
import re
import time
import urllib.robotparser
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urldefrag, urlsplit

import requests
from bs4 import BeautifulSoup

from . import wayback
from .config import origin
from .frontier import now
from .storage import read_record

MAX_RETRIES = 5
BACKOFF_START = 60
MAX_NET_FAILS = 8          # consecutive connection/DNS failures before giving up (~2 h of pauses)


class StopCrawl(Exception):
    """Access control / challenge / licence problem: stop everything and report."""


class Lock:
    def __init__(self, raw_dir, name="crawl"):
        self.path = raw_dir / f"{name}.pid"

    def __enter__(self):
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pid = int(self.path.read_text().strip() or 0)
            try:
                os.kill(pid, 0)
                raise SystemExit(f"Another crawler (pid {pid}) holds {self.path}. Refusing to start.")
            except ProcessLookupError:     # stale lock from a killed run
                self.path.unlink()
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


def normalise(base, href):
    url, _ = urldefrag(urljoin(base, href.strip()))
    return url if url.startswith(("http://", "https://")) else None


def work_of(url):
    """FRBR work URI: path before the expression (/eng@date), so versions and sources share it."""
    path = urlsplit(origin(url)).path
    m = re.search(r"/[a-z]{3}@", path) or re.search(r"/(?:eng|swa)(?=/|$)", path)
    return path[:m.start()] if m else re.sub(r"/source(\.\w+)?$", "", path)


def challenge_reason(status, headers, body: bytes):
    h = {k.lower(): v for k, v in headers.items()}
    if status in (401, 403):
        return f"HTTP {status}"
    if h.get("cf-mitigated") == "challenge":
        return "Cloudflare challenge (cf-mitigated header)"
    loc = h.get("location", "")
    if "/accounts/login" in loc:
        return f"login wall (redirect to {loc})"
    head = body[:20000].lower()
    if b"<title>just a moment" in head or b"challenge-platform" in head or b"g-recaptcha" in head and status != 200:
        return "bot challenge page"
    return None


class Fetcher:
    def __init__(self, scope, frontier, store, raw_dir, user_agent, log=print):
        self.scope, self.frontier, self.store, self.raw_dir = scope, frontier, store, raw_dir
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.ua = user_agent
        self.log = log
        self.delay = scope.min_delay
        self.last = 0.0
        self.robots = {}
        self.net_fails = 0

    # ---- robots -----------------------------------------------------------
    def load_robots(self):
        for host in self.scope.hosts:
            url = f"https://{host}/robots.txt"
            rec = self.frontier.latest_response(url)
            self.frontier.add(url, "other")
            if rec is None or self.frontier.get(url)["status"] == "pending":
                self.fetch_one(self.frontier.get(url), check_robots=False)
                rec = self.frontier.latest_response(url)
            rp = urllib.robotparser.RobotFileParser()
            if rec["http_status"] == 200:
                _, body = read_record(self.raw_dir, rec["warc_file"], rec["offset"])
                rp.parse(body.decode("utf-8", "replace").splitlines())
            elif rec["http_status"] in (404, 410):
                rp.allow_all = True
            else:
                raise StopCrawl(f"robots.txt for {host} returned {rec['http_status']}; not crawling")
            self.robots[host] = rp
            cd = rp.crawl_delay(self.ua)
            rr = rp.request_rate(self.ua)
            self.delay = max(self.delay, float(cd or 0), (rr.seconds / rr.requests) if rr else 0)
        self.log(f"robots loaded; delay between requests = {self.delay:.1f}s")

    def allowed(self, url):
        rp = self.robots.get(urlsplit(url).hostname)
        ok = rp is not None and rp.can_fetch(self.ua, url)
        return ok and (not self.scope.wayback or wayback.allowed_by_origin(self, url))

    # ---- fetch loop -------------------------------------------------------
    def run(self):
        self.load_robots()
        if self.scope.wayback:
            wayback.prepare(self)
        else:
            for s in self.scope.seeds:
                self.frontier.add(s["url"], s.get("kind") or self.scope.classify(s["url"]) or "other", 0, "seed")
        while True:
            if self.frontier.requests_made() >= self.scope.max_requests:
                self.log(f"request budget {self.scope.max_requests} reached; stopping cleanly")
                return
            t = time.time()
            row = self.frontier.next_pending(t)
            if row is None:
                soon = self.frontier.soonest_backoff()
                if soon is None:
                    self.log("frontier empty; done")
                    return
                time.sleep(max(1.0, soon - t))
                continue
            self.fetch_one(row)

    def fetch_one(self, row, check_robots=True):
        url = row["url"]
        host = urlsplit(url).hostname
        if host not in self.scope.hosts:
            self.frontier.update(url, status="skipped", note="host out of scope")
            return
        if check_robots and not self.allowed(url):
            self.frontier.update(url, status="skipped", note="disallowed by robots.txt")
            self.log(f"robots disallow: {url}")
            return
        wait = self.last + self.delay - time.time()
        if wait > 0:
            time.sleep(wait)
        headers = {}
        if row["etag"]:
            headers["If-None-Match"] = row["etag"]
        if row["last_modified"]:
            headers["If-Modified-Since"] = row["last_modified"]
        try:
            r = self.session.get(url, headers=headers, timeout=120, allow_redirects=False, stream=True)
            body = r.raw.read(decode_content=True)
        except requests.RequestException as e:
            # Our connectivity, not the URL: pause the whole crawl; the URL keeps its retry budget.
            self.net_fails += 1
            if self.net_fails > MAX_NET_FAILS:
                raise StopCrawl(f"network down ({self.net_fails} consecutive failures): {e}")
            pause = min(900, 30 * 2 ** (self.net_fails - 1))
            self.log(f"network error ({type(e).__name__}); pausing {pause}s, will retry {url}")
            time.sleep(pause)
            return
        finally:
            self.last = time.time()
        self.net_fails = 0
        sent = {**self.session.headers, **headers}
        resp_headers = [(k, v) for k, v in r.headers.items()
                        if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")]
        resp_headers.append(("Content-Length", str(len(body))))
        self.store.write(url, dict(sent), r.status_code, r.reason or "", resp_headers, body)
        self.log(f"{r.status_code} {len(body):>9,}B {row['kind']:<9} {url}")

        reason = challenge_reason(r.status_code, r.headers, body)
        if reason:
            self.frontier.update(url, status="failed", http_status=r.status_code, fetched_at=now(), note=reason)
            raise StopCrawl(f"{reason} at {url}")
        if r.status_code in (429, 503):
            ra = r.headers.get("Retry-After")
            self._retry(row, f"HTTP {r.status_code}", retry_after=ra)
            time.sleep(BACKOFF_START)   # the server said slow down: pause this worker, not just this URL
            return
        cols = dict(http_status=r.status_code, fetched_at=now(), retries=row["retries"])
        if r.status_code == 304:
            self.frontier.update(url, status="fetched", **cols)
            return
        cols.update(etag=r.headers.get("ETag"), last_modified=r.headers.get("Last-Modified"),
                    content_hash=hashlib.sha256(body).hexdigest())
        if 300 <= r.status_code < 400 and r.headers.get("Location"):
            target = normalise(url, r.headers["Location"])
            if target:
                kind = self.scope.classify(target) or row["kind"]
                self.frontier.add(target, kind, row["depth"], url)
            self.frontier.update(url, status="fetched", note=f"redirect -> {target}", **cols)
            return
        status = "fetched" if r.status_code < 400 else "failed"
        self.frontier.update(url, status=status, **cols)
        if status == "fetched" and "html" in r.headers.get("Content-Type", ""):
            self.discover(row, body)

    def _retry(self, row, why, retry_after=None):
        n = row["retries"] + 1
        if n > MAX_RETRIES:
            self.frontier.update(row["url"], status="failed", retries=n, note=why)
            return
        delay = BACKOFF_START * 2 ** (n - 1)
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
                except (TypeError, ValueError):
                    pass
        delay = max(delay, self.delay)
        self.frontier.update(row["url"], retries=n, not_before=time.time() + delay, note=why)
        self.log(f"{why}: backing off {delay:.0f}s for {row['url']}")

    # ---- link discovery ---------------------------------------------------
    def discover(self, row, body):
        allowed = self.scope.follow.get(row["kind"], [])
        if not allowed or row["depth"] >= self.scope.max_depth:
            return
        src_work = work_of(row["url"])
        base = origin(row["url"])
        hosts = [self.scope.wayback["origin_host"]] if self.scope.wayback else self.scope.hosts
        soup = BeautifulSoup(body, "lxml")
        for a in soup.find_all("a", href=True):
            url = normalise(base, a["href"])
            if not url or urlsplit(url).hostname not in hosts:
                continue
            kind = self.scope.classify(url)
            if kind not in allowed:
                continue
            if kind in self.scope.same_work and work_of(url) != src_work:
                continue
            if self.scope.wayback:
                wayback.map_link(self, url, row["depth"] + 1, row["url"])
            else:
                self.frontier.add(url, kind, row["depth"] + 1, row["url"])
