"""SQLite frontier + WARC record index ($LEXHACK_DATA/raw/frontier.db)."""
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS urls (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL,                -- act|judgment|gazette|listing|source|other
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|fetched|failed|skipped
    http_status INTEGER,
    fetched_at TEXT,
    etag TEXT,
    last_modified TEXT,
    content_hash TEXT,
    depth INTEGER NOT NULL DEFAULT 0,
    discovered_from TEXT,
    retries INTEGER NOT NULL DEFAULT 0,
    not_before REAL NOT NULL DEFAULT 0, -- unix time; backoff after 429/503
    note TEXT
);
CREATE INDEX IF NOT EXISTS urls_status ON urls(status, depth, id);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    warc_file TEXT NOT NULL,
    offset INTEGER NOT NULL,
    length INTEGER NOT NULL,
    uri TEXT NOT NULL,
    record_type TEXT NOT NULL,         -- request|response
    http_status INTEGER,
    content_type TEXT,
    date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_uri ON records(uri, record_type);
CREATE TABLE IF NOT EXISTS snapshots (   -- Wayback CDX rows: which captures exist for an original URL
    original TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    mimetype TEXT,
    status TEXT,
    PRIMARY KEY (original, timestamp)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Frontier:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, timeout=60)  # autocommit: every write is durable
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def add(self, url, kind, depth=0, discovered_from=None) -> bool:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO urls(url, kind, depth, discovered_from) VALUES (?,?,?,?)",
            (url, kind, depth, discovered_from))
        return cur.rowcount == 1

    def get(self, url):
        return self.db.execute("SELECT * FROM urls WHERE url=?", (url,)).fetchone()

    shard = (0, 1)   # (i, n): this process only takes urls with id % n == i

    def next_pending(self, t: float):
        i, n = self.shard
        return self.db.execute(
            "SELECT * FROM urls WHERE status='pending' AND not_before<=? AND id % ? = ? ORDER BY depth, id LIMIT 1",
            (t, n, i)).fetchone()

    def soonest_backoff(self):
        i, n = self.shard
        return self.db.execute(
            "SELECT MIN(not_before) FROM urls WHERE status='pending' AND id % ? = ?", (n, i)).fetchone()[0]

    def update(self, url, **cols):
        sets = ", ".join(f"{k}=?" for k in cols)
        self.db.execute(f"UPDATE urls SET {sets} WHERE url=?", (*cols.values(), url))

    def requests_made(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM records WHERE record_type='request'").fetchone()[0]

    def add_record(self, **r):
        self.db.execute(
            "INSERT INTO records(warc_file, offset, length, uri, record_type, http_status, content_type, date)"
            " VALUES (:warc_file,:offset,:length,:uri,:record_type,:http_status,:content_type,:date)", r)

    def latest_response(self, uri):
        return self.db.execute(
            "SELECT * FROM records WHERE uri=? AND record_type='response' ORDER BY id DESC LIMIT 1",
            (uri,)).fetchone()

    def responses(self):
        return self.db.execute(
            "SELECT r.*, u.kind FROM records r JOIN urls u ON u.url=r.uri "
            "WHERE r.record_type='response' ORDER BY r.id").fetchall()

    def add_snapshots(self, rows):
        self.db.executemany("INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?)", rows)

    def latest_snapshot(self, original):
        r = self.db.execute("SELECT timestamp FROM snapshots WHERE original=? AND status='200' "
                            "ORDER BY timestamp DESC LIMIT 1", (original,)).fetchone()
        return r[0] if r else None

    def requeue(self, kind):
        """Incremental refresh: mark fetched URLs of a kind pending again; etag/last_modified are kept
        so the refetch is conditional."""
        return self.db.execute(
            "UPDATE urls SET status='pending', retries=0 WHERE status='fetched' AND kind=?", (kind,)).rowcount
