# LexHack crawler

A polite, resumable crawler for new.kenyalaw.org (Peachjam). It fetches once, stores everything in WARC files, and parses offline.

> **Status:** blocked. new.kenyalaw.org returns HTTP 403 to this crawler's User-Agent, starting with robots.txt. See `REPORT.md`. Do not run it again until Kenya Law grants access.

## Setup

```sh
cd ~/Developer/Lexhack
uv sync
cat > .env <<'EOF'
LEXHACK_DATA=/Users/you/lexhack-data     # data lives here, never in the repo
CRAWLER_CONTACT=you@example.org          # goes into the User-Agent; the crawler refuses to start without it
EOF
```

Both variables can also come from the environment. The crawler never falls back to a default.

## Run, resume, inspect

```sh
uv run python -m crawler.crawl run --scope scope.pilot.yaml   # fetch; Ctrl-C at any time
uv run python -m crawler.crawl run --scope scope.pilot.yaml   # same command resumes
uv run python -m crawler.crawl status                         # counts by kind/status
uv run python -m crawler.crawl add URL [URL...]               # enqueue by hand (e.g. picked sample judgments)
uv run python -m crawler.parse                                # WARC -> $LEXHACK_DATA/parsed/*.json, offline, re-runnable
uv run python -m crawler.test_offline                         # self-check, no network
```

- **Lock:** `$LEXHACK_DATA/raw/crawl.pid` blocks a second instance. A lock left by a killed process is cleared automatically.
- **Hard stop:** a 401 or 403, a login redirect, or a bot challenge writes `raw/STOPPED.txt` and exits with code 2. Delete that file only after the cause is resolved. The URL stays `failed`; re-queue it deliberately with `crawl retry URL`.

## Parallel runs

```sh
for i in 0 1 2; do nohup uv run python -m crawler.crawl run --scope scope.wayback-judgments.yaml --shard $i/3 > $LEXHACK_DATA/raw/s$i.out 2>&1 & done
pkill -TERM -f "crawler.crawl run"      # stop; background jobs ignore Ctrl-C/SIGINT
```

Each shard takes the URLs with `id % N == i` and has its own lock (`crawl-s{i}ofN.pid`) and its own WARC files (`kenyalaw-s{i}ofN-*.warc.gz`). On a 429 or 503, the worker pauses for 60 s. Three shards against the Internet Archive ran at ~50 pages/min with no 429s (2026-09-23).

## Switching scope (pilot → full)

The two crawls differ only in the scope file. `scope.yaml`, the default, is a symlink to `scope.pilot.yaml`.

```sh
ln -sf scope.full.yaml crawler/scope.yaml
```

A scope file sets the allowed hosts, the URL regex for each kind (first match wins), the follow rules (which kinds each kind's links may enqueue), `same_work` (follow only within the same FRBR work), `max_depth`, `max_requests` and `min_delay`.

`scope.full.yaml` is a draft and has **not** been verified against the live site.

## Incremental updates

```sh
uv run python -m crawler.crawl requeue --kind listing
```

This re-queues listing pages. They are refetched with `If-None-Match` / `If-Modified-Since`, so unchanged pages come back as cheap 304s, and new documents on them get enqueued.

## Layout

| Module | Job |
|---|---|
| `config.py` | env (`.env` via python-dotenv), paths, scope loading |
| `frontier.py` | SQLite `urls` frontier + `records` WARC index (`raw/frontier.db`) |
| `fetcher.py` | robots.txt (incl. Crawl-delay), ≥2 s spacing, one connection, 429/503 backoff (Retry-After, else 60 s doubling, 5 tries), manual redirects, conditional GETs, hard stops, link discovery |
| `storage.py` | warcio writer: gzip per record, request+response pairs, rotation at ~1 GB, seek-by-offset reader |
| `parse.py` | Peachjam HTML → metadata `<dl>`, display type, sections by `data-eid`, `akn-remark`s, version dates, `/akn/` links, source URL; PDFs → text (pypdf) |
