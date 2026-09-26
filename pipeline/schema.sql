-- LexHack schema. Idempotent: safe to re-run. Apply with `uv run python -m pipeline.load_acts`
-- (or any loader), which runs this file over the direct (unpooled) connection first.
-- Every ID carries the jurisdiction ('ke/...') so the design can extend beyond Kenya.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS acts (
  act_id        TEXT PRIMARY KEY,          -- 'ke/act/cap-63'
  jurisdiction  TEXT NOT NULL,             -- 'ke'
  title         TEXT NOT NULL,
  cap_number    TEXT,                      -- '63'
  frbr_uri      TEXT                       -- AKN work URI, '/akn/ke/act/1930/10'
);

CREATE TABLE IF NOT EXISTS act_versions (
  version_id    TEXT PRIMARY KEY,          -- act_id + '@' + date
  act_id        TEXT NOT NULL REFERENCES acts,
  version_date  DATE NOT NULL,
  source        TEXT NOT NULL,             -- 'wayback' | 'manual'
  source_url    TEXT,                      -- Kenya Law URL (what users click); fetch provenance is in raw_path's JSON
  raw_path      TEXT                       -- parsed JSON, relative to $LEXHACK_DATA
);

CREATE TABLE IF NOT EXISTS provisions (
  provision_id  TEXT PRIMARY KEY,          -- act_id + '/' + eid
  act_id        TEXT NOT NULL REFERENCES acts,
  eid           TEXT NOT NULL,             -- stable across versions
  number        TEXT,                      -- '204'
  heading       TEXT                       -- 'Punishment of murder' (latest version)
);

CREATE TABLE IF NOT EXISTS provision_texts (   -- a section's text in one version
  provision_id  TEXT NOT NULL REFERENCES provisions,
  version_id    TEXT NOT NULL REFERENCES act_versions,
  text          TEXT NOT NULL,
  tsv           TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  embedding     VECTOR(1536),              -- gemini-embedding-2, output_dimensionality=1536, L2-normalised
  PRIMARY KEY (provision_id, version_id)
);
CREATE INDEX IF NOT EXISTS provision_texts_tsv ON provision_texts USING gin (tsv);
CREATE INDEX IF NOT EXISTS provision_texts_embedding ON provision_texts USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS judgments (
  judgment_id       TEXT PRIMARY KEY,      -- 'ke/judgment/kesc/2017/2'
  neutral_citation  TEXT,                  -- '[2017] KESC 2 (KLR)'
  title             TEXT NOT NULL,
  court             TEXT,
  case_number       TEXT,
  decision_date     DATE,
  judges            TEXT[],
  has_full_text     BOOLEAN,
  source            TEXT NOT NULL,         -- 'wayback' | 'manual'
  source_url        TEXT,                  -- Kenya Law URL
  raw_path          TEXT                   -- parsed JSON (full text), relative to $LEXHACK_DATA
);

-- Every place a judgment mentions a statute section. Raw extraction output.
CREATE TABLE IF NOT EXISTS citation_mentions (
  mention_id    SERIAL PRIMARY KEY,
  judgment_id   TEXT NOT NULL REFERENCES judgments,
  provision_id  TEXT REFERENCES provisions,  -- NULL if not yet resolved
  raw_text      TEXT NOT NULL,               -- 'section 204 of the Penal Code'
  paragraph     TEXT,
  char_start    INT,
  char_end      INT,
  method        TEXT NOT NULL,               -- 'regex' | 'llm'
  confidence    REAL
);

-- What a court (or Parliament) actually DID to a section. Definitions: README.md §5.4-5.5.
CREATE TABLE IF NOT EXISTS citation_events (
  event_id          SERIAL PRIMARY KEY,
  event_key         TEXT UNIQUE,                 -- 'E07' for ground-truth rows
  provision_id      TEXT NOT NULL REFERENCES provisions,
  judgment_id       TEXT REFERENCES judgments,   -- NULL for statutory events
  event_type        TEXT NOT NULL CHECK (event_type IN ('declared_unconstitutional', 'read_down', 'severed',
                      'upheld', 'interpreted', 'reversed_on_appeal', 'repealed_by_statute', 'amended_by_statute')),
  scope             TEXT NOT NULL CHECK (scope IN ('total', 'partial')),
                    -- how much of THIS section the event bears on (invalidated / adjudicated / set aside)
  scope_text        TEXT,                        -- verbatim limiting words
  subsection        TEXT,                        -- '8(2)' when the holding is limited to a sub-provision
  operative_quote   TEXT NOT NULL,               -- exact words of the order or holding
  source_paragraph  TEXT,
  effective_date    DATE,
  affects_event_id  INT REFERENCES citation_events, -- DIRECT action only (appeal / same-case directions), never precedent
  method            TEXT NOT NULL,               -- 'manual' | 'extracted'
  verified          BOOLEAN DEFAULT FALSE,
  verified_by       TEXT,                        -- 'human:leo …' | 'agent:opus …'
  confidence        REAL,
  notes             TEXT
);
