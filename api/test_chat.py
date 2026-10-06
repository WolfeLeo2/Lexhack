"""Checks for POST /api/chat (api/main.py, api/agent.py): the NDJSON stream with a fake model, limits, errors.

  uv run python -m api.test_chat
"""
import json
import os
import time
from collections import deque

from fastapi.testclient import TestClient

from . import agent, main, tools
from .status import provision_status, statuses
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
    expect("label find_section, no section", agent.step_label("find_section", {"act": "Penal Code"}), "Looking up the section")
    expect("label find_section, no act", agent.step_label("find_section", {"section": "204"}), "Looking up the section")
    expect("history", agent.history_from_turns([{"question": "q", "answer": "a"}]),
           [{"role": "user", "parts": [{"text": "q"}]}, {"role": "model", "parts": [{"text": "a"}]}])


def test_stream(c):
    shown = {int(e) for e in tools.call("get_section", {"provision_id": S204})["ids"]["event"]}
    with main.db() as conn:
        hist = [e for e in provision_status(conn, S204)["history"] if e["event_id"] in shown]
        quotes = dict(conn.execute("SELECT event_id, operative_quote FROM citation_events WHERE event_id = ANY(%s)",
                                   ([e["event_id"] for e in hist],)).fetchall())
    disp = next(e["event_id"] for e in hist if e["state"] == "displaced by a later ruling")
    live = next(e["event_id"] for e in hist if e["state"] == "in effect" and (e.get("verified_by") or "").startswith("agent:"))
    answer = f"**s.204**: [[section:{S204}]] and [[event:999999]]. [[event:{disp}]] [[event:{live}]]"
    agent.generate = fake_model([part(functionCall={"name": "find_section", "args": {"act": "Penal Code", "section": "204"}}),
                                 part(functionCall={"name": "get_section", "args": {"provision_id": S204}}),
                                 part(text=answer)])
    r = c.post("/api/chat", json={"question": "Is s.204 of the Penal Code good law?",
                                  "history": [{"question": "hi", "answer": "hello"}]})
    expect("200", r.status_code, 200)
    expect("ndjson", r.headers["content-type"].startswith("application/x-ndjson"), True)
    ev = lines(r)
    expect("order", [e["type"] for e in ev], ["step", "step", "answer", "done"])
    expect("step", ev[0], {"type": "step", "tool": "find_section", "label": "Looking up Penal Code s.204"})
    ans = ev[2]
    expect("removed", ans["removed"], 1)
    with main.db() as conn:
        want, invented = agent.render(answer, {"section": [S204], "event": [str(disp), str(live)]}, conn)
        status = statuses(conn, [S204])[S204]
    expect("text is render()", ans["text"], want)
    expect("kinds", [p["kind"] for p in ans["parts"]],
           ["text", "section", "text", "removed", "text", "ruling", "text", "ruling"])
    d, l = ans["parts"][5], ans["parts"][7]
    expect("displaced: state", (d["event_id"], d["state"]), (disp, "displaced by a later ruling"))
    expect("in effect: no state", (l["event_id"], l["state"]), (live, None))
    expect("checked_by", (d["checked_by"], l["checked_by"]), ("checked by an AI reviewer",) * 2)
    expect("quotes verbatim", (d["quote"], l["quote"]), (quotes[disp], quotes[live]))
    sec = ans["parts"][1]
    expect("section status = resolver", sec["status"], status)
    expect("section fields", (sec["provision_id"], sec["act"], sec["number"]), (S204, "Penal Code", "204"))
    expect("done", ev[3]["disclaimer"], main.DISCLAIMER)


def test_draft(c):
    with main.db() as conn:
        ids = [e["event_id"] for e in provision_status(conn, S204)["summary_events"]]
    first = f"It is submitted that [[section:{S204}]] governs. See Wanjiru v Kamau [2031] eKLR."
    revised = f"It is submitted that [[section:{S204}]] governs, as limited by [[event:{ids[0]}]]."
    bodies = []
    agent.generate = fake_model([part(functionCall={"name": "find_section", "args": {"act": "Penal Code", "section": "204"}}),
                                 part(text=first), part(text=revised)], bodies)
    ev = lines(c.post("/api/chat", json={"question": "Draft a paragraph on s.204", "mode": "draft"}))
    expect("draft order", [(e["type"], e.get("tool")) for e in ev],
           [("step", "find_section"), ("step", "check"), ("step", "revise"), ("answer", None), ("done", None)])
    expect("check label", ev[1]["label"], "Checking the draft's citations")
    expect("draft system prompt", agent.DRAFT.strip() in bodies[0]["systemInstruction"]["parts"][0]["text"], True)
    sent = next(c["parts"][0]["text"] for c in bodies[-1]["contents"]   # the body's list grows after the call
                if c["role"] == "user" and "citation check" in c["parts"][0].get("text", ""))
    expect("revise turn lists the section's ruling", f"[[event:{ids[0]}]]" in sent, True)
    expect("revise turn lists the fake case", "[2031] eKLR" in sent, True)
    ans = ev[3]
    expect("revised draft used", any(p["kind"] == "ruling" and p["event_id"] == ids[0] for p in ans["parts"]), True)
    expect("clean after revision", ans["check"], [])
    expect("draft label", ans["label"], agent.DRAFT_LABEL)

    # the revision keeps the invented case: still reported
    agent.generate = fake_model([part(text=first), part(text=revised + " See Wanjiru v Kamau [2031] eKLR.")])
    ans = [e for e in lines(c.post("/api/chat", json={"question": "Draft", "mode": "draft"})) if e["type"] == "answer"][0]
    expect("fake case reported", [(f["kind"], f["raw_text"], f["result"]) for f in ans["check"]],
           [("case", "[2031] eKLR", "not_in_collection")])

    # clean first time: no revise step, one model call
    agent.generate = fake_model([part(text=revised)])
    ev = lines(c.post("/api/chat", json={"question": "Draft", "mode": "draft"}))
    expect("clean: no revise", [e.get("tool") for e in ev if e["type"] == "step"], ["check"])
    agent.generate = fake_model([part(text="ok")])
    expect("answer mode: no check", "check" in lines(c.post("/api/chat", json={"question": "q"}))[-2], False)
    expect("bad mode 422", c.post("/api/chat", json={"question": "q", "mode": "essay"}).status_code, 422)


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
    main._chat_hits["*"] = deque([time.monotonic()] * main.CHAT_GLOBAL_RATE)   # everyone, this minute
    r = c.post("/api/chat", json={"question": "q"})
    expect("global cap 429 busy", (r.status_code, r.json().get("detail")), (429, main.CHAT_BUSY))
    main._chat_hits.clear()
    held = [main.CHAT_SLOTS.acquire(blocking=False) for _ in range(4)]
    r = c.post("/api/chat", json={"question": "q"})
    expect("four running: 429 busy", (all(held), r.status_code, r.json().get("detail")), (True, 429, main.CHAT_BUSY))
    for _ in held:
        main.CHAT_SLOTS.release()
    main._chat_hits.clear()


def test_proxy_key(c):
    agent.generate = fake_model([part(text="ok")] * 4)
    os.environ["CHAT_PROXY_SECRET"] = "s3cret"
    try:
        main._chat_hits.clear()
        main._chat_hits["web:1.1.1.1"] = deque([time.monotonic()] * main.CHAT_RATE)

        def post(key, ip):
            return c.post("/api/chat", json={"question": "q"},
                          headers={"x-hakiki-proxy-key": key, "x-hakiki-client-ip": ip}).status_code
        expect("proxy: full bucket", post("s3cret", "1.1.1.1"), 429)
        expect("proxy: other client, own bucket", post("s3cret", "2.2.2.2"), 200)
        expect("wrong secret falls back to the caller's IP", post("wrong", "1.1.1.1"), 200)
        main._chat_hits["testclient"] = deque([time.monotonic()] * main.CHAT_RATE)
        expect("wrong secret uses the caller's bucket", post("wrong", "2.2.2.2"), 429)
    finally:
        del os.environ["CHAT_PROXY_SECRET"]
        main._chat_hits.clear()


def test_deadline(c):
    def slow(body, api_key, **kw):   # past the deadline, then a tool call: the stopped run must end there
        time.sleep(0.6)
        return part(functionCall={"name": "list_acts", "args": {}})
    agent.generate, real = slow, main.CHAT_DEADLINE
    main.CHAT_DEADLINE = 0.2
    try:
        ev = lines(c.post("/api/chat", json={"question": "q"}))
    finally:
        main.CHAT_DEADLINE = real
    expect("deadline: one error event", ev, [{"type": "error", "message": main.CHAT_TIMEOUT}])
    time.sleep(0.8)
    expect("stopped run ended at its next tool call, slot released", main.CHAT_SLOTS.acquire(blocking=False) and all(
        main.CHAT_SLOTS.acquire(blocking=False) for _ in range(3)), True)
    for _ in range(4):
        main.CHAT_SLOTS.release()


def test_error(c):
    def boom(body, api_key, **kw):
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
            test_draft(c)
            test_limits(c)
            test_error(c)
            test_proxy_key(c)
            test_deadline(c)
    finally:
        agent.generate = real
    for f in fails:
        print("FAIL", *f)
    print(f"{len(fails)} failures")
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    run()
