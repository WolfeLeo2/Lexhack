"""LexHack API. The response models below ARE the contract the web UI builds against (also served at /docs).

  uv run uvicorn api.main:app --reload            # http://127.0.0.1:8000/docs

Every answer reports what the sources say, with the court's verbatim words and a link. Never legal advice, never a
bare yes/no.
"""
import os
from contextlib import contextmanager

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import crawler.config  # noqa: F401  (loads .env)

from .status import provision_status

DISCLAIMER = "LexHack reports what published sources say. It is not legal advice."
app = FastAPI(title="LexHack citator API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
                   allow_methods=["GET"], allow_headers=["*"])


@contextmanager
def db():
    # ponytail: a connection per request; add psycopg_pool if traffic ever matters
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:   # pooled URL for app traffic
        yield conn


class Act(BaseModel):
    act_id: str                    # 'ke/act/cap-63'
    title: str                     # 'Penal Code'
    cap_number: str | None         # '63'
    versions: list[str]            # version dates, oldest first


class ProvisionRef(BaseModel):
    provision_id: str              # 'ke/act/cap-63/part_II__chp_XVIII__sec_194'
    act_id: str
    act_title: str
    number: str | None             # '194'
    heading: str | None            # 'Definition of libel'


class Provision(ProvisionRef):
    text: str                      # text in the latest version we hold
    version_date: str              # which version that is
    source_url: str | None         # Kenya Law page of that version


class Event(BaseModel):
    event_id: int
    event_type: str                # declared_unconstitutional | read_down | severed | upheld | interpreted | reversed_on_appeal
    scope: str                     # total | partial
    scope_text: str | None         # verbatim "to the extent that…"
    subsection: str | None         # '8(2)'
    operative_quote: str           # the court's exact words
    source_paragraph: str | None
    effective_date: str | None
    court: str | None
    title: str | None              # case name
    neutral_citation: str | None
    source_url: str | None         # judgment on Kenya Law
    verified: bool                 # False = extracted by the pipeline, not yet checked by a person
    state: str                     # 'in effect' | 'reversed on appeal' | 'displaced by a later ruling'
    superseded_by: int | None      # event_id of the event that reversed or displaced this one


class ProvisionStatus(BaseModel):
    provision: Provision
    status: str                    # e.g. 'limited by a court' — always read together with summary_events
    summary_events: list[Event]    # the events that produce the status, court's words included
    history: list[Event]           # every event, oldest first
    disclaimer: str = DISCLAIMER


class SearchHit(ProvisionRef):
    status: str
    snippet: str


def ref_row(r):
    return dict(zip(["provision_id", "act_id", "act_title", "number", "heading"], r))


@app.get("/api/acts", response_model=list[Act])
def acts():
    with db() as conn:
        rows = conn.execute("""SELECT a.act_id, a.title, a.cap_number, array_agg(v.version_date::text ORDER BY v.version_date)
                               FROM acts a JOIN act_versions v USING (act_id) GROUP BY 1, 2, 3 ORDER BY 2""").fetchall()
    return [Act(act_id=a, title=t, cap_number=c, versions=v) for a, t, c, v in rows]


@app.get("/api/acts/{act_id:path}/provisions", response_model=list[ProvisionRef])
def act_provisions(act_id: str):
    with db() as conn:
        rows = conn.execute("""SELECT p.provision_id, p.act_id, a.title, p.number, p.heading FROM provisions p
                               JOIN acts a USING (act_id) WHERE p.act_id = %s""", (act_id,)).fetchall()
    if not rows:
        raise HTTPException(404, f"no act {act_id}")
    key = lambda r: (int("".join(c for c in (r[3] or "0") if c.isdigit()) or 0), r[3] or "")
    return [ProvisionRef(**ref_row(r)) for r in sorted(rows, key=key)]


@app.get("/api/provisions/{provision_id:path}", response_model=ProvisionStatus)
def provision(provision_id: str, include_unverified: bool = False):
    """include_unverified=true adds machine-extracted events (verified: false). Blind review measured their precision at
    ~53% (README §7b), so they're off by default and must be shown as unverified leads, never as status."""
    with db() as conn:
        row = conn.execute("""
            SELECT p.provision_id, p.act_id, a.title, p.number, p.heading, t.text, v.version_date::text, v.source_url
            FROM provisions p JOIN acts a USING (act_id) JOIN provision_texts t USING (provision_id)
            JOIN act_versions v USING (version_id) WHERE p.provision_id = %s
            ORDER BY v.version_date DESC LIMIT 1""", (provision_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"no provision {provision_id}")
        res = provision_status(conn, provision_id, include_unverified)
    prov = Provision(**ref_row(row[:5]), text=row[5], version_date=row[6], source_url=row[7])
    return ProvisionStatus(provision=prov, status=res["status"],
                           summary_events=[Event(**e) for e in res["summary_events"]],
                           history=[Event(**e) for e in res["history"]])


@app.get("/api/search", response_model=list[SearchHit])
def search(q: str = Query(min_length=2), limit: int = Query(10, le=50)):
    """Hybrid search over the latest text of every section: Postgres full-text + meaning (pgvector), merged by
    reciprocal rank fusion. Meaning search is skipped if the embedding call fails, so search always answers."""
    vec = None
    try:
        from pipeline.embed import embed_batch
        vec = str(embed_batch([q], os.environ["GEMINI_API_KEY"], task="RETRIEVAL_QUERY")[0])
    except Exception:   # quota or network: fall back to words only
        pass
    with db() as conn:
        rows = conn.execute("""
            WITH latest AS (
                SELECT DISTINCT ON (t.provision_id) t.provision_id, t.text, t.tsv, t.embedding
                FROM provision_texts t JOIN act_versions v USING (version_id)
                ORDER BY t.provision_id, v.version_date DESC),
            fts AS (SELECT provision_id, row_number() OVER (ORDER BY ts_rank(tsv, q) DESC) AS r
                    FROM latest, websearch_to_tsquery('english', %(q)s) q WHERE tsv @@ q LIMIT 50),
            sem AS (SELECT provision_id, row_number() OVER (ORDER BY embedding <=> %(v)s::vector) AS r
                    FROM latest WHERE %(v)s::text IS NOT NULL ORDER BY embedding <=> %(v)s::vector LIMIT 50),
            fused AS (SELECT provision_id, sum(1.0 / (60 + r)) AS score FROM
                      (SELECT * FROM fts UNION ALL SELECT * FROM sem) x GROUP BY 1)
            SELECT p.provision_id, p.act_id, a.title, p.number, p.heading, left(l.text, 240)
            FROM fused f JOIN provisions p USING (provision_id) JOIN acts a USING (act_id)
            JOIN latest l USING (provision_id) ORDER BY f.score DESC LIMIT %(n)s""",
                            {"q": q, "v": vec, "n": limit}).fetchall()
        return [SearchHit(**ref_row(r[:5]), snippet=r[5], status=provision_status(conn, r[0])["status"]) for r in rows]
