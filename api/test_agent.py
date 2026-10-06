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
    expect("in-effect ruling: no state", "displaced" in out or "reversed" in out, False)
    with main.db() as conn:   # on s.204 the 2017 Muruatetu rulings are displaced by the 2021 directions
        from .status import provision_status
        d = next(e["event_id"] for e in provision_status(conn, S204)["history"]
                 if e["state"] == "displaced by a later ruling")
        dout, _ = agent.render(f"[[event:{d}]]", {"event": [str(d)]}, conn)
    expect("displaced ruling: state shown", "; displaced by a later ruling)" in dout, True)
    with main.db() as conn:   # naming a held Act is plain text, not a removed reference; an Act we don't hold is
        aparts, aremoved = agent.render_parts("[[act:penal code]], [[act:ke/act/cap-63a]] and [[act:Land Act]]", {}, conn)
        j = conn.execute("SELECT judgment_id, title, neutral_citation FROM judgments WHERE position(neutral_citation "
                         "in title) > 0 LIMIT 1").fetchone()
        jout, _ = agent.render(f"[[judgment:{j[0]}]]", {"judgment": [j[0]]}, conn)
    expect("act refs", [p.get("text", p["kind"]) for p in aparts],
           ["Penal Code", ", ", "Sexual Offences Act", " and ", "removed"])
    expect("act refs: only the unheld one removed", aremoved, 1)
    expect("citation not repeated after a title carrying it", jout.count(j[2]), j[1].count(j[2]))


def test_grouped():
    """The model sometimes groups references: [[event:1], [judgment:x]]. Each is rendered on its own; none leaks."""
    with main.db() as conn:
        x, y = [str(r[0]) for r in conn.execute("SELECT event_id FROM citation_events WHERE provision_id = %s AND "
                                                "verified ORDER BY event_id LIMIT 2", (S204,))]
        j = conn.execute("SELECT judgment_id FROM judgments WHERE has_full_text LIMIT 1").fetchone()[0]
        expect("grouped refs", agent.refs(f"[[event:{x}], [judgment:{j}]] [[event:{x}],[event:{y}]]"),
               [("event", x), ("judgment", j), ("event", x), ("event", y)])
        parts, removed = agent.render_parts(f"See [[event:{x}], [event:{y}]].", {"event": [x, y]}, conn)
        expect("grouped: both rulings", [p.get("event_id") for p in parts if p["kind"] == "ruling"], [int(x), int(y)])
        expect("grouped: none removed", removed, 0)
        parts, removed = agent.render_parts(f"See [[event:{x}], [event:999999]].", {"event": [x]}, conn)
        expect("grouped, one unseen: removed and counted", ([p["kind"] for p in parts if p["kind"] != "text"], removed),
               (["ruling", "removed"], 1))
        outs = [agent.render(t, {"event": [x, y], "judgment": [j]}, conn)[0] for t in (
            f"[[event:{x}], [judgment:{j}]]", "a [[event:1 unclosed", "stray ke/judgment/x]] b", "[[]] [[event:1, 2]]",
            f"[[event:{x}], [section:nope]] and [[judgment:{j}]]")]
    expect("no [[ or ]] in any rendered output", [o for o in outs if "[[" in o or "]]" in o], [])
    expect("unclosed reference dropped", outs[1], "a  unclosed")


def fake_model(replies, bodies=None):
    """generate() stand-in: returns the queued replies in order; records each request body in bodies."""
    it = iter(replies)

    def gen(body, api_key, **kw):
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
        expect("tool error: type only, no message", out["steps"][0]["result"]["error"].startswith("tool failed: "), True)
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


def test_prompt():   # the 1a rules: case names as written; advice questions still look the section up
    expect("prompt: no invented citation", "never add a year" in agent.SYSTEM, True)
    expect("prompt: advice still looks up", "Don't skip the lookup" in agent.SYSTEM, True)


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
        test_grouped()
        test_loop()
        test_prompt()
        if "--live" in sys.argv:
            test_live()
    for f in fails:
        print("FAIL", *f)
    print(f"{len(fails)} failures")
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    run()
