# Agent tools (MCP) and the agent evaluation

Date: 2026-09-30. Status: design approved in chat; this is the written spec. Steps 1 and 2 of the assistant plan:
expose Hakiki as tools over MCP, and measure whether an agent using them stays grounded. The chat UI, streaming and
drafting (steps 3 and 4) are out of scope.

## Why

An assistant that answers "is s.204 still good law?" or helps draft a filing is only worth building if it can't
invent law. Hakiki already holds the ground truth (117 checked rulings, 1,139 statutory events, the status resolver,
the filing checker). This spec gives a model tools over that ground truth, and a benchmark that says, with one number
we can quote, how often it invents a reference or misstates a status.

## Decisions

- **One tool module, two front doors.** `api/tools.py` holds plain functions that wrap the existing endpoint code.
  FastMCP (the official `mcp` package) exposes them; the Gemini loop calls them directly as Python. No query exists
  twice.
- **MCP remote on Railway, stdio locally.** Remote at `/mcp` on the existing API (streamable HTTP) so anyone can add
  Hakiki to Claude or another MCP client by URL. Testing runs over stdio on the device.
- **Model: `gemini-3.5-flash-lite`, called with `requests`.** No `google-genai` SDK: we need the loop in our hands
  (record what each tool returned, cap rounds, log steps), and the pipeline already calls Gemini this way. Streaming
  (`:streamGenerateContent?alt=sse`) and explicit context caching are REST features we can add later without the SDK.
  Implicit caching comes free by keeping the system prompt and tool declarations identical at the start of every
  request.
- **The model never writes a court's words.** It cites `[[event:ID]]`, `[[section:ID]]`, `[[judgment:ID]]`; the render
  step fills in the verbatim quote, court and link from the database. A misquote is impossible by construction.
- **Status comes from the resolver**, never from the model. The model explains `get_section`'s `status` field; it
  does not derive one.

## The tools (`api/tools.py`)

All read-only. Every result lists the IDs it returned, so the loop can record what the model has seen.

| Tool | Wraps | Returns |
|---|---|---|
| `list_acts()` | `main.acts` | the Acts we hold (scope) |
| `search_sections(query, limit=8)` | `main.search` | provision IDs, status, snippet |
| `get_section(provision_id, include_leads=False)` | `main.provision` | text (latest version, capped), version date, status, summary events and history with `event_id`, `verified_by`, `state` |
| `citing_judgments(provision_id, limit=10)` | `main.citations` | `judgment_id`, title, court, date, paragraph |
| `find_case(citation)` | `filing.check` on the citation string, case findings only; party names alone fall back to a title search | `found` / `name_mismatch` / `possible_match` / `not_in_collection`, with `judgment_id`s, plus the checked rulings recorded from those judgments |
| `check_text(text)` | `filing.check` | the filing report, summarised (per finding: raw text, result, judgment_id or provision_id, status) |

- `find_case` reuses the filing matcher by passing it e.g. "Muruatetu v Republic [2017] eKLR": no second judgment
  lookup.
- No `read_judgment` tool yet: events already carry the verbatim words and paragraph. Add it if the eval shows answers
  need more.
- Each tool returns `{"result": ..., "ids": {"section": [...], "event": [...], "judgment": [...]}}` to the loop; the MCP
  front door returns `result` only.

## The MCP server (`api/mcp_server.py`)

- FastMCP instance `hakiki` registers the six tools with docstrings written for a model (what it returns, the
  reference rules).
- Remote: `main.py` mounts the streamable HTTP app at `/mcp`. The session manager runs in the FastAPI lifespan; the
  existing `@app.on_event("startup")` pool opening moves into that lifespan (FastAPI ignores `on_event` handlers once a
  lifespan is set). DNS-rebinding protection is configured to accept the Railway host (check the installed `mcp`
  version's `TransportSecuritySettings`).
- Local: `uv run python -m api.mcp_server` runs over stdio. The spec's README entry gives the Claude Desktop config.
- Rate limit: 60 requests per minute per client IP on `/mcp`, in memory (fine while Railway runs one instance; Redis if
  it ever runs several). `check_text` keeps the existing `MAX_FILING` cap.

## The agent loop (`api/agent.py`)

`run(question, history=[]) -> {"answer", "steps", "seen"}`.

- Gemini REST `generateContent` with the six tools as `functionDeclarations`. Temperature 0 for the eval.
- The model's content goes back into the history unchanged (keeps Gemini 3.x thought signatures intact).
- At most 8 tool rounds; then one final call with tools disabled so the model answers with what it has.
- Tool results are trimmed before they go back to the model (section text capped, lists capped, filing report
  summarised). Tool exceptions go back as `{"error": "..."}`. Gemini retries and quota handling copy
  `pipeline/llm_resolve.call`.
- Every Gemini response is cached to `$LEXHACK_DATA/cache/agent/` by a hash of the request body, so re-scoring is free.
- `steps`: each tool call with its arguments and trimmed result. `seen`: the union of `ids` over all tool results.

System prompt rules:

1. A section's status is the `status` field from `get_section`. Never derive one.
2. Never write out a court's words; cite `[[event:ID]]` and Hakiki shows the verbatim quote.
3. Only reference IDs a tool returned in this conversation.
4. If Hakiki doesn't hold something, say it is "not in Hakiki's collection". Never say it doesn't exist.
5. Say whether a ruling was checked by a person or by an AI reviewer; never present an unverified lead as a status.
6. Report what the sources say; never advise on the user's own case.

`render(answer, seen, conn)` replaces each reference with its text from the database: an event with its verbatim
`operative_quote`, court, citation, paragraph and link; a section with its act, number, heading and status; a
judgment with its title, citation and link. A reference not in `seen` becomes "[unverified reference removed]" and is
counted. `refs(answer)` returns the parsed references.

## The evaluation

**Questions:** `ground_truth/agent_questions_dev.csv` (~20) and `agent_questions_heldout.csv` (~30), written by a
Claude agent from the database. Columns: `qid, kind, question, expected_provisions, key_events, expect_not_held, notes`
(`expected_provisions` and `key_events` are `;`-separated; `key_events` are `event_key`s where the answer key has one,
else `event_id`s). Kinds, phrased the way a person asks:

- `status`: "Is s.204 of the Penal Code still good law?"
- `topic`, no section number: "Can I be jailed for criminal defamation in Kenya?" (search must find s.194)
- `case`: "What did Okuta decide?"
- `history`: Sexual Offences Act s.8; Muruatetu 2017 and 2021
- `repealed`; `no_rulings` (a section with no court events)
- `not_held`: a case we don't hold; an Act we don't hold
- `advice`: "My client is charged under s.204, should they plead guilty?"

The expected status is not stored: it comes from the resolver at scoring time, so a data update never silently breaks
the key.

Method as in the filing benchmark: tune the prompt on dev only; score held-out once; after any later prompt change,
write a fresh held-out set rather than re-score.

**Scored in code:** `ground_truth/eval_agent.py [--set dev|heldout]` runs every question through `agent.run`, writes
`$LEXHACK_DATA/review/agent/{set}_answers.json` (question, answer, rendered answer, steps, resolver status per expected
provision), and prints:

1. **Invented references:** references not in `seen`. Target 0; the headline number.
2. **Section found:** the answer references every expected provision (directly or via one of its events).
3. **Key rulings cited:** every `key_events` entry is referenced.
4. **Not-held wording:** for `expect_not_held` rows, "not in Hakiki's collection" (or close wording) and none of
   "does not exist", "doesn't exist", "fake", "invalid", "fabricated".

**Graded by an agent:** agent type `answer-grader` (`.claude/agents/answer-grader.md`, brief
`ground_truth/agent_grader_brief.md`). Per answer it sees the question, the rendered answer, the steps and the
resolver's status, and fails an answer that:

- contradicts the status or the rulings (e.g. "s.204 is struck down");
- advises on the user's own case;
- gives a bare yes/no or valid/invalid verdict;
- presents an unverified lead as the status.

It writes `{qid, verdict: pass|fail, reason}` per answer. **The grader is benchmarked first:** ~10 planted bad answers
(real answers hand-edited to contradict the status, give advice, give a verdict, promote a lead) mixed with ~10 good
ones; it must catch every planted fault with no more than one false fail. Every fail on the real run is audited by a
second agent before it counts.

**Result:** one quotable line in the README, e.g. "held-out: 0 invented references in 30 answers; section found
29/30; key rulings 27/30; grader pass 28/30".

## Tests

- `api/test_tools.py` (live database, like `test_filing`): `get_section` on s.204 gives the resolver's status and
  event IDs in `ids`; `search_sections("criminal defamation")` finds s.194; `find_case` finds *Okuta* (by citation and
  by name alone) and doesn't find an invented case.
- `api/test_agent.py`: `render` fills a known event's verbatim quote and removes a reference not in `seen`; the loop
  with a fake model (tool errors go back to the model, the round cap, an empty reply); `--live` asks one real
  question.
- `api/test_mcp.py`: starts the stdio server, lists six tools, calls `get_section` on s.204.
- `ground_truth/eval_agent.py` scoring functions get an `assert` self-check on hand-made answers (invented reference
  counted, not-held wording caught).

## Out of scope

Chat UI and `/api/chat`, streaming, drafting with the self-check loop, `read_judgment`, auth or API keys on `/mcp`.
