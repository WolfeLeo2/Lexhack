"""Embed provision texts with gemini-embedding-2 (1536 dims, L2-normalised) into provision_texts.embedding.

  uv run python -m pipeline.embed

Only rows with embedding IS NULL are sent. Every vector is cached on disk by input hash
($LEXHACK_DATA/cache/embeddings/), so re-runs and identical texts across versions cost nothing.
Needs GEMINI_API_KEY in .env.
"""
import hashlib
import json
import math
import time

import requests

from crawler.config import data_dir, require_env

from .db import connect

MODEL, DIMS, TASK = "gemini-embedding-2", 1536, "RETRIEVAL_DOCUMENT"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents"
BATCH = 50
# ponytail: the model reads at most 8,192 tokens; anything longer is embedded from its start only.
# Fine for statute sections; judgments will need chunking.


def key(text):
    return hashlib.sha256(f"{MODEL}|{DIMS}|{TASK}|{text}".encode()).hexdigest()


def normalise(v):   # embedding-2 already returns unit vectors; kept so a model swap can't silently break cosine
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def embed_batch(texts, api_key):
    body = {"requests": [{"model": f"models/{MODEL}", "content": {"parts": [{"text": t}]},
                          "taskType": TASK, "outputDimensionality": DIMS} for t in texts]}
    for attempt in range(10):   # per-minute quotas can take a few minutes to clear
        wait = min(120, 10 * 2 ** attempt)
        try:
            r = requests.post(URL, json=body, headers={"x-goog-api-key": api_key}, timeout=120)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 429 and "PerDay" in r.text:   # waiting minutes won't help; progress is cached
            raise SystemExit("Gemini daily quota exhausted (free tier: 1,000 texts/day/model). Re-run tomorrow "
                             "or enable billing on the key; already-embedded texts are cached.")
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return [normalise(e["values"]) for e in r.json()["embeddings"]]
    raise RuntimeError("embedding failed after 10 attempts (network or rate limit)")


def main():
    api_key = require_env("GEMINI_API_KEY")
    cache = data_dir() / "cache" / "embeddings"
    cache.mkdir(parents=True, exist_ok=True)
    with connect() as conn:   # don't hold a connection open while calling the API (Neon drops idle ones)
        rows = conn.execute("SELECT provision_id, version_id, text FROM provision_texts WHERE embedding IS NULL").fetchall()
    todo = sorted({t for _, _, t in rows if not (cache / f"{key(t)}.json").exists()})
    print(f"{len(rows)} rows without embeddings; {len(todo)} unique texts to embed", flush=True)
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        for t, v in zip(chunk, embed_batch(chunk, api_key)):
            (cache / f"{key(t)}.json").write_text(json.dumps(v))
        print(f"  embedded {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany("UPDATE provision_texts SET embedding = %s::vector WHERE provision_id = %s AND version_id = %s",
                            [((cache / f"{key(t)}.json").read_text(), p, v) for p, v, t in rows])
    print(f"stored {len(rows)} embeddings")


if __name__ == "__main__":
    main()
