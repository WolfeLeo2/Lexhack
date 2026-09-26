"""CLI.  uv run python -m crawler.crawl {run|add|status|requeue} ...

  run     --scope scope.pilot.yaml        fetch pending URLs (resumable; lock-protected)
  add     --scope ... URL [URL...]         enqueue URLs by hand (kind from scope patterns)
  status                                   frontier counts
  requeue --kind listing                   mark fetched URLs pending again (conditional refetch)
  retry   URL [URL...]                     put failed/skipped URLs back to pending (after e.g. access granted)
"""
import argparse
import sys
from pathlib import Path

from . import config
from .fetcher import Fetcher, Lock, StopCrawl
from .frontier import Frontier
from .storage import WarcStore


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "add", "status", "requeue", "retry"])
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--scope", default="scope.yaml")
    ap.add_argument("--kind")
    ap.add_argument("--depth", type=int, default=0)
    ap.add_argument("--shard", default="0/1", help="i/N: run N of these in parallel, one per i (own lock + WARC)")
    a = ap.parse_args(argv)

    raw = config.raw_dir()
    frontier = Frontier(raw / "frontier.db")

    if a.cmd == "status":
        for r in frontier.db.execute("SELECT kind, status, COUNT(*) n FROM urls GROUP BY 1,2 ORDER BY 1,2"):
            print(f"{r['kind']:<10} {r['status']:<8} {r['n']}")
        print("requests made:", frontier.requests_made())
        return

    if a.cmd == "requeue":
        print(frontier.requeue(a.kind), "URLs requeued")
        return

    if a.cmd == "retry":
        for u in a.urls:
            frontier.update(u, status="pending", retries=0, not_before=0)
            print("pending", u)
        return

    scope = config.load_scope(a.scope)
    if a.cmd == "add":
        for u in a.urls:
            kind = a.kind or scope.classify(u) or "other"
            print(("added " if frontier.add(u, kind, a.depth, "manual") else "exists ") + kind, u)
        return

    ua = config.user_agent()   # exits if CRAWLER_CONTACT unset
    i, n = map(int, a.shard.split("/"))
    frontier.shard = (i, n)
    suffix = f"-s{i}of{n}" if n > 1 else ""
    with Lock(raw, "crawl" + suffix):
        f = Fetcher(scope, frontier, WarcStore(raw, frontier, "kenyalaw" + suffix), raw, ua)
        try:
            f.run()
        except StopCrawl as e:
            msg = f"CRAWL STOPPED: {e}"
            (raw / "STOPPED.txt").write_text(msg + "\n")
            print(msg, file=sys.stderr)
            sys.exit(2)
        except KeyboardInterrupt:
            print("interrupted; state is saved, re-run to resume", file=sys.stderr)
            sys.exit(130)


if __name__ == "__main__":
    main()
