"""DeepSeek chat call returning JSON, cached on disk by a caller-supplied key. Shared by classify_events and
verify_events. Retries network errors and 429/5xx; stops cleanly on HTTP 402 (balance empty)."""
import json
import time

import requests

from crawler.config import require_env

URL = "https://api.deepseek.com/chat/completions"


def call_json(prompt, cache, key, model="deepseek-flash", thinking=False):
    """-> (parsed JSON dict, whether an API call was made). Unparseable replies are cached as {"error": ...}."""
    path = cache / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), False
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}, "thinking": {"type": "enabled" if thinking else "disabled"}}
    if not thinking:
        body["temperature"] = 0   # not supported in thinking mode
    for attempt in range(8):
        wait = min(120, 10 * 2 ** attempt)
        try:
            r = requests.post(URL, json=body, timeout=600,
                              headers={"Authorization": f"Bearer {require_env('DEEPSEEK_API_KEY')}"})
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            # ChunkedEncodingError: the connection dropped mid-reply
            print(f"  network error ({type(e).__name__}); retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 402:
            raise SystemExit("DeepSeek balance is empty (HTTP 402): top up; answers so far are cached.")
        if r.status_code in (429, 500, 502, 503):
            print(f"  HTTP {r.status_code}; retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]["content"]
        try:
            out = json.loads(msg)
        except json.JSONDecodeError:
            out = {"error": "unparseable", "raw": msg[:2000]}
        path.write_text(json.dumps(out), encoding="utf-8")
        return out, True
    raise RuntimeError("DeepSeek call failed after 8 attempts")
