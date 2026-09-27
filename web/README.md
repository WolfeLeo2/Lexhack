# Hakiki (web UI)

Hakiki (Swahili for "verify") is the product; LexHack 2026 is the hackathon it was built for.

Next.js (App Router, Tailwind v4) over the FastAPI service in `../api`. Pages are server components that call the API
directly (`lib/api.ts`), so there is no CORS and the pages work before JavaScript loads.

```sh
uv run uvicorn api.main:app --reload     # from the repo root: the API on :8000
cd web && pnpm install && pnpm dev       # http://localhost:3000
```

`API_URL` (default `http://127.0.0.1:8000`) points the UI at another API. Responses are cached for 5 minutes.

| Route | What it shows |
|---|---|
| `/` | Search, and three examples (s.204, s.194, KICA s.29) of Kenya Law's text with the court's words pinned to it; every section with checked rulings; the Acts shelf |
| `/acts`, `/acts/{act_id}` | The Acts; an Act's versions and its sections, filterable, with statuses |
| `/p/{provision_id}` | A section: text, status stamp, the rulings behind it, the lineage chart, every ruling in full, judgments that cite it (`?cites=` for more). `?leads=1` adds unverified leads (they never change the status) |
| `/search?q=` | Hybrid search, each hit with its status, citation count and leads |
| `/about` | What Hakiki is, how to use it, what each status means, where the data comes from |

`pnpm check` runs the display-tidying checks (`lib/text.check.ts`).

Design notes: same palette and type as `../edu` (statute text in Newsreader, court words in italic on highlighter, our
words in IBM Plex Sans). Status is always words, never a red/green flag. Animations are CSS only and respect
reduced motion.
