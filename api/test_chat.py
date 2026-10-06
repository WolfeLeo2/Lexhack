"""Checks for POST /api/chat (api/main.py, api/agent.py): the NDJSON stream with a fake model, limits, errors.

  uv run python -m api.test_chat
"""
import json
import time
from collections import deque

from fastapi.testclient import TestClient

from . import agent, main
from .status import statuses
from .test_agent import S204, fake_model, part

fails = []


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


def lines(r):
    return [json.loads(x) for x in r.text.splitlines() if x.strip()]


def test_labels():
    expect("label find_section", agent.step_label("find_section", {"act": "Penal Code", "section": "204"}),
           "Looking up Penal Code s.204")
    expect("label search", agent.step_label("search_sections", {"query": "criminal defamation"}),
           "Searching sections for “criminal defamation”")
    expect("label find_case", agent.step_label("find_case", {"citation": "Okuta v AG"}), "Looking for the case “Okuta v AG”")
    expect("label truncated", agent.step_label("search_sections", {"query": "x" * 100}),
           f"Searching sections for “{'x' * 80}…”")
    for name in ("get_section", "citing_judgments", "list_acts", "check_text", "unknown_tool"):
        expect(f"label {name} plain", bool(agent.step_label(name, {"text": "x"})), True)
    expect("history", agent.history_from_turns([{"question": "q", "answer": "a"}]),
           [{"role": "user", "parts": [{"text": "q"}]}, {"role": "model", "parts": [{"text": "a"}]}])


def test_stream(c):
    agent.generate = fake_model([part(functionCall={"name": "find_section", "args": {"act": "Penal Code", "section": "204"}}),
                                 part(text=f"**s.204**: [[section:{S204}]] and [[event:999999]].")])
    r = c.post("/api/chat", json={"question": "Is s.204 of the Penal Code good law?",
                                  "history": [{"question": "hi", "answer": "hello"}]})
    expect("200", r.status_code, 200)
    expect("ndjson", r.headers["content-type"].startswith("application/x-ndjson"), True)
    ev = lines(r)
    expect("order", [e["type"] for e in ev], ["step", "answer", "done"])
    expect("step", ev[0], {"type": "step", "tool": "find_section", "label": "Looking up Penal Code s.204"})
    ans = ev[1]
    expect("removed", ans["removed"], 1)
    with main.db() as conn:
        want, invented = agent.render(f"**s.204**: [[section:{S204}]] and [[event:999999]].", {"section": [S204]}, conn)
        status = statuses(conn, [S204])[S204]
    expect("text is render()", ans["text"], want)
    expect("kinds", [p["kind"] for p in ans["parts"]], ["text", "section", "text", "removed", "text"])
    sec = ans["parts"][1]
    expect("section status = resolver", sec["status"], status)
    expect("section fields", (sec["provision_id"], sec["act"], sec["number"]), (S204, "Penal Code", "204"))
    expect("done", ev[2]["disclaimer"], main.DISCLAIMER)


def test_limits(c):
    expect("long question 422", c.post("/api/chat", json={"question": "x" * 2001}).status_code, 422)
    expect("empty question 422", c.post("/api/chat", json={"question": ""}).status_code, 422)
    expect("long history 422", c.post("/api/chat", json={"question": "q", "history": [{"question": "q", "answer": "a"}] * 7})
           .status_code, 422)
    expect("long answer 422", c.post("/api/chat", json={"question": "q", "history": [{"question": "q", "answer": "a" * 4001}]})
           .status_code, 422)
    main._chat_hits.clear()
    main._chat_hits["testclient"] = deque([time.monotonic()] * main.CHAT_RATE)   # ten questions this minute
    r = c.post("/api/chat", json={"question": "q"})
    expect("11th in a minute 429", (r.status_code, "detail" in r.json()), (429, True))
    main._chat_hits.clear()


def test_error(c):
    def boom(body, api_key):
        raise RuntimeError("secret internals: key=abc")
    agent.generate = boom
    ev = lines(c.post("/api/chat", json={"question": "q"}))
    expect("error event", [e["type"] for e in ev], ["error"])
    expect("no internals", "secret" in ev[0]["message"], False)


def run():
    real = agent.generate
    try:
        test_labels()
        with TestClient(main.app) as c:
            main._chat_hits.clear()
            test_stream(c)
            test_limits(c)
            test_error(c)
    finally:
        agent.generate = real
    for f in fails:
        print("FAIL", *f)
    print(f"{len(fails)} failures")
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    run()
