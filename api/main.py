"""LexHack API. The response models below ARE the contract the web UI builds against (also served at /docs).

  uv run uvicorn api.main:app --reload            # http://127.0.0.1:8000/docs

Every answer reports what the sources say, with the court's verbatim words and a link. Never legal advice, never a
bare yes/no.
"""
import functools
import hmac
import json
import logging
import os
import queue
import threading
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import crawler.config  # noqa: F401  (loads .env)

from psycopg_pool import ConnectionPool

from . import agent, extract, filing
from .status import members, provision_status, renumbering, statuses
from . import mcp_server

DISCLAIMER = "Hakiki reports what published sources say. It is not legal advice."
# Opening a connection costs ~1 s from Kenya to Neon (Frankfurt); a pool keeps a few open. Pooled URL (PgBouncer).
POOL = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=5, open=False,
                      kwargs={"prepare_threshold": None},   # PgBouncer transaction mode: no prepared statements
                      check=ConnectionPool.check_connection)  # Neon drops idle connections; re-check before use


@asynccontextmanager
async def lifespan(app):
    POOL.open()
    try:
        async with mcp_server.mcp.session_manager.run():   # the /mcp endpoint's sessions (stateless)
            yield
    finally:
        POOL.close()


app = FastAPI(title="LexHack citator API", version="0.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
                   allow_methods=["GET"], allow_headers=["*"])

RATE, WINDOW = 60, 60.0   # /mcp requests per client IP per minute
_hits = {}
CHAT_RATE = 10            # /api/chat questions per client IP per minute (each costs Gemini calls)
CHAT_GLOBAL_RATE = 30     # /api/chat questions per minute from everyone (key "*")
_chat_hits = {}
CHAT_SLOTS = threading.BoundedSemaphore(4)   # agent runs at once
CHAT_DEADLINE = 55        # seconds; the web proxy's maxDuration is 60


def allow(key, now, hits=_hits, rate=RATE, window=WINDOW):
    """Sliding window. ponytail: in memory, one Railway instance; Redis if it ever runs several. Keys are never
    dropped: fine at our traffic, prune idle keys if memory ever grows."""
    q = hits.setdefault(key, deque())
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= rate:
        return False
    q.append(now)
    return True


def client_key(forwarded, peer):
    # the last entry is the one Railway's edge wrote; earlier ones are client-supplied and can be spoofed
    return (forwarded.split(",")[-1].strip() if forwarded else peer) or ""


def chat_key(request):
    """Rate-limit key. Behind the web proxy every request comes from Vercel's IP, so when the proxy proves itself with
    CHAT_PROXY_SECRET, trust the client IP it forwards; otherwise the caller's own IP (client_key)."""
    secret = os.environ.get("CHAT_PROXY_SECRET", "")
    given = request.headers.get("x-hakiki-proxy-key", "")
    if secret and hmac.compare_digest(given.encode(), secret.encode()):
        return "web:" + request.headers.get("x-hakiki-client-ip", "")
    return client_key(request.headers.get("x-forwarded-for"), request.client.host if request.client else "")


@app.middleware("http")
async def limit_mcp(request, call_next):
    if request.url.path.startswith("/mcp"):
        ip = client_key(request.headers.get("x-forwarded-for"), request.client.host if request.client else "")
        if not allow(ip, time.monotonic()):
            return JSONResponse({"error": f"rate limit: {RATE} requests a minute"}, status_code=429)
    return await call_next(request)


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
    provision_id: str | None = None   # the ID the ruling was recorded on: an older numbering if the section was renumbered


class Numbering(BaseModel):
    provision_id: str
    number: str | None             # the section number under this ID (Employment Act old s.85 is new s.84)
    versions: list[str]            # version dates under this ID, oldest first


class ProvisionStatus(BaseModel):
    provision: Provision
    status: str                    # e.g. 'limited by a court' — always read together with summary_events
    summary_events: list[Event]    # the events that produce the status, court's words included
    history: list[Event]           # every event, oldest first
    cited_by: int                  # distinct judgments we hold that cite this section
    lead_count: int                # unverified leads not shown unless include_unverified=true
    # The section under another ID in earlier / later versions (Kenya Law renumbered it, e.g. the Employment Act's
    # 2022-12-31 revision: sec_45 -> part_VI__sec_45). Status, history and counts cover every ID.
    renumbered_from: Numbering | None = None
    renumbered_to: Numbering | None = None
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


MAX_FILING = 200_000   # characters


class CheckRequest(BaseModel):
    text: str


class JudgmentRef(BaseModel):
    judgment_id: str
    title: str
    court: str | None
    decision_date: str | None
    neutral_citation: str | None
    source_url: str | None


class CaseCheck(BaseModel):
    result: str                    # found | name_mismatch | possible_match | not_in_collection (never "fake")
    form: str                      # neutral ([2017] KESC 2 (KLR)) | eklr ([2017] eKLR)
    match_basis: str | None        # neutral citation | case number | party names and year | quote
    cited_name: str | None         # the case name the filing gives before the citation
    judgment: JudgmentRef | None   # ours, for found and name_mismatch
    candidates: list[JudgmentRef] = []   # possible_match: up to three, best first


class QuoteCheck(BaseModel):
    quote: str                     # as written in the filing
    result: str                    # verbatim | close | not_found | not_checked (judgment not held or text unreachable)
    similarity: float | None
    court_text: str | None         # the judgment's words at the match; for not_found, the nearest passage if any
    paragraph: str | None          # judgment paragraph of that passage
    judgment_ocr: bool = False     # our copy of the judgment was read by OCR from a scan: a "close" or "not_found"
                                   # may be a scanning slip on our side, not a misquote


class SectionCheck(BaseModel):
    result: str                    # linked | not_covered (a law we don't hold, or a section we can't resolve)
    act_ref: str | None
    provision: ProvisionRef | None
    status: str | None
    summary_events: list[Event]    # the court's verbatim words, as on the section page


class Finding(BaseModel):
    kind: str                      # case | section
    raw_text: str
    char_start: int                # offsets into the submitted text, in characters (code points)
    char_end: int
    case: CaseCheck | None
    quotes: list[QuoteCheck]
    section: SectionCheck | None


class CheckReport(BaseModel):
    findings: list[Finding]
    disclaimer: str


class ExtractResult(BaseModel):
    kind: str                      # pdf | docx | text
    pages: int | None              # PDFs only
    text: str                      # what was read: shown to the reader before checking
    ocr_pages: list[int] = []      # pages read by OCR (scans): slips there can look like misquotes


def counts(conn, provision_ids, chain_map=None):
    """{provision_id: Counts}, over every ID of a renumbered section. Leads are counted as load_events shows them: one
    per judgment and event type, and not when a verified event already records the same ruling."""
    chain_map = renumbering(conn, provision_ids) if chain_map is None else chain_map
    rows = conn.execute("""
        SELECT g.key,
               (SELECT count(DISTINCT coalesce(j.duplicate_of, m.judgment_id)) FROM citation_mentions m
                  JOIN judgments j USING (judgment_id) WHERE m.provision_id = ANY(ids)),
               (SELECT count(*) FROM (SELECT DISTINCT e.judgment_id, e.event_type FROM citation_events e
                  JOIN judgments dj ON dj.judgment_id = e.judgment_id AND dj.duplicate_of IS NULL
                  WHERE e.provision_id = ANY(ids) AND NOT e.verified AND e.check_verdict IS DISTINCT FROM 'fail'
                    AND NOT EXISTS (SELECT 1 FROM citation_events v WHERE v.provision_id = ANY(ids) AND v.verified
                                    AND v.judgment_id IS NOT DISTINCT FROM e.judgment_id AND v.event_type = e.event_type)) x)
        FROM jsonb_each(%s::jsonb) g CROSS JOIN LATERAL (SELECT ARRAY(SELECT jsonb_array_elements_text(g.value)) ids) i""",
                        (json.dumps({p: members(chain_map, p) for p in provision_ids}),)).fetchall()
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
        chain_map = renumbering(conn, [r[0] for r in rows])   # a renumbered section is listed once, by its current ID
        rows = [r for r in rows if r[0] == chain_map.get(r[0], [{"provision_id": r[0]}])[-1]["provision_id"]]
        status = statuses(conn, [r[0] for r in rows], chain_map=chain_map)
        n = counts(conn, [r[0] for r in rows], chain_map)
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
        ids = members(renumbering(conn, [provision_id]), provision_id)   # every numbering of the section
        total = conn.execute("""SELECT count(DISTINCT m.judgment_id) FROM citation_mentions m JOIN judgments j USING (judgment_id)
                                WHERE m.provision_id = ANY(%s) AND j.duplicate_of IS NULL""", (ids,)).fetchone()[0]
        rows = conn.execute("""
            SELECT j.judgment_id, j.title, j.court, j.neutral_citation, j.decision_date::text, j.source_url, count(*),
                   (array_agg(m.raw_text ORDER BY m.char_start))[1], (array_agg(m.paragraph ORDER BY m.char_start))[1]
            FROM citation_mentions m JOIN judgments j USING (judgment_id) WHERE m.provision_id = ANY(%s) AND j.duplicate_of IS NULL
            GROUP BY j.judgment_id
            ORDER BY CASE j.court WHEN 'Supreme Court' THEN 3 WHEN 'Court of Appeal' THEN 2 ELSE 1 END DESC,
                     j.decision_date DESC NULLS LAST, j.judgment_id
            LIMIT %s OFFSET %s""", (ids, limit, offset)).fetchall()
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
        chain_map = renumbering(conn, [provision_id])
        res = provision_status(conn, provision_id, include_unverified, chain_map)
        n = counts(conn, [provision_id], chain_map)[provision_id]
        chain = chain_map.get(provision_id, [])
    i = next((k for k, x in enumerate(chain) if x["provision_id"] == provision_id), 0)
    moved = {"renumbered_from": chain[i - 1] if i > 0 else None, "renumbered_to": chain[i + 1] if i + 1 < len(chain) else None}
    prov = Provision(**ref_row(row[:5]), text=row[5], version_date=row[6], source_url=row[7])
    return ProvisionStatus(provision=prov, status=res["status"],
                           summary_events=[Event(**e) for e in res["summary_events"]],
                           history=[Event(**e) for e in res["history"]], **n.model_dump(), **moved)


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
        chain_map = renumbering(conn, [r[0] for r in rows])
        status = statuses(conn, [r[0] for r in rows], chain_map=chain_map)
        n = counts(conn, [r[0] for r in rows], chain_map)
    return [SearchHit(**ref_row(r[:5]), **n[r[0]].model_dump(), snippet=r[5], status=status[r[0]]) for r in rows]


@app.post("/api/check", response_model=CheckReport)
def check_filing(req: CheckRequest):
    """Every case and section citation in a pasted filing, with evidence (api/filing.py). The filing is not stored
    or logged."""
    if len(req.text) > MAX_FILING:
        raise HTTPException(413, f"filing longer than {MAX_FILING:,} characters")
    with db() as conn:
        res = filing.check(conn, req.text)
    return CheckReport(**res, disclaimer=DISCLAIMER)


@app.post("/api/extract", response_model=ExtractResult)
async def extract_file(request: Request):
    """Text of an uploaded filing (raw bytes in the body; X-Filename for messages). PDF, DOCX or plain text, up to
    10 MB; not stored. A scanned PDF (no text layer) is refused with a message, not OCR'd."""
    if int(request.headers.get("content-length") or 0) > extract.MAX_BYTES:
        raise HTTPException(413, f"That file is larger than {extract.MAX_BYTES // (1024 * 1024)} MB.")
    try:
        return ExtractResult(**extract.read(await request.body(), request.headers.get("x-filename", "")))
    except extract.ExtractError as e:
        raise HTTPException(e.status, str(e))


class Turn(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=4000)   # the plain answer text Hakiki returned


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default=[], max_length=6)
    mode: Literal["answer", "draft"] = "answer"   # draft: a short draft, checked by the filing checker (agent.draft)


CHAT_ERROR = "Hakiki couldn't finish that answer. Please try again in a minute."
CHAT_TIMEOUT = "Hakiki took too long on that answer. Please try again, or ask a narrower question."
CHAT_BUSY = "Hakiki is busy, try again in a moment"


class Stopped(Exception):
    """The reader went away (disconnect or deadline): end the agent run at its next tool call."""


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    """The research agent (api/agent.py), streamed as NDJSON: step events as tools run, delta events with the answer's
    text as it is written (references taken out; reset = discard the deltas so far), then the answer (references
    filled in from the database, authoritative) and done; or one error event. Over-long input is a 422 (Pydantic),
    not a 413."""
    now = time.monotonic()
    if not allow(chat_key(request), now, _chat_hits, CHAT_RATE):
        raise HTTPException(429, f"rate limit: {CHAT_RATE} questions a minute")
    if not allow("*", now, _chat_hits, CHAT_GLOBAL_RATE) or not CHAT_SLOTS.acquire(blocking=False):
        raise HTTPException(429, CHAT_BUSY)
    events, stop = queue.Queue(), threading.Event()

    def step(name, args):
        if stop.is_set():
            raise Stopped
        events.put({"type": "step", "tool": name, "label": agent.step_label(name, args)})

    strip = [agent.RefStrip()]

    def text(delta):
        if stop.is_set():
            raise Stopped
        if t := strip[0].feed(delta):
            events.put({"type": "delta", "text": t})

    def reset():
        strip[0] = agent.RefStrip()
        events.put({"type": "reset"})

    def work():
        try:
            history = agent.history_from_turns([t.model_dump() for t in req.history])
            if req.mode == "draft":
                d = agent.draft(req.question, history, on_step=step, attempts=2, started=now, on_text=text,
                                on_reset=reset)
                parts, removed, extra = d["parts"], d["removed"], {"check": d["check"], "label": agent.DRAFT_LABEL}
            else:
                out = agent.run(req.question, history, on_step=step, attempts=2,   # few Gemini retries: a deadline
                                on_text=text, on_reset=reset)
                with db() as conn:
                    parts, removed = agent.render_parts(out["answer"], out["seen"], conn)
                extra = {}
            events.put({"type": "answer", "text": "".join(map(agent.part_text, parts)), "parts": parts,
                        "removed": removed, **extra})
            events.put({"type": "done", "disclaimer": DISCLAIMER})
        except Stopped:
            pass
        except Exception:
            logging.exception("chat failed")   # the real error stays in the server log
            events.put({"type": "error", "message": CHAT_ERROR})
        finally:
            CHAT_SLOTS.release()
        events.put(None)

    def stream():   # a sync generator: Starlette iterates it in a worker thread, so the blocking get is fine
        deadline = time.monotonic() + CHAT_DEADLINE
        try:
            while True:
                try:
                    e = events.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    yield json.dumps({"type": "error", "message": CHAT_TIMEOUT}) + "\n"
                    return
                if e is None:
                    return
                yield json.dumps(e) + "\n"
        finally:   # closed early (client gone) or past the deadline: stop the agent at its next tool call or text
            stop.set()

    threading.Thread(target=work, daemon=True).start()
    return StreamingResponse(stream(), media_type="application/x-ndjson")


app.mount("/", mcp_server.http_app)   # serves /mcp; mounted last so every /api route above matches first
