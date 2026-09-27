"""LexHack API. The response models below ARE the contract the web UI builds against (also served at /docs).

  uv run uvicorn api.main:app --reload            # http://127.0.0.1:8000/docs

Every answer reports what the sources say, with the court's verbatim words and a link. Never legal advice, never a
bare yes/no.
"""
import functools
import os
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import crawler.config  # noqa: F401  (loads .env)

from psycopg_pool import ConnectionPool

from .status import provision_status, statuses

DISCLAIMER = "Hakiki reports what published sources say. It is not legal advice."
app = FastAPI(title="LexHack citator API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
                   allow_methods=["GET"], allow_headers=["*"])


# Opening a connection costs ~1 s from Kenya to Neon (Frankfurt); a pool keeps a few open. Pooled URL (PgBouncer).
POOL = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=5, open=False,
                      kwargs={"prepare_threshold": None},   # PgBouncer transaction mode: no prepared statements
                      check=ConnectionPool.check_connection)  # Neon drops idle connections; re-check before use


@app.on_event("startup")
def _open_pool():
    POOL.open()


@contextmanager
def db():
    with POOL.connection() as conn:
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
    verified: bool                 # False = extracted by the pipeline and not yet reviewed
    verified_by: str | None        # 'human:…' = checked by a person; 'agent:…' = checked by an AI reviewer
    state: str                     # 'in effect' | 'reversed on appeal' | 'displaced by a later ruling'
    superseded_by: int | None      # event_id of the event that reversed or displaced this one


class ProvisionStatus(BaseModel):
    provision: Provision
    status: str                    # e.g. 'limited by a court' — always read together with summary_events
    summary_events: list[Event]    # the events that produce the status, court's words included
    history: list[Event]           # every event, oldest first
    cited_by: int                  # distinct judgments we hold that cite this section
    lead_count: int                # unverified leads not shown unless include_unverified=true
    disclaimer: str = DISCLAIMER


class Counts(BaseModel):
    cited_by: int = 0
    lead_count: int = 0


class ActSection(ProvisionRef, Counts):
    status: str                    # from verified events only, like search


class SearchHit(ProvisionRef, Counts):
    status: str
    snippet: str


class CitingJudgment(BaseModel):
    judgment_id: str
    title: str
    court: str | None
    neutral_citation: str | None
    decision_date: str | None
    source_url: str | None
    mentions: int                  # how often this judgment cites the section
    raw_text: str                  # the first citation as written, e.g. 'section 204 of the Penal Code'
    paragraph: str | None          # where that first citation is


class Citations(BaseModel):
    total: int                     # distinct citing judgments
    judgments: list[CitingJudgment]  # highest court first, then newest


class Stats(BaseModel):
    acts: int
    sections: int
    judgments: int
    cited_sections: int            # sections cited by at least one judgment
    verified_events: int           # by a person (answer key) or an AI reviewer
    verified_sections: int
    person_events: int             # verified_by 'human:…'
    agent_events: int              # verified_by 'agent:…' (the answer key's agent audit, and review_events)
    leads: int                     # extracted events the checker didn't fail
    lead_sections: int


def counts(conn, provision_ids):
    """{provision_id: Counts}. Leads are counted as load_events shows them: one per judgment and event type, and not
    when a verified event already records the same ruling."""
    rows = conn.execute("""
        SELECT p,
               (SELECT count(DISTINCT coalesce(j.duplicate_of, m.judgment_id)) FROM citation_mentions m
                  JOIN judgments j USING (judgment_id) WHERE m.provision_id = p),
               (SELECT count(*) FROM (SELECT DISTINCT e.judgment_id, e.event_type FROM citation_events e
                  JOIN judgments dj ON dj.judgment_id = e.judgment_id AND dj.duplicate_of IS NULL
                  WHERE e.provision_id = p AND NOT e.verified AND e.check_verdict IS DISTINCT FROM 'fail'
                    AND NOT EXISTS (SELECT 1 FROM citation_events v WHERE v.provision_id = p AND v.verified
                                    AND v.judgment_id IS NOT DISTINCT FROM e.judgment_id AND v.event_type = e.event_type)) x)
        FROM unnest(%s::text[]) p""", (list(provision_ids),)).fetchall()
    return {p: Counts(cited_by=c, lead_count=n) for p, c, n in rows}


def ref_row(r):
    return dict(zip(["provision_id", "act_id", "act_title", "number", "heading"], r))


@app.get("/api/acts", response_model=list[Act])
def acts():
    with db() as conn:
        rows = conn.execute("""SELECT a.act_id, a.title, a.cap_number, array_agg(v.version_date::text ORDER BY v.version_date)
                               FROM acts a JOIN act_versions v USING (act_id) GROUP BY 1, 2, 3 ORDER BY 2""").fetchall()
    return [Act(act_id=a, title=t, cap_number=c, versions=v) for a, t, c, v in rows]


@app.get("/api/acts/{act_id:path}/provisions", response_model=list[ActSection])
def act_provisions(act_id: str):
    with db() as conn:
        rows = conn.execute("""SELECT p.provision_id, p.act_id, a.title, p.number, p.heading FROM provisions p
                               JOIN acts a USING (act_id) WHERE p.act_id = %s""", (act_id,)).fetchall()
        if not rows:
            raise HTTPException(404, f"no act {act_id}")
        status = statuses(conn, [r[0] for r in rows])
        n = counts(conn, [r[0] for r in rows])
    key = lambda r: (int("".join(c for c in (r[3] or "0") if c.isdigit()) or 0), r[3] or "")
    return [ActSection(**ref_row(r), **n[r[0]].model_dump(), status=status[r[0]]) for r in sorted(rows, key=key)]


@app.get("/api/stats", response_model=Stats)
def stats():
    with db() as conn:
        row = conn.execute("""WITH live_events AS (SELECT e.* FROM citation_events e JOIN judgments j USING (judgment_id)
                                                  WHERE j.duplicate_of IS NULL)   -- court events only
            SELECT (SELECT count(*) FROM acts), (SELECT count(*) FROM provisions),
            (SELECT count(*) FROM judgments WHERE duplicate_of IS NULL),
            (SELECT count(DISTINCT provision_id) FROM citation_mentions WHERE provision_id IS NOT NULL),
            (SELECT count(*) FROM live_events WHERE verified),
            (SELECT count(DISTINCT provision_id) FROM live_events WHERE verified),
            (SELECT count(*) FROM live_events WHERE verified AND verified_by LIKE 'human:%%'),
            (SELECT count(*) FROM live_events WHERE verified AND verified_by LIKE 'agent:%%'),
            (SELECT count(*) FROM live_events WHERE NOT verified AND check_verdict IS DISTINCT FROM 'fail'),
            (SELECT count(DISTINCT provision_id) FROM live_events WHERE NOT verified AND check_verdict IS DISTINCT FROM 'fail')
        """).fetchone()
    return Stats(**dict(zip(Stats.model_fields, row)))


# Registered before /api/provisions/{id}: its :path converter would otherwise swallow '/citations'.
@app.get("/api/provisions/{provision_id:path}/citations", response_model=Citations)
def citations(provision_id: str, limit: int = Query(20, le=100), offset: int = 0):
    with db() as conn:
        total = conn.execute("""SELECT count(DISTINCT m.judgment_id) FROM citation_mentions m JOIN judgments j USING (judgment_id)
                                WHERE m.provision_id = %s AND j.duplicate_of IS NULL""", (provision_id,)).fetchone()[0]
        rows = conn.execute("""
            SELECT j.judgment_id, j.title, j.court, j.neutral_citation, j.decision_date::text, j.source_url, count(*),
                   (array_agg(m.raw_text ORDER BY m.char_start))[1], (array_agg(m.paragraph ORDER BY m.char_start))[1]
            FROM citation_mentions m JOIN judgments j USING (judgment_id) WHERE m.provision_id = %s AND j.duplicate_of IS NULL
            GROUP BY j.judgment_id
            ORDER BY CASE j.court WHEN 'Supreme Court' THEN 3 WHEN 'Court of Appeal' THEN 2 ELSE 1 END DESC,
                     j.decision_date DESC NULLS LAST, j.judgment_id
            LIMIT %s OFFSET %s""", (provision_id, limit, offset)).fetchall()
    cols = list(CitingJudgment.model_fields)
    return Citations(total=total, judgments=[CitingJudgment(**dict(zip(cols, r))) for r in rows])


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
        n = counts(conn, [provision_id])[provision_id]
    prov = Provision(**ref_row(row[:5]), text=row[5], version_date=row[6], source_url=row[7])
    return ProvisionStatus(provision=prov, status=res["status"],
                           summary_events=[Event(**e) for e in res["summary_events"]],
                           history=[Event(**e) for e in res["history"]], **n.model_dump())


@functools.lru_cache(maxsize=2048)   # a repeated query skips the ~1 s Gemini call
def query_vector(q):
    from pipeline.embed import embed_batch
    return str(embed_batch([q], os.environ["GEMINI_API_KEY"], task="RETRIEVAL_QUERY")[0])


@app.get("/api/search", response_model=list[SearchHit])
def search(q: str = Query(min_length=2), limit: int = Query(10, le=50)):
    """Hybrid search over the latest text of every section: Postgres full-text + meaning (pgvector), merged by
    reciprocal rank fusion. Meaning search is skipped if the embedding call fails, so search always answers."""
    try:
        vec = query_vector(q.strip().lower())
    except Exception:   # quota or network: fall back to words only
        vec = None
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
        status = statuses(conn, [r[0] for r in rows])
        n = counts(conn, [r[0] for r in rows])
    return [SearchHit(**ref_row(r[:5]), **n[r[0]].model_dump(), snippet=r[5], status=status[r[0]]) for r in rows]
