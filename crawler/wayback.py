"""Internet Archive source: seed the frontier from Wayback CDX captures of the origin site.

All IA requests (CDX pages, playback) go through the normal Fetcher, so they are rate-limited,
robots-checked and stored in the WARC like anything else. Playback uses `id_` URLs, which return
the archived bytes unmodified, so the parser sees exactly what the origin served.
"""
import random
import re
import urllib.robotparser
from collections import defaultdict
from urllib.parse import quote, urlsplit

from .config import origin, wayback_url
from .storage import read_record

CDX = "https://web.archive.org/cdx/search/cdx"
EXPR_RE = re.compile(r"/[a-z]{3}@(\d{4})-\d{2}-\d{2}(/source(\.\w+)?)?$")


def norm(u):
    u = re.sub(r"^http://", "https://", u)
    return re.sub(r"^(https://[^/]+):(80|443)/", r"\1/", u)


def cdx_pages(fetcher, prefix):
    """Fetch every CDX page for a URL prefix (stored + resumable), load rows into snapshots."""
    fr = fetcher.frontier
    page = 0
    while True:
        url = (f"{CDX}?url={quote(prefix, safe='/:')}&matchType=prefix&filter=statuscode:200"
               f"&fl=original,timestamp,mimetype,statuscode&page={page}")
        fr.add(url, "listing", 0, "cdx")
        row = fr.get(url)
        if row["status"] == "pending":
            fetcher.fetch_one(row)
            row = fr.get(url)
        rec = fr.latest_response(url)
        if row["status"] != "fetched" or rec is None or rec["http_status"] != 200:
            return
        _, body = read_record(fetcher.raw_dir, rec["warc_file"], rec["offset"])
        rows = [l.split(" ") for l in body.decode("utf-8", "replace").splitlines() if l.strip()]
        if not rows:
            return
        fr.add_snapshots([(norm(r[0]), r[1], r[2], r[3]) for r in rows if len(r) == 4])
        page += 1


def enqueue_original(fetcher, original, depth=0, src="seed"):
    ts = fetcher.frontier.latest_snapshot(original)
    if ts:
        return fetcher.frontier.add(wayback_url(ts, original), fetcher.scope.classify(original) or "other",
                                    depth, src)
    # Keep a visible record of coverage gaps; never fetched (host is out of scope).
    fetcher.frontier.add(original, fetcher.scope.classify(original) or "other", depth, src)
    fetcher.frontier.update(original, status="skipped", note="no wayback capture")
    return False


def load_origin_robots(fetcher, host):
    """The origin's robots.txt as archived: its Disallow rules still decide what we take."""
    cdx_pages(fetcher, f"{host}/robots.txt")
    original = f"https://{host}/robots.txt"
    if not enqueue_original(fetcher, original, src="origin-robots"):
        fetcher.log(f"no archived robots.txt for {host}; origin rules unknown")
        return None
    url = wayback_url(fetcher.frontier.latest_snapshot(original), original)
    row = fetcher.frontier.get(url)
    if row["status"] == "pending":
        fetcher.fetch_one(row)
    rec = fetcher.frontier.latest_response(url)
    if not rec or rec["http_status"] != 200:
        return None
    _, body = read_record(fetcher.raw_dir, rec["warc_file"], rec["offset"])
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(body.decode("utf-8", "replace").splitlines())
    fetcher.log(f"origin robots.txt ({host}, archived {url.split('/')[4][:8]}) loaded")
    return rp


def pick_sample(frontier, prefix, buckets, per_bucket, seed=0):
    """Judgments spread across eras (by year in URI) and courts (round-robin), deterministic."""
    rows = frontier.db.execute(
        "SELECT DISTINCT original FROM snapshots WHERE status='200' AND original LIKE ?", (f"%{prefix}%",))
    by = defaultdict(lambda: defaultdict(list))
    for (u,) in rows:
        m = re.search(r"/judgment/([a-z]+)/(\d{4})/\d+/[a-z]{3}@[\d-]+$", urlsplit(u).path)
        if not m:
            continue
        year = int(m.group(2))
        for i, (lo, hi) in enumerate(buckets):
            if lo <= year <= hi:
                by[i][m.group(1)].append(u)
    rnd = random.Random(seed)
    picked = []
    for i in range(len(buckets)):
        courts = {c: rnd.sample(sorted(v), len(v)) for c, v in sorted(by[i].items())}
        out = []
        while len(out) < per_bucket and any(courts.values()):
            for c in list(courts):
                if courts[c] and len(out) < per_bucket:
                    out.append(courts[c].pop())
        picked += out
    return picked


def prepare(fetcher):
    wb, fr = fetcher.scope.wayback, fetcher.frontier
    fetcher.origin_robots = load_origin_robots(fetcher, wb["origin_host"])
    for prefix in wb.get("cdx", []):
        cdx_pages(fetcher, prefix)
    for s in fetcher.scope.seeds:
        enqueue_original(fetcher, s["url"])
    for work in wb.get("works", []):   # every captured version + source file of these works
        for (u,) in fr.db.execute("SELECT DISTINCT original FROM snapshots WHERE original LIKE ?",
                                  (f"https://{wb['origin_host']}{work}/%",)):
            if EXPR_RE.search(u):
                enqueue_original(fetcher, u, 0, "work")
    samples = wb.get("sample") or []
    for s in samples if isinstance(samples, list) else [samples]:   # a list is enqueued in order
        for u in pick_sample(fr, s["prefix"], s["buckets"], s["per_bucket"], s.get("seed", 0)):
            enqueue_original(fetcher, u, 0, "sample")


def map_link(fetcher, original, depth, src):
    """Discovery hook: only follow links the archive actually holds."""
    return enqueue_original(fetcher, norm(original), depth, src)


def allowed_by_origin(fetcher, url):
    rp = getattr(fetcher, "origin_robots", None)
    return rp is None or rp.can_fetch(fetcher.ua, origin(url))
