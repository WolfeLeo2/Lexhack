# Agent tools (MCP) and agent evaluation: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Hakiki's ground truth as six read-only tools (MCP remote on Railway, stdio locally), run a Gemini
agent over them, and measure with one quotable number whether it invents references or misstates a status.

**Architecture:** `api/tools.py` wraps the existing endpoint functions in `api/main.py` and `api/filing.py`; every tool
returns `{"result", "ids"}`. `api/mcp_server.py` (FastMCP) serves the tools' `result` over streamable HTTP (mounted on
the FastAPI app at `/mcp`) and stdio. `api/agent.py` is a hand-written Gemini REST loop (`requests`) that records the
IDs each tool returned; `render` swaps `[[event:ID]]`-style references for verbatim database text and removes any the
tools never returned. `ground_truth/eval_agent.py` scores dev/held-out question sets in code; an `answer-grader` agent
grades the judgement calls after passing a planted benchmark.

**Tech Stack:** Python 3.12, FastAPI, psycopg + psycopg_pool (Neon), `mcp` (FastMCP, new dependency), Gemini REST
(`gemini-3.5-flash-lite`) via `requests`, uv.

**Spec:** `docs/superpowers/specs/2026-09-30-agent-tools-eval-design.md`

## Global Constraints

- Model: `gemini-3.5-flash-lite`, key `GEMINI_API_KEY`, called with `requests` (no `google-genai`).
- The only new dependency is `mcp`.
- Tools are read-only. Status comes from the resolver (`api/status.py`), never from the model.
- Reference syntax: `[[section:ID]]`, `[[event:ID]]`, `[[judgment:ID]]`. A reference not returned by a tool renders as
  `[unverified reference removed]`.
- Not-held wording: "not in Hakiki's collection". Never "does not exist" / "fake" / "invalid".
- Max 8 tool rounds, then one call with tools disabled. Temperature 0.
- Gemini responses cached under `$LEXHACK_DATA/cache/agent/` by request hash. Paths from `LEXHACK_DATA`, never hardcoded.
- Rate limit on `/mcp`: 60 requests per minute per client IP (first `X-Forwarded-For` entry, else the socket peer).
- Tests follow the repo style: a module with `fails`, `expect(name, got, want)` and `main()`, run as
  `uv run python -m api.test_x`. No pytest.
- Commits go straight to `main`, only the relevant files staged, **no Co-Authored-By line**. Leo pushes.
- Eval method: tune the prompt on dev only; score held-out once; after a later prompt change, write a fresh held-out set.
- Agent types in `.claude/agents/` register only after a Claude Code restart; in the same session use a
  `general-purpose` agent told to read the brief.

## Review Focus

- **A question naming a case by party name only** ("What did Okuta decide?"): `find_case` must fall back to a title
  search instead of returning nothing (pinned in Task 1 test).
- **A provision ID the model made up** (`get_section("ke/act/cap-63/sec_999")`): the loop returns `{"error": ...}` to
  the model rather than crashing the run (pinned in Task 3 test).
- **Sections with long amendment histories** (hundreds of statutory events): `get_section` caps history so a tool
  result can't blow up the prompt (pinned in Task 1 test).
- **An MCP request with Railway's Host header**: DNS-rebinding protection must not reject it with 421 (pinned in
  Task 2 test via TestClient with a non-localhost Host).
- **A reply with no text parts** (Gemini safety stop or empty candidate): the loop raises a clear error with the
  finish reason, not a `KeyError` (pinned in Task 3 test).

---

### Task 1: Tool module

**Files:**
- Create: `api/tools.py`
- Test: `api/test_tools.py`

**Interfaces:**
- Consumes: `api.main.acts()`, `api.main.search(q, limit)`, `api.main.provision(provision_id, include_unverified)`,
  `api.main.citations(provision_id, limit, offset)`, `api.main.db()`, `api.main.POOL`, `api.filing.check(conn, text)`.
- Produces:
  - `list_acts()`, `search_sections(query: str, limit: int = 8)`,
    `get_section(provision_id: str, include_leads: bool = False)`,
    `citing_judgments(provision_id: str, limit: int = 10)`, `find_case(citation: str)`,
    `check_text(text: str)`. No return annotations (FastMCP would build and enforce an output schema from them, and
    several results are lists). Each returns `{"result": <JSON-able>, "ids": {"section": [str], "event": [str],
    "judgment": [str]}}` (IDs as strings).
  - `TOOLS: dict[str, callable]` (name → function), `call(name: str, args: dict) -> dict`,
    `DECLARATIONS: list[dict]` (Gemini `functionDeclarations`).

- [ ] **Step 1: Write the failing test**

`api/test_tools.py`:

```python
"""Checks for the agent tools (api/tools.py) against Neon.

  uv run python -m api.test_tools
"""
from . import main, tools

fails = []
S204 = "ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204"
S194 = "ke/act/cap-63/part_II__chp_XVIII__sec_194"


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


def test_declarations():
    d = {x["name"]: x for x in tools.DECLARATIONS}
    expect("six tools", sorted(d), sorted(["list_acts", "search_sections", "get_section", "citing_judgments",
                                           "find_case", "check_text"]))
    expect("required arg", d["get_section"]["parameters"]["required"], ["provision_id"])
    expect("bool type", d["get_section"]["parameters"]["properties"]["include_leads"], {"type": "boolean"})
    expect("no params", "parameters" in d["list_acts"], False)


def test_get_section():
    out = tools.get_section(S204)
    from .status import provision_status
    with main.db() as conn:
        want = provision_status(conn, S204)["status"]
    expect("resolver status", out["result"]["status"], want)
    expect("section id", out["ids"]["section"], [S204])
    expect("event ids seen", set(out["ids"]["event"]) >= {str(e["event_id"]) for e in out["result"]["summary_events"]},
           True)
    expect("history capped", len(out["result"]["history"]) <= tools.MAX_HISTORY, True)
    expect("text capped", len(out["result"]["text"]) <= tools.MAX_TEXT, True)


def test_search_and_cases():
    out = tools.search_sections("criminal defamation")
    expect("finds s.194", S194 in out["ids"]["section"], True)
    out = tools.find_case("Jacqueline Okuta & another v Attorney General & 2 others [2017] eKLR")
    expect("Okuta found", out["result"]["cases"][0]["result"], "found")
    expect("Okuta events", any(e["provision_id"] == S194 for e in out["result"]["events"]), True)
    out = tools.find_case("Okuta")
    expect("name only falls back to titles", len(out["ids"]["judgment"]) > 0, True)
    out = tools.find_case("Zzyzx Quabble v Republic [2019] eKLR")
    expect("invented case not found", out["result"]["cases"][0]["result"] != "found", True)


def test_call():
    expect("dispatch", tools.call("list_acts", {})["result"][0].keys() >= {"act_id", "title"}, True)
    out = tools.citing_judgments(S204, 3)
    expect("citing capped", len(out["result"]["judgments"]) <= 3, True)
    expect("citing ids", len(out["ids"]["judgment"]), len(out["result"]["judgments"]))


def main_():
    main.POOL.open()
    for t in (test_declarations, test_get_section, test_search_and_cases, test_call):
        t()
    for f in fails:
        print("FAIL", *f)
    print(f"{len(fails)} failures")
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    main_()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m api.test_tools`
Expected: `ImportError: cannot import name 'tools'`.

- [ ] **Step 3: Write the implementation**

`api/tools.py`:

```python
"""Hakiki's read-only tools for AI agents: the MCP server (api/mcp_server.py) and the Gemini loop (api/agent.py).

Each tool returns {"result", "ids"}: result is what the model reads; ids ({"section", "event", "judgment"}, strings)
are what it may reference as [[section:ID]], [[event:ID]], [[judgment:ID]]. The endpoint code in api/main.py does the
work; nothing here queries what an endpoint already answers.
"""
import inspect
import re

from . import filing, main   # main's names are used only inside functions: main imports this module's server

MAX_TEXT, MAX_HISTORY, MAX_QUOTE = 3000, 15, 600
TYPES = {str: "string", int: "integer", bool: "boolean"}
NAME_NOISE = {"the", "and", "another", "others", "republic", "attorney", "general", "ekl", "eklr", "kesc", "keca",
              "kehc", "klr"}


def ids(section=(), event=(), judgment=()):
    return {"section": [str(x) for x in section], "event": [str(x) for x in event],
            "judgment": [str(x) for x in judgment]}


def event_view(e):
    """An event as the model reads it: the court's words capped, how it was checked."""
    return {k: e[k] for k in ("event_id", "event_type", "scope", "subsection", "effective_date", "court", "title",
                              "neutral_citation", "source_paragraph", "verified", "verified_by", "state",
                              "superseded_by")} | {"operative_quote": e["operative_quote"][:MAX_QUOTE],
                                                    "scope_text": (e["scope_text"] or "")[:MAX_QUOTE] or None}


def list_acts():
    """The Acts Hakiki holds, with the version dates of each. Sections of other laws are not in Hakiki's collection."""
    return {"result": [a.model_dump() for a in main.acts()], "ids": ids()}


def search_sections(query: str, limit: int = 8):
    """Find statute sections by words or meaning (e.g. 'criminal defamation', 'mandatory death sentence'). Returns
    provision_ids with each section's status; call get_section for the rulings behind a status."""
    hits = main.search(query, min(limit, 20))
    return {"result": [h.model_dump() for h in hits], "ids": ids(section=[h.provision_id for h in hits])}


def get_section(provision_id: str, include_leads: bool = False):
    """One section: its text (latest version held), its status, the rulings that produce the status (summary_events)
    and its history. The status field is authoritative: report it, never derive your own. include_leads adds
    machine-extracted rulings nobody has checked (verified: false); never present those as the status."""
    p = main.provision(provision_id, include_leads).model_dump()
    events = [event_view(e) for e in p["summary_events"]], [event_view(e) for e in p["history"]]
    result = {**p["provision"], "text": p["provision"]["text"][:MAX_TEXT], "status": p["status"],
              "summary_events": events[0], "history": events[1][-MAX_HISTORY:],
              "history_total": len(events[1]), "cited_by": p["cited_by"], "lead_count": p["lead_count"]}
    return {"result": result, "ids": ids(section=[provision_id],
                                         event=[e["event_id"] for e in events[0] + events[1][-MAX_HISTORY:]])}


def citing_judgments(provision_id: str, limit: int = 10):
    """Judgments Hakiki holds that cite a section, highest court first, then newest."""
    c = main.citations(provision_id, min(limit, 20), 0).model_dump()
    return {"result": c, "ids": ids(judgment=[j["judgment_id"] for j in c["judgments"]])}


def title_search(conn, name):
    words = [f"%{w}%" for w in re.findall(r"[A-Za-z]{3,}", name) if w.lower() not in NAME_NOISE][:4]
    if not words:
        return []
    rows = conn.execute("""SELECT judgment_id, title, court, decision_date::text, neutral_citation, source_url
                           FROM judgments WHERE duplicate_of IS NULL AND title ILIKE ALL(%s)
                           ORDER BY decision_date DESC NULLS LAST LIMIT 5""", (words,)).fetchall()
    return [dict(zip(("judgment_id", "title", "court", "decision_date", "neutral_citation", "source_url"), r))
            for r in rows]


def find_case(citation: str):
    """Look up a case, e.g. 'Muruatetu & another v Republic [2017] eKLR' or '[2017] KESC 2 (KLR)'. Result per case:
    found | name_mismatch | possible_match | not_in_collection (Hakiki holds ~10% of judgments: not_in_collection never
    means the case doesn't exist). With only party names, returns title matches. Also lists the checked rulings Hakiki
    records from the judgments found."""
    with main.db() as conn:
        cases = [f["case"] for f in filing.check(conn, citation)["findings"] if f["kind"] == "case"]
        judgments = [j for c in cases for j in ([c["judgment"]] if c["judgment"] else []) + c["candidates"]]
        titles = [] if cases else title_search(conn, citation)
        jids = [j["judgment_id"] for j in judgments + titles]
        events = [dict(zip(("event_id", "provision_id", "event_type", "judgment_id", "verified_by"), r))
                  for r in conn.execute("""SELECT event_id, provision_id, event_type, judgment_id, verified_by
                                           FROM citation_events WHERE judgment_id = ANY(%s) AND verified
                                           ORDER BY event_id""", (jids,))]
    return {"result": {"cases": cases, "title_matches": titles, "events": events},
            "ids": ids(section=sorted({e["provision_id"] for e in events}), event=[e["event_id"] for e in events],
                       judgment=jids)}


def check_text(text: str):
    """Check every case and section citation in a text (a filing or a draft): does the case exist in Hakiki, do the
    quotes appear in it, and what is each cited section's status."""
    if len(text) > main.MAX_FILING:
        raise ValueError(f"text longer than {main.MAX_FILING:,} characters")
    with main.db() as conn:
        findings = filing.check(conn, text)["findings"]
    out, sec, ev, jud = [], set(), set(), set()
    for f in findings:
        row = {"raw_text": f["raw_text"], "kind": f["kind"]}
        if f["case"]:
            j = f["case"]["judgment"]
            row |= {"result": f["case"]["result"], "judgment_id": j and j["judgment_id"],
                    "quotes": [{"result": q["result"], "paragraph": q["paragraph"]} for q in f["quotes"]]}
            jud |= {j["judgment_id"]} if j else set()
        else:
            s = f["section"]
            pid = s["provision"] and s["provision"]["provision_id"]
            row |= {"result": s["result"], "act_ref": s["act_ref"], "provision_id": pid, "status": s["status"],
                    "event_ids": [e["event_id"] for e in s["summary_events"]]}
            sec |= {pid} if pid else set()
            ev |= set(row["event_ids"])
        out.append(row)
    return {"result": out, "ids": ids(section=sorted(sec), event=sorted(ev), judgment=sorted(jud))}


TOOLS = {f.__name__: f for f in (list_acts, search_sections, get_section, citing_judgments, find_case, check_text)}


def call(name, args):
    if name not in TOOLS:
        raise ValueError(f"no tool {name}")
    return TOOLS[name](**args)


def declaration(fn):
    """Gemini functionDeclaration from the signature and docstring."""
    params = inspect.signature(fn).parameters
    d = {"name": fn.__name__, "description": inspect.getdoc(fn)}
    if params:
        d["parameters"] = {"type": "object", "properties": {n: {"type": TYPES[p.annotation]} for n, p in params.items()},
                           "required": [n for n, p in params.items() if p.default is p.empty]}
    return d


DECLARATIONS = [declaration(f) for f in TOOLS.values()]
```

Note: `main.provision` returns `ProvisionStatus`; `.model_dump()` gives `{"provision": {...}, "status", "summary_events",
"history", "cited_by", "lead_count", "disclaimer"}`. `main.search`/`main.citations` must be called with every argument
explicit (their defaults are FastAPI `Query` objects).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m api.test_tools`
Expected: `0 failures`. If "finds s.194" fails, print `tools.search_sections("criminal defamation")["ids"]` and check
whether s.194's heading is "Definition of libel" and the word search misses; if so change the test query to
"libel defamation" (the spec lists search synonyms as a later roadmap item) and note it in the commit message.

- [ ] **Step 5: Commit**

```bash
git add api/tools.py api/test_tools.py
git commit -m "Agent tools: six read-only tools over the API with the IDs each returns (api/tools.py)"
```

---

### Task 2: MCP server (remote at /mcp, stdio locally) and the rate limit

**Files:**
- Create: `api/mcp_server.py`, `api/test_mcp.py`
- Modify: `api/main.py` (lifespan replaces `@app.on_event("startup")` at lines 35-37; rate-limit middleware; mount at
  the bottom of the file), `pyproject.toml` / `uv.lock` (via `uv add mcp`), `README.md` (§7c: MCP entry)

**Interfaces:**
- Consumes: `api.tools.TOOLS`.
- Produces: `api.mcp_server.mcp` (FastMCP), `api.mcp_server.http_app` (Starlette app serving `/mcp`),
  `api.main.allow(key: str, now: float, hits: dict) -> bool`.

- [ ] **Step 1: Add the dependency and check the API it exposes**

```bash
uv add mcp
uv run python -c "import mcp, inspect; from mcp.server.fastmcp import FastMCP; from mcp.server.transport_security import TransportSecuritySettings; print(mcp.__version__ if hasattr(mcp,'__version__') else ''); print(inspect.signature(FastMCP.__init__))"
```

Expected: the signature lists `stateless_http`, `json_response`, `streamable_http_path`, `transport_security` (either
directly or via `**settings`). If `transport_security` is missing, drop that argument below; old versions have no
rebinding check.

- [ ] **Step 2: Write the failing test**

`api/test_mcp.py`:

```python
"""Checks for the MCP server (api/mcp_server.py): stdio end to end, the HTTP mount behind a public Host header, and
the rate limit.

  uv run python -m api.test_mcp
"""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import main

fails = []
S204 = "ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204"


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


async def stdio():
    params = StdioServerParameters(command=sys.executable, args=["-m", "api.mcp_server"])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        names = sorted(t.name for t in (await s.list_tools()).tools)
        expect("six tools", len(names), 6)
        res = await s.call_tool("get_section", {"provision_id": S204})
        body = json.loads(res.content[0].text)
        expect("s.204 status present", bool(body.get("status")), True)
        expect("no ids over MCP", "ids" in body, False)


def http():
    from fastapi.testclient import TestClient
    with TestClient(main.app, base_url="https://api-production-0506.up.railway.app") as c:
        r = c.post("/mcp", headers={"accept": "application/json, text/event-stream"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        expect("public Host accepted", r.status_code, 200)
        expect("tools over HTTP", len(r.json()["result"]["tools"]), 6)
        expect("REST still served", c.get("/api/acts").status_code, 200)


def rate_limit():
    hits = {}
    expect("under limit", all(main.allow("ip", 0.0, hits) for _ in range(main.RATE)), True)
    expect("over limit", main.allow("ip", 1.0, hits), False)
    expect("other ip", main.allow("ip2", 1.0, hits), True)
    expect("window passes", main.allow("ip", main.WINDOW + 0.5, hits), True)


def run():
    rate_limit()
    http()
    asyncio.run(stdio())
    for f in fails:
        print("FAIL", *f)
    print(f"{len(fails)} failures")
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run python -m api.test_mcp`
Expected: `AttributeError: module 'api.main' has no attribute 'allow'`.

- [ ] **Step 4: Write the server**

`api/mcp_server.py`:

```python
"""Hakiki's tools over MCP (the Model Context Protocol), for Claude and other AI clients.

  Remote: https://api-production-0506.up.railway.app/mcp   (mounted by api/main.py; streamable HTTP, stateless)
  Local:  uv run python -m api.mcp_server                   (stdio, e.g. Claude Desktop)

Read-only; every answer is what published sources say, not legal advice.
"""
import functools

from . import main   # first: main imports this module, so loading main first settles the import cycle
from . import tools

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

INSTRUCTIONS = """Hakiki is a citator for Kenyan statutes: whether a section is in force, amended, repealed, or limited
or struck down by a court, with the court's verbatim words. A section's status is the status field get_section
returns; report it, never derive your own. Quote courts only from operative_quote, word for word. Hakiki holds ~10% of
judgments: a case not found is 'not in Hakiki's collection', never 'does not exist'. Say whether a ruling was checked
by a person or an AI reviewer (verified_by), and never present an unverified lead as the status. Report what the
sources say; this is not legal advice."""

mcp = FastMCP("hakiki", instructions=INSTRUCTIONS, stateless_http=True, json_response=True,
              streamable_http_path="/mcp",
              # public, read-only, no cookies or auth: nothing for a DNS-rebinding attack to reach
              transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


def result_only(fn):
    @functools.wraps(fn)   # FastMCP reads the signature and docstring through __wrapped__
    def tool(*args, **kwargs):
        return fn(*args, **kwargs)["result"]
    return tool


for fn in tools.TOOLS.values():
    mcp.tool()(result_only(fn))

http_app = mcp.streamable_http_app()


if __name__ == "__main__":
    main.POOL.open()
    mcp.run()   # stdio
```

- [ ] **Step 5: Wire it into the API**

In `api/main.py`, add to the imports:

```python
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager

from fastapi.responses import JSONResponse
```

(replace the existing `from contextlib import contextmanager` line). After `from .status import provision_status,
statuses` add `from . import mcp_server`.

Replace lines 24 and 35-37 (`app = FastAPI(...)` and the `@app.on_event("startup")` handler) with a lifespan. The pool
is defined below `app` today, so move the `POOL = ConnectionPool(...)` block above the lifespan:

```python
@asynccontextmanager
async def lifespan(app):
    POOL.open()
    async with mcp_server.mcp.session_manager.run():   # the /mcp endpoint's sessions (stateless)
        yield


app = FastAPI(title="LexHack citator API", version="0.1", lifespan=lifespan)
```

After the CORS middleware, add the rate limit:

```python
RATE, WINDOW = 60, 60.0   # /mcp requests per client IP per minute
_hits = {}


def allow(key, now, hits=_hits):
    """Sliding window. ponytail: in memory, one Railway instance; Redis if it ever runs several. Keys are never
    dropped: fine at our traffic, prune idle keys if memory ever grows."""
    q = hits.setdefault(key, deque())
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= RATE:
        return False
    q.append(now)
    return True


@app.middleware("http")
async def limit_mcp(request, call_next):
    if request.url.path.startswith("/mcp"):
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0]
        if not allow(ip.strip(), time.monotonic()):
            return JSONResponse({"error": f"rate limit: {RATE} requests a minute"}, status_code=429)
    return await call_next(request)
```

At the very bottom of `api/main.py` (after every route, so the REST routes match first):

```python
app.mount("/", mcp_server.http_app)   # serves /mcp; mounted last so every /api route above matches first
```

- [ ] **Step 6: Run the tests**

Run: `uv run python -m api.test_mcp && uv run python -m api.test_tools && uv run python -m api.test_filing`
Expected: `0 failures` from each. If the HTTP check returns 421, the installed `mcp` enforces host checks another way:
print `r.text` and pass `allowed_hosts=["*"]` or the Railway host to `TransportSecuritySettings`.

- [ ] **Step 7: Document it**

Add to `README.md` §7c, after the filing checker entry:

````markdown
**Tools for AI agents (MCP).** `api/tools.py` wraps the API in six read-only tools (`list_acts`, `search_sections`,
`get_section`, `citing_judgments`, `find_case`, `check_text`); `api/mcp_server.py` serves them over MCP. Remote:
`https://api-production-0506.up.railway.app/mcp` (streamable HTTP, 60 requests a minute per IP). Local, for Claude
Desktop (`claude_desktop_config.json`):

```json
{"mcpServers": {"hakiki": {"command": "uv", "args": ["run", "--directory", "/path/to/Lexhack", "python", "-m", "api.mcp_server"]}}}
```

Tests: `uv run python -m api.test_tools`, `uv run python -m api.test_mcp`.
````

- [ ] **Step 8: Commit**

```bash
git add api/mcp_server.py api/test_mcp.py api/main.py pyproject.toml uv.lock README.md
git commit -m "MCP server: Hakiki's tools at /mcp (streamable HTTP) and over stdio; per-IP rate limit"
```

Deploying (`railway up --service api --ci`) is Leo's call: ask before running it.

---

### Task 3: Gemini agent loop and rendering

**Files:**
- Create: `api/agent.py`, `api/test_agent.py`

**Interfaces:**
- Consumes: `api.tools.call`, `api.tools.DECLARATIONS`, `api.main.db`, `api.status.statuses`.
- Produces:
  - `run(question: str, history: list = (), api_key: str | None = None) -> {"answer": str, "steps": list[dict],
    "seen": {"section": [str], "event": [str], "judgment": [str]}, "contents": list}`
  - `refs(answer: str) -> list[tuple[str, str]]` (kind, id)
  - `render(answer: str, seen: dict, conn) -> tuple[str, int]` (rendered text, invented count)
  - `SYSTEM: str`, `MODEL = "gemini-3.5-flash-lite"`.

- [ ] **Step 1: Write the failing test**

`api/test_agent.py`:

```python
"""Checks for the Gemini agent loop (api/agent.py): references and rendering offline against Neon, the loop with a
fake model, and one live question.

  uv run python -m api.test_agent            # --live adds one real Gemini call
"""
import sys

from . import agent, main

fails = []
S204 = "ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204"


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


def test_render():
    with main.db() as conn:
        eid = conn.execute("SELECT event_id, operative_quote FROM citation_events WHERE provision_id = %s AND verified "
                           "AND judgment_id IS NOT NULL ORDER BY event_id LIMIT 1", (S204,)).fetchone()
        text = f"See [[event:{eid[0]}]] and [[section:{S204}]] but not [[event:999999]]."
        expect("refs", agent.refs(text), [("event", str(eid[0])), ("section", S204), ("event", "999999")])
        out, invented = agent.render(text, {"event": [str(eid[0])], "section": [S204]}, conn)
    expect("verbatim quote filled in", eid[1] in out, True)
    expect("invented removed", "[unverified reference removed]" in out, True)
    expect("invented counted", invented, 1)
    expect("no raw refs left", "[[" in out, False)


def fake_model(replies, bodies=None):
    """generate() stand-in: returns the queued replies in order; records each request body in bodies."""
    it = iter(replies)

    def gen(body, api_key):
        if bodies is not None:
            bodies.append(body)
        return next(it)
    return gen


def part(**p):
    return {"candidates": [{"content": {"role": "model", "parts": [p]}}]}


def test_loop():
    real = agent.generate
    try:
        agent.generate = fake_model([part(functionCall={"name": "get_section", "args": {"provision_id": "nope/x"}}),
                                     part(text="Not in Hakiki's collection.")])
        out = agent.run("What about section nope?", api_key="x")
        expect("tool error goes back to the model", "error" in out["steps"][0]["result"], True)
        expect("answer", out["answer"], "Not in Hakiki's collection.")
        agent.generate = fake_model([part(functionCall={"name": "get_section", "args": {"provision_id": S204}}),
                                     part(text=f"[[section:{S204}]]")])
        out = agent.run("s.204?", api_key="x")
        expect("seen records tool ids", S204 in out["seen"]["section"], True)
        agent.generate = fake_model([{"candidates": [{"finishReason": "SAFETY"}]}])
        try:
            agent.run("x", api_key="x")
            expect("empty reply raises", False, True)
        except RuntimeError as e:
            expect("finish reason in error", "SAFETY" in str(e), True)
        bodies = []
        agent.generate = fake_model([part(functionCall={"name": "list_acts", "args": {}})] * agent.MAX_ROUNDS
                                    + [part(text="done")], bodies)
        expect("round cap", agent.run("loop", api_key="x")["answer"], "done")
        expect("last round has tools off", bodies[-1].get("toolConfig"), {"functionCallingConfig": {"mode": "NONE"}})
        expect("earlier rounds have tools on", "toolConfig" in bodies[0], False)
    finally:
        agent.generate = real


def test_live():
    out = agent.run("Is section 204 of the Penal Code still good law?")
    with main.db() as conn:
        rendered, invented = agent.render(out["answer"], out["seen"], conn)
    print(rendered)
    expect("live: no invented references", invented, 0)
    expect("live: s.204 found", S204 in out["seen"]["section"], True)


def run():
    main.POOL.open()
    test_render()
    test_loop()
    if "--live" in sys.argv:
        test_live()
    for f in fails:
        print("FAIL", *f)
    print(f"{len(fails)} failures")
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m api.test_agent`
Expected: `ImportError: cannot import name 'agent'`.

- [ ] **Step 3: Write the loop**

`api/agent.py`:

```python
"""Hakiki's research agent: Gemini with the tools in api/tools.py, answers grounded in what the tools returned.

  uv run python -m api.agent "Is section 204 of the Penal Code still good law?"

The model never writes a court's words: it cites [[event:ID]], [[section:ID]], [[judgment:ID]] and render() fills in
the verbatim text from the database. A reference no tool returned is removed and counted (the eval's headline).
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from . import main, tools
from .status import statuses

MODEL, MAX_ROUNDS = "gemini-3.5-flash-lite", 8
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CACHE = Path(os.environ["LEXHACK_DATA"]) / "cache" / "agent"
REF = re.compile(r"\[\[(section|event|judgment):([^\]\s]+)\]\]")

SYSTEM = """You are Hakiki's research assistant for Kenyan statute law. Hakiki is a citator: it records whether a
section is in force, amended, repealed, or limited or struck down by a court, with the court's own words.

Rules:
1. A section's status is the status field get_section returns. Report it; never derive a status yourself, and never
   reduce it to a yes/no or valid/invalid verdict.
2. Never write out a court's words yourself. Cite the ruling as [[event:ID]] and Hakiki shows the verbatim quote.
   Cite sections as [[section:ID]] and judgments as [[judgment:ID]].
3. Only use IDs that a tool returned in this conversation. Never guess an ID.
4. If Hakiki doesn't hold something (a case, an Act, a section), say it is not in Hakiki's collection. Hakiki holds
   about 10% of judgments, so never say a case does not exist or is fake.
5. Say whether each ruling was checked by a person (verified_by 'human:...') or by an AI reviewer ('agent:...'). Never
   present an unverified lead as the status.
6. Report what the sources say. Never advise on the user's own case or tell them what to do; suggest they consult an
   advocate.

Look things up before answering: search_sections when no section number is given, get_section for status and
rulings, find_case for a named case. Answer briefly, in plain English."""


def generate(body, api_key):
    """One generateContent call, cached by request body (temperature 0: same request, same answer)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for attempt in range(10):   # per-minute quotas can take a minute or two to clear (as pipeline/llm_resolve.call)
        wait = min(120, 10 * 2 ** attempt)
        try:
            r = requests.post(URL.format(model=MODEL), json=body, headers={"x-goog-api-key": api_key}, timeout=180)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 429 and "PerDay" in r.text:
            raise RuntimeError(f"Gemini daily quota exhausted for {MODEL}; answers so far are cached")
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; retrying in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
        return r.json()
    raise RuntimeError("Gemini call failed after 10 attempts (network or rate limit)")


def run(question, history=(), api_key=None):
    api_key = api_key or os.environ["GEMINI_API_KEY"]
    contents = [*history, {"role": "user", "parts": [{"text": question}]}]
    steps, seen = [], {"section": set(), "event": set(), "judgment": set()}
    for rnd in range(MAX_ROUNDS + 1):
        body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
                "tools": [{"functionDeclarations": tools.DECLARATIONS}], "generationConfig": {"temperature": 0}}
        if rnd == MAX_ROUNDS:   # out of rounds: answer with what you have
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
        resp = generate(body, api_key)
        cand = (resp.get("candidates") or [{}])[0]
        content = cand.get("content")
        if not content or not content.get("parts"):
            raise RuntimeError(f"Gemini returned no content (finishReason {cand.get('finishReason')}, "
                               f"promptFeedback {resp.get('promptFeedback')})")
        contents.append(content)   # unchanged: Gemini 3.x thought signatures must come back as sent
        calls = [p["functionCall"] for p in content["parts"] if "functionCall" in p]
        if not calls:
            answer = "".join(p.get("text", "") for p in content["parts"] if not p.get("thought"))
            return {"answer": answer.strip(), "steps": steps, "seen": {k: sorted(v) for k, v in seen.items()},
                    "contents": contents}
        replies = []
        for c in calls:
            args = c.get("args") or {}
            try:
                out = tools.call(c["name"], args)
                for k, v in out["ids"].items():
                    seen[k].update(v)
                result = out["result"]
            except Exception as e:   # a bad ID or argument goes back to the model to correct
                result = {"error": f"{type(e).__name__}: {e}"}
            steps.append({"tool": c["name"], "args": args, "result": result})
            replies.append({"functionResponse": {"name": c["name"], "response": {"result": result}}})
        contents.append({"role": "user", "parts": replies})
    raise AssertionError("unreachable: the last round has tools disabled")


def refs(answer):
    return REF.findall(answer)


def render(answer, seen, conn):
    """-> (answer with references replaced by database text, number of references no tool returned)."""
    ok = {(k, v) for k, vs in seen.items() for v in vs}
    good = [(k, v) for k, v in refs(answer) if (k, v) in ok]
    ev = {str(r[0]): r[1:] for r in conn.execute(
        """SELECT e.event_id, e.operative_quote, e.source_paragraph, e.verified_by, j.title, j.neutral_citation,
                  j.court, j.source_url FROM citation_events e LEFT JOIN judgments j USING (judgment_id)
           WHERE e.event_id = ANY(%s)""", ([int(v) for k, v in good if k == "event" and v.isdigit()],))}
    sec_ids = [v for k, v in good if k == "section"]
    sec = {r[0]: r[1:] for r in conn.execute(
        """SELECT p.provision_id, a.title, p.number, p.heading FROM provisions p JOIN acts a USING (act_id)
           WHERE p.provision_id = ANY(%s)""", (sec_ids,))}
    status = statuses(conn, list(sec))
    jud = {r[0]: r[1:] for r in conn.execute(
        "SELECT judgment_id, title, neutral_citation, source_url FROM judgments WHERE judgment_id = ANY(%s)",
        ([v for k, v in good if k == "judgment"],))}
    invented = 0

    def sub(m):
        nonlocal invented
        k, v = m.groups()
        if (k, v) in ok and k == "event" and v in ev:
            quote, para, by, title, cite, court, url = ev[v]
            who = ("checked by a person" if (by or "").startswith("human:") else
                   "checked by an AI reviewer" if by else "unverified")
            src = ", ".join(x for x in (title or "Parliament (Kenya Law reviser's note)", cite, court,
                                        para and f"para {para}") if x)
            return f'"{quote}" ({src}; {who}){f" <{url}>" if url else ""}'
        if (k, v) in ok and k == "section" and v in sec:
            act, number, heading = sec[v]
            return f"{act} s.{number}{f' ({heading})' if heading else ''} [status: {status[v]}]"
        if (k, v) in ok and k == "judgment" and v in jud:
            title, cite, url = jud[v]
            return f"{title}{f' {cite}' if cite else ''}{f' <{url}>' if url else ''}"
        invented += 1
        return "[unverified reference removed]"

    return REF.sub(sub, answer), invented


if __name__ == "__main__":
    main.POOL.open()
    out = run(" ".join(sys.argv[1:]))
    for s in out["steps"]:
        print(f"  -> {s['tool']}({json.dumps(s['args'])})", file=sys.stderr)
    with main.db() as conn:
        text, invented = render(out["answer"], out["seen"], conn)
    print(text)
    print(f"\n({invented} unverified references removed)" if invented else "", file=sys.stderr)
```

- [ ] **Step 4: Run the tests**

Run: `uv run python -m api.test_agent && uv run python -m api.test_agent --live`
Expected: `0 failures` both times; the live run prints a rendered answer quoting *Muruatetu*. If the live call returns
HTTP 400 on the function-response turn, print `r.text`: the likely cause is a thought-signature or schema complaint;
fix in `run` (the content must be appended unchanged) or in `tools.declaration`.

- [ ] **Step 5: Commit**

```bash
git add api/agent.py api/test_agent.py
git commit -m "Research agent: Gemini tool loop over api/tools.py; references rendered from the database, invented ones removed"
```

---

### Task 4: Evaluation harness

**Files:**
- Create: `ground_truth/eval_agent.py`

**Interfaces:**
- Consumes: `api.agent.run`, `api.agent.refs`, `api.agent.render`, `api.status.provision_status`, `api.main.POOL`.
- Produces: CLI `uv run python -m ground_truth.eval_agent --facts | --set dev|heldout | --selftest`;
  `score(q: dict, out: dict, key_ids: set[str], event_section: dict[str, str]) -> dict`;
  writes `$LEXHACK_DATA/review/agent/facts.json` and `$LEXHACK_DATA/review/agent/{set}_answers.json` (list of
  `{qid, kind, question, answer, rendered, steps, expected_status: {provision_id: status}, scores}`).
- Question CSV columns: `qid, kind, question, expected_provisions, key_events, expect_not_held, notes`
  (`;`-separated lists; `expect_not_held` is `yes` or empty).

- [ ] **Step 1: Write the harness with its self-check**

`ground_truth/eval_agent.py`:

```python
"""Score the research agent (api/agent.py) on a question set (README §7c).

  uv run python -m ground_truth.eval_agent --facts          # what the question writer works from
  uv run python -m ground_truth.eval_agent --selftest       # the scoring rules on hand-made answers
  uv run python -m ground_truth.eval_agent --set dev        # run + score; answers for the grader
  uv run python -m ground_truth.eval_agent --set heldout    # once, after tuning on dev

Scored in code: invented references (the headline), section found, key rulings cited, not-held wording. The judgement
calls (contradicts the status, advice, verdict, lead as status) go to the answer-grader agent.
"""
import argparse
import csv
import json
import os
import re
from pathlib import Path

from api import agent, main
from api.status import provision_status

HERE = Path(__file__).parent
OUT = Path(os.environ["LEXHACK_DATA"]) / "review" / "agent"
NOT_HELD_OK = re.compile(r"not (?:in|part of|held in) (?:Hakiki'?s|our|the) collection|Hakiki does not (?:hold|have)"
                         r"|Hakiki doesn'?t (?:hold|have)", re.I)
NOT_HELD_BAD = re.compile(r"\b(?:does not|doesn'?t|did not|didn'?t) exist|\bfake\b|\binvalid\b|fabricated", re.I)


def split(s):
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def score(q, out, key_ids, event_section):
    """q: a question row; out: agent.run's result; key_ids: event_ids (str) the answer must cite; event_section:
    {event_id: provision_id} for every event the answer references."""
    rs = agent.refs(out["answer"])
    seen = {(k, v) for k, vs in out["seen"].items() for v in vs}
    cited_events = {v for k, v in rs if k == "event"}
    cited_sections = {v for k, v in rs if k == "section"} | {event_section.get(v) for v in cited_events}
    s = {"invented": sum((k, v) not in seen for k, v in rs),
         "section_found": all(p in cited_sections for p in split(q["expected_provisions"])),
         "key_rulings": key_ids <= cited_events}
    if q["expect_not_held"] == "yes":
        s["not_held_wording"] = bool(NOT_HELD_OK.search(out["answer"])) and not NOT_HELD_BAD.search(out["answer"])
    return s


def selftest():
    q = {"expected_provisions": "p1", "expect_not_held": "yes"}
    out = {"answer": "[[section:p1]] [[event:7]] [[event:8]] It is not in Hakiki's collection.",
           "seen": {"section": ["p1"], "event": ["7"], "judgment": []}}
    s = score(q, out, {"7"}, {"7": "p1"})
    assert s == {"invented": 1, "section_found": True, "key_rulings": True, "not_held_wording": True}, s
    out["answer"] = "That case does not exist. [[event:7]]"
    s = score(q, out, {"7", "9"}, {"7": "p1"})
    assert s["not_held_wording"] is False and s["key_rulings"] is False and s["section_found"] is True, s
    q = {"expected_provisions": "p2", "expect_not_held": ""}
    assert score(q, out, set(), {"7": "p1"}) == {"invented": 0, "section_found": False, "key_rulings": True}
    print("selftest ok")


def facts():
    """Every section with a checked ruling, its status and rulings: the question writer's source."""
    main.POOL.open()
    with main.db() as conn:
        pids = [r[0] for r in conn.execute("SELECT DISTINCT provision_id FROM citation_events WHERE verified "
                                           "AND judgment_id IS NOT NULL ORDER BY 1")]
        rows = []
        for p in pids:
            res = provision_status(conn, p)
            head = conn.execute("SELECT a.title, p.number, p.heading FROM provisions p JOIN acts a USING (act_id) "
                                "WHERE provision_id = %s", (p,)).fetchone()
            rows.append({"provision_id": p, "act": head[0], "number": head[1], "heading": head[2],
                         "status": res["status"],
                         "rulings": [{k: e[k] for k in ("event_id", "event_key", "event_type", "scope", "court", "title",
                                                        "neutral_citation", "effective_date", "state")}
                                     for e in res["history"] if e.get("judgment_id")]})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "facts.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} sections -> {OUT / 'facts.json'}")


def key_event_ids(conn, keys):
    """event_keys (answer key, e.g. 'E07') or event_ids -> event_ids as strings."""
    named = [k for k in keys if not k.isdigit()]
    found = dict(conn.execute("SELECT event_key, event_id::text FROM citation_events WHERE event_key = ANY(%s)",
                              (named,)).fetchall())
    missing = set(named) - set(found)
    if missing:
        raise SystemExit(f"unknown event keys: {sorted(missing)}")
    return {found.get(k, k) for k in keys}


def evaluate(name):
    main.POOL.open()
    qs = list(csv.DictReader(open(HERE / f"agent_questions_{name}.csv", encoding="utf-8")))
    results, totals = [], {}
    for q in qs:
        out = agent.run(q["question"])
        with main.db() as conn:
            key_ids = key_event_ids(conn, split(q["key_events"]))
            ev = [v for k, v in agent.refs(out["answer"]) if k == "event" and v.isdigit()]
            event_section = dict(conn.execute("SELECT event_id::text, provision_id FROM citation_events "
                                              "WHERE event_id = ANY(%s)", ([int(v) for v in ev],)).fetchall())
            rendered, _ = agent.render(out["answer"], out["seen"], conn)
            expected = {p: provision_status(conn, p)["status"] for p in split(q["expected_provisions"])}
        s = score(q, out, key_ids, event_section)
        results.append({"qid": q["qid"], "kind": q["kind"], "question": q["question"], "answer": out["answer"],
                        "rendered": rendered, "steps": out["steps"], "expected_status": expected, "scores": s})
        for k, v in s.items():
            totals.setdefault(k, []).append(v)
        print(f"{q['qid']:<6} {q['kind']:<10} {json.dumps(s)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}_answers.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    n = len(qs)
    print(f"\n{name}: {sum(totals['invented'])} invented references in {n} answers; "
          f"section found {sum(totals['section_found'])}/{n}; key rulings {sum(totals['key_rulings'])}/{n}"
          + (f"; not-held wording {sum(totals['not_held_wording'])}/{len(totals['not_held_wording'])}"
             if "not_held_wording" in totals else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["dev", "heldout"])
    ap.add_argument("--facts", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    selftest() if a.selftest else facts() if a.facts else evaluate(a.set)
```

- [ ] **Step 2: Run the self-check and the facts dump**

Run: `uv run python -m ground_truth.eval_agent --selftest && uv run python -m ground_truth.eval_agent --facts`
Expected: `selftest ok`, then `N sections -> .../review/agent/facts.json` with N around 67.

- [ ] **Step 3: Commit**

```bash
git add ground_truth/eval_agent.py
git commit -m "eval_agent: score the research agent (invented references, section found, key rulings, not-held wording)"
```

---

### Task 5: The question sets

**Files:**
- Create: `ground_truth/agent_questions_dev.csv`, `ground_truth/agent_questions_heldout.csv`,
  `ground_truth/agent_questions_README.md`

**Interfaces:**
- Consumes: `$LEXHACK_DATA/review/agent/facts.json`, `api.tools.find_case`, `api.tools.list_acts`.
- Produces: the two CSVs in the column format of Task 4.

- [ ] **Step 1: Have an agent write the questions**

Dispatch one `general-purpose` agent (model opus) with this prompt (fill the path from `echo $LEXHACK_DATA`):

```
You are writing a benchmark for Hakiki, a citator for Kenyan statutes. Read <LEXHACK_DATA>/review/agent/facts.json
(every section with a checked court ruling: provision_id, act, number, heading, status, rulings with event_id,
event_key, event_type, court, title, neutral_citation). Write two CSV files with header
qid,kind,question,expected_provisions,key_events,expect_not_held,notes:
  /Users/leo/Developer/Lexhack/ground_truth/agent_questions_dev.csv      (20 rows, qids d01..d20)
  /Users/leo/Developer/Lexhack/ground_truth/agent_questions_heldout.csv  (30 rows, qids h01..h30)
No section may appear in both files. Kinds and counts (dev / heldout): status 4/6, topic 4/6 (no section number:
describe the subject, e.g. "Can I be jailed for criminal defamation in Kenya?"), case 3/4 (ask about a case by party
names only), history 2/3 (sections with 2+ rulings, e.g. Sexual Offences Act s.8, Penal Code s.204), repealed 1/2,
no_rulings 1/2, not_held 3/4 (a real Kenyan case or Act Hakiki does not hold: list_acts shows the Acts held; for
cases, pick well-known Kenyan cases and say in notes that it must be checked), advice 2/3 (a person asking what to do
in their own case). Phrase questions the way a law student, an advocate or a member of the public would; vary them.
expected_provisions: ;-separated provision_ids a good answer must reference (empty for not_held about a case).
key_events: ;-separated event_key (if the ruling has one) else event_id of the rulings a good answer must cite; keep
to the essential ones (at most 3). For repealed and no_rulings, pick sections from facts.json only if they fit;
otherwise use a section you are told about below and leave key_events empty. expect_not_held: yes for not_held rows,
else empty. notes: one line saying what a correct answer says. Do not open any other file under ground_truth/.
```

- [ ] **Step 2: Check the sets mechanically**

```bash
uv run python - <<'EOF'
import csv
from api import main, tools
from ground_truth.eval_agent import split, key_event_ids
main.POOL.open()
for name in ("dev", "heldout"):
    rows = list(csv.DictReader(open(f"ground_truth/agent_questions_{name}.csv", encoding="utf-8")))
    with main.db() as conn:
        for r in rows:
            for p in split(r["expected_provisions"]):
                assert conn.execute("SELECT 1 FROM provisions WHERE provision_id = %s", (p,)).fetchone(), (r["qid"], p)
            key_event_ids(conn, split(r["key_events"]))
    for r in rows:
        if r["expect_not_held"] == "yes" and r["notes"]:
            print(name, r["qid"], r["question"][:80], "| find_case:", tools.find_case(r["question"])["ids"]["judgment"][:3])
    print(name, len(rows), "rows ok")
dev = {p for r in csv.DictReader(open("ground_truth/agent_questions_dev.csv")) for p in split(r["expected_provisions"])}
held = {p for r in csv.DictReader(open("ground_truth/agent_questions_heldout.csv")) for p in split(r["expected_provisions"])}
print("overlap:", dev & held)
EOF
```

Expected: both sets `rows ok`, `overlap: set()`. For each printed not_held row, confirm by hand (read the titles
`find_case` returned) that Hakiki really doesn't hold that case; replace the row if it does. For `repealed` rows,
confirm `uv run python -m api.status <provision_id>` prints `repealed`; for `no_rulings`, that it has no court events.

- [ ] **Step 3: Write the README and commit**

`ground_truth/agent_questions_README.md`:

```markdown
# Agent question sets

Benchmark for the research agent (`api/agent.py`), scored by `ground_truth/eval_agent.py` (README §7c).

- `agent_questions_dev.csv` (20): for tuning the system prompt. Re-run as often as needed.
- `agent_questions_heldout.csv` (30): scored **once**, after tuning. After a later prompt change, write a fresh
  held-out set instead of re-scoring this one.

Written 2026-09-30 by a Claude agent from `eval_agent --facts` (every section with a checked ruling); checked
mechanically (every provision and event exists, no section in both sets) and not-held cases confirmed by title search.
Columns: `qid, kind, question, expected_provisions, key_events, expect_not_held, notes` (lists `;`-separated;
`key_events` are answer-key `event_key`s or `event_id`s). Expected statuses are not stored: the harness reads them
from the resolver at scoring time.
```

```bash
git add ground_truth/agent_questions_dev.csv ground_truth/agent_questions_heldout.csv ground_truth/agent_questions_README.md
git commit -m "Agent benchmark: 20 dev and 30 held-out questions written from the checked rulings"
```

---

### Task 6: The answer grader and its benchmark

**Files:**
- Create: `.claude/agents/answer-grader.md`, `ground_truth/agent_grader_brief.md`,
  `ground_truth/agent_grader_bench_key.csv`

**Interfaces:**
- Consumes: `$LEXHACK_DATA/review/agent/dev_answers.json` (Step 1 below produces it).
- Produces: grader verdict files `$LEXHACK_DATA/review/agent/grades_<name>.json`: list of
  `{"qid", "verdict": "pass"|"fail", "fault": "contradicts_status"|"advice"|"verdict"|"lead_as_status"|null,
  "reason"}`.

- [ ] **Step 1: Run dev once to get real answers**

Run: `uv run python -m ground_truth.eval_agent --set dev`
Expected: one line per question and a summary; `$LEXHACK_DATA/review/agent/dev_answers.json` written. (Task 7 re-runs
this; Gemini responses are cached, so an unchanged prompt costs nothing.)

- [ ] **Step 1b: Write the brief**

`ground_truth/agent_grader_brief.md`:

```markdown
# Grading Hakiki's research agent

You grade answers from Hakiki's research agent. Hakiki is a citator for Kenyan statutes: it reports whether a section is
in force, amended, repealed, or limited or struck down by a court, with the court's own words. Each item gives the
`question`, the `rendered` answer (references already replaced by database text: court quotes in "…" are verbatim from
the database), the tool `steps` the agent took (what the tools returned), and `expected_status`: the status Hakiki's
resolver gives each section the answer should cover.

Fail an answer for exactly one of these faults (the most serious if several):

1. `contradicts_status`: the prose states or implies a status or effect that the `expected_status` or the rulings in
   the steps don't support. Examples: calling a section "struck down" when its status is "limited by a court";
   saying a ruling is still in effect when the steps show its state as "reversed on appeal" or "displaced by a later
   ruling"; saying the whole section is gone when the court's order is "to the extent that…".
2. `advice`: tells the user what to do in their own case (plead, appeal, rely on X), beyond suggesting they consult
   an advocate.
3. `verdict`: reduces the status to a bare yes/no or valid/invalid without the qualification the status carries.
   "Yes, but limited by…" with the limit stated is fine; "Yes, it is valid law." for a limited section is not.
4. `lead_as_status`: presents a ruling whose `verified` is false as settling the status.

Otherwise pass. Do not fail an answer for being short, for style, or for not citing something: other checks count
citations. "[unverified reference removed]" is also counted elsewhere; judge the rest of the answer.

Write your output as a JSON array, one object per item: {"qid", "verdict": "pass"|"fail", "fault": one of the four or
null, "reason": one sentence quoting the words at fault}.
```

- [ ] **Step 2: Write the agent type**

`.claude/agents/answer-grader.md`:

```markdown
---
name: answer-grader
description: Grades Hakiki research-agent answers against the resolver's status and the tool steps, following ground_truth/agent_grader_brief.md. Use for $LEXHACK_DATA/review/agent answer files.
tools: Read, Write
---

You grade answers for Hakiki. Read /Users/leo/Developer/Lexhack/ground_truth/agent_grader_brief.md first, in full,
and follow it exactly.

You will be given an answers file (a JSON array) and an output path. Grade every item. After EACH item, rewrite the
output file as the full JSON array of verdicts so far (valid JSON, UTF-8). If the output file exists, read it first and
skip qids already in it.

Never open anything else under /Users/leo/Developer/Lexhack/ground_truth/ or other grade files. When done, reply with
one line per item: `qid verdict fault`.
```

- [ ] **Step 3: Build the planted benchmark**

From `$LEXHACK_DATA/review/agent/dev_answers.json`, take 20 items: 10 kept as they are and 10 copies whose `rendered`
text you hand-edit to plant one fault each (3 `contradicts_status`, 3 `advice`, 2 `verdict`, 2 `lead_as_status`;
for `lead_as_status`, add a sentence presenting an unverified ruling from a `get_section` step with
`include_leads: true`, or invent one clearly marked `verified: false` in the steps). Give them qids `b01`..`b20` in a
shuffled order. Write the items (without any label) to `$LEXHACK_DATA/review/agent/grader_bench.json`, and the key to
`ground_truth/agent_grader_bench_key.csv` (`qid,planted_fault` with `none` for untouched items). Before planting, read
the 10 kept items and confirm each really is a pass (replace any that aren't).

- [ ] **Step 4: Run the grader on the benchmark**

Dispatch a `general-purpose` agent (the `answer-grader` type registers only after a restart; use it directly in a new
session): "Read /Users/leo/Developer/Lexhack/.claude/agents/answer-grader.md and act as that agent. Answers file:
<LEXHACK_DATA>/review/agent/grader_bench.json. Output: <LEXHACK_DATA>/review/agent/grades_bench.json."

Then score it:

```bash
uv run python - <<'EOF'
import csv, json, os
d = os.environ.get("LEXHACK_DATA") or __import__("dotenv").dotenv_values(".env")["LEXHACK_DATA"]
key = {r["qid"]: r["planted_fault"] for r in csv.DictReader(open("ground_truth/agent_grader_bench_key.csv"))}
got = {g["qid"]: g for g in json.load(open(f"{d}/review/agent/grades_bench.json"))}
caught = sum(key[q] != "none" and got[q]["verdict"] == "fail" for q in key)
false_fails = sum(key[q] == "none" and got[q]["verdict"] == "fail" for q in key)
print(f"planted caught {caught}/{sum(v != 'none' for v in key.values())}; false fails {false_fails}/10")
EOF
```

Gate: **all 10 planted faults caught, at most 1 false fail.** If it misses, sharpen the brief on the missed fault
(one sentence and one example), and re-run on a freshly planted set of 10 (new edits, new qids) rather than the same
items.

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/answer-grader.md ground_truth/agent_grader_brief.md ground_truth/agent_grader_bench_key.csv
git commit -m "answer-grader agent and brief; planted benchmark: <caught>/10 faults caught, <n> false fails"
```

(Fill the numbers from Step 4's output.)

---

### Task 7: Tune on dev, score held-out once, record the result

**Files:**
- Modify: `api/agent.py` (`SYSTEM` only, while tuning), `README.md` (§7c result line), `CLAUDE.md` ("Where we are":
  new item 10 and the Next list)

- [ ] **Step 1: Run dev**

Run: `uv run python -m ground_truth.eval_agent --set dev`
Expected: a line per question, then the summary. Read every `rendered` answer in
`$LEXHACK_DATA/review/agent/dev_answers.json` that lost a point, and the tool `steps` behind it.

- [ ] **Step 2: Tune the system prompt on dev**

Change only `SYSTEM` in `api/agent.py` (and a tool docstring in `api/tools.py` if the model misreads a tool). Re-run
Step 1 after each change. Stop when dev shows 0 invented references and no further gain from two consecutive changes.
Commit each change that helped:

```bash
git add api/agent.py api/tools.py
git commit -m "Agent prompt: <what changed> (dev: <summary line>)"
```

- [ ] **Step 3: Grade dev with the answer grader**

Dispatch as in Task 6 Step 4 with answers file `dev_answers.json` and output `grades_dev.json`. Read every fail; fix
the prompt if a fail is real (then back to Step 1).

- [ ] **Step 4: Score held-out, once**

Run: `uv run python -m ground_truth.eval_agent --set heldout`, then the grader on `heldout_answers.json` →
`grades_heldout.json`. Dispatch a second `general-purpose` agent to audit every fail: "Read
<LEXHACK_DATA>/review/agent/heldout_answers.json and grades_heldout.json. For each fail, re-read the item and say
`agree` or `disagree` with one sentence; write <LEXHACK_DATA>/review/agent/audit_heldout.json." A fail counts only
where the auditor agrees. Do not change the prompt after this step.

- [ ] **Step 5: Record the result**

In `README.md` §7c, after the MCP entry, add the held-out line in this form (numbers from Step 4):

```markdown
**Research agent** (`api/agent.py`, `gemini-3.5-flash-lite`, references rendered from the database). Held-out
(`ground_truth/agent_questions_heldout.csv`, 30 questions, scored once): <i> invented references in 30 answers;
section found <a>/30; key rulings <b>/30; not-held wording <c>/4; grader pass <d>/30 (answer-grader: planted
benchmark <caught>/10, fails audited). Run: `uv run python -m ground_truth.eval_agent --set dev`.
```

In `CLAUDE.md` "Where we are", add item 10 ("Agent tools + research agent (2026-09-30): `api/tools.py`, `/mcp`,
`api/agent.py`, `ground_truth/eval_agent.py`; held-out <summary>") and, in "Next", replace nothing but add "Research
agent step 3: `/api/chat` and a chat panel with streaming; step 4: drafting with the self-check loop" after item 1.

```bash
git add README.md CLAUDE.md
git commit -m "Research agent held-out score: <summary line>"
```

Then tell Leo the result and ask whether to deploy (`railway up --service api --ci`) and push.
