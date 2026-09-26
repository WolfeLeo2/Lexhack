"""Postgres (Neon) connection + schema. Loaders use the direct (unpooled) URL: bulk writes, DDL."""
import os
from pathlib import Path

import psycopg

import crawler.config  # noqa: F401  (loads .env)

SCHEMA = Path(__file__).with_name("schema.sql")


def connect():
    url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ["DATABASE_URL"]
    return psycopg.connect(url)


def apply_schema(conn):
    conn.execute(SCHEMA.read_text())
