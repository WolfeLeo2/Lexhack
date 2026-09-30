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
