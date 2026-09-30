"""Postgres (Neon) connection + schema. Loaders use the direct (unpooled) URL: bulk writes, DDL."""
import os
from pathlib import Path

import psycopg

import crawler.config  # noqa: F401  (loads .env)

SCHEMA = Path(__file__).with_name("schema.sql")


def connect():
    url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ["DATABASE_URL"]
    # A dropped network (a laptop sleeping) otherwise leaves a query waiting forever: fail within ~1 min instead, and
    # the caller's retry/skip logic takes over.
    return psycopg.connect(url, connect_timeout=15, keepalives=1, keepalives_idle=30, keepalives_interval=10,
                           keepalives_count=3, options="-c statement_timeout=300000")


def apply_schema(conn):
    conn.execute(SCHEMA.read_text())
