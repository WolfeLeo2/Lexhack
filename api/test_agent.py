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
        text = f"See [[event:{eid[0]}]] and [[section:{S204}]] but not [[event:999999]] or [[event:{eid[0]}, 5]]."
        expect("refs", agent.refs(text), [("event", str(eid[0])), ("section", S204), ("event", "999999"),
                                          (None, f"[[event:{eid[0]}, 5]]")])
        out, invented = agent.render(text, {"event": [str(eid[0])], "section": [S204]}, conn)
        st = conn.execute("SELECT event_id FROM citation_events WHERE judgment_id IS NULL AND verified_by LIKE 'source:%%' "
                          "ORDER BY event_id LIMIT 1").fetchone()
        sout, _ = agent.render(f"[[event:{st[0]}]]", {"event": [str(st[0])]}, conn)
    expect("statutory event label", "from Kenya Law's reviser's note)" in sout, True)
    expect("statutory event not AI-labelled", "AI reviewer" in sout, False)
    expect("verbatim quote filled in", eid[1] in out, True)
    expect("invented removed", "[unverified reference removed]" in out, True)
    expect("invented and malformed counted", invented, 2)
    expect("malformed removed", out.count("[unverified reference removed]"), 2)
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
    with main.POOL:
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
