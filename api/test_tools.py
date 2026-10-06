"""Checks for the agent tools (api/tools.py) against Neon.

  uv run python -m api.test_tools
"""
from . import main, tools

fails = []
S204 = "ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204"
S194 = "ke/act/cap-63/part_II__chp_XVIII__sec_194"
S45, S45_OLD = "ke/act/cap-226/part_VI__sec_45", "ke/act/cap-226/sec_45"


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


def test_declarations():
    d = {x["name"]: x for x in tools.DECLARATIONS}
    expect("seven tools", sorted(d), sorted(["list_acts", "search_sections", "get_section", "find_section",
                                             "citing_judgments", "find_case", "check_text"]))
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
    shown = out["result"]["summary_events"] + out["result"]["history"]
    expect("events carry judgment_id", all(e["judgment_id"] for e in shown if e["title"]), True)
    expect("judgment ids seen", set(out["ids"]["judgment"]) == {e["judgment_id"] for e in shown if e["judgment_id"]},
           True)
    expect("history capped", len(out["result"]["history"]) <= tools.MAX_HISTORY, True)
    expect("text capped", len(out["result"]["text"]) <= tools.MAX_TEXT, True)


def test_search_and_cases():
    out = tools.search_sections("criminal defamation")
    expect("finds s.194", S194 in out["ids"]["section"], True)
    out = tools.find_case("Jacqueline Okuta & another v Attorney General & 2 others [2017] eKLR")
    expect("Okuta found", out["result"]["cases"][0]["result"], "found")
    expect("Okuta events", any(e["provision_id"] == S194 for e in out["result"]["events"]), True)
    ev = next(e for e in out["result"]["events"] if e["provision_id"] == S194)
    expect("event carries Act and section", (ev["act_title"], ev["section_number"], bool(ev["heading"])),
           ("Penal Code", "194", True))
    out = tools.find_case("Wachira & 12 others v Republic & 2 others [2022] eKLR")   # eKLR path: one-word candidates
    expect("unconfirmed citation falls back to titles", ("ke/judgment/kehc/2022/12795" in out["ids"]["judgment"],
                                                         "979" in out["ids"]["event"]), (True, True))
    for c in ("Otieno v Republic [2019] eKLR", "Republic v Kamau [2018] eKLR",   # 9 / many titles start so
              "Joseph Otieno v Republic", "Peter Mwangi v Republic [2019] eKLR",
              "Okuta v Republic", "Andare v Republic", "Republic v Ibrahim"):   # wrong party; a name cut short
        out = tools.find_case(c)
        expect(f"common name with citation: nothing confirmed: {c}",
               (any(t["confirmed"] for t in out["result"]["title_matches"]), out["ids"]["event"],
                out["ids"]["judgment"]), (False, [], []))
    out = tools.find_case("John Kamau v Republic")   # 3 titles hold the words; one is exactly that name
    expect("only the title named exactly so is confirmed",
           [t["judgment_id"] for t in out["result"]["title_matches"] if t["confirmed"]], ["ke/judgment/keca/2007/472"])
    out = tools.find_case("Muruatetu v Republic (2021)")   # 2016/2017/2021 titles: at most one confirmed
    conf = [t for t in out["result"]["title_matches"] if t["confirmed"]]
    print("Muruatetu (2021) confirmed:", [(t["judgment_id"], t["decision_date"]) for t in conf])
    expect("Muruatetu (2021): at most one, of that year", all(t["decision_date"][:4] == "2021" or "[2021]" in t["title"]
                                                             for t in conf) and len(conf) <= 1, True)
    out = tools.find_case("Okuta v Attorney General (2017)")
    expect("year agrees: confirmed", any(t["confirmed"] for t in out["result"]["title_matches"]), True)
    out = tools.find_case("Okuta v Attorney General (2015)")
    t = out["result"]["title_matches"][0]
    expect("year conflicts: flagged, not confirmed", (t["confirmed"], t.get("year_mismatch"), out["ids"]["event"]),
           (False, True, []))
    out = tools.find_case("Okuta")   # one word in exactly one held title: that case
    expect("name only falls back to titles", len(out["result"]["title_matches"]) > 0, True)
    expect("unique word: confirmed", out["result"]["title_matches"][0]["confirmed"], True)
    expect("unique word: its rulings", any(e["provision_id"] == S194 for e in out["result"]["events"]), True)
    expect("unique word: not ambiguous", out["result"]["ambiguous"], False)
    out = tools.find_case("Kimaru & 17 others v Attorney General")   # 'kimaru' alone is in 4 titles; all words: one
    expect("full name breaks the tie", (out["ids"]["judgment"], out["result"]["ambiguous"]),
           (["ke/judgment/kehc/2022/114"], False))
    expect("full name: its rulings", len(out["ids"]["event"]) > 0, True)
    for q in ("Summarise the ruling in Kimaru & 17 others v Attorney General",
              "Did the court in Kimaru & 17 others v Attorney General strike anything down?"):
        expect(f"question around a full name: {q}", tools.find_case(q)["ids"]["judgment"],
               ["ke/judgment/kehc/2022/114"])
    for q in ("What did the court hold in Republic v Mwangi?",   # 'court' once tied this to an unrelated case
              "What did the High Court and the Court of Appeal decide in Republic v Mwangi?"):
        out = tools.find_case(q)
        expect(f"question, court words don't count: {q}", (out["result"]["ambiguous"], out["ids"]["event"],
               any(t["confirmed"] for t in out["result"]["title_matches"])), (True, [], False))
    expect("party span", tools.party_span("What did the High Court decide in Okuta v Attorney General on criminal "
                                          "defamation?"), "Okuta v Attorney General")
    out = tools.find_case("Republic v Mwangi")   # many titles have both words
    expect("common full name: ambiguous, no events", (out["result"]["ambiguous"], out["ids"]["event"]), (True, []))
    out = tools.find_case("Mwangi")   # one word in many titles: no rulings from unrelated judgments
    expect("one word: no rulings", out["ids"]["event"], [])
    expect("one word: unconfirmed, ambiguous", (any(t["confirmed"] for t in out["result"]["title_matches"]),
                                                out["result"]["ambiguous"]), (False, True))
    out = tools.find_case("the ruling in Kimaru v Attorney General; Kenya National Human Rights and Equality "
                          "Commission")   # 9 titles say Kimaru; Okimaru isn't one
    expect("name only: held case with rulings first", out["ids"]["judgment"][:1], ["ke/judgment/kehc/2022/114"])
    expect("name only: whole words", any("Okimaru" in t["title"] for t in out["result"]["title_matches"]), False)
    expect("name only: its rulings listed", len(out["ids"]["event"]) > 0, True)
    out = tools.find_case("Matemu v Trusted Society of Human Rights Alliance")
    expect("name only: Matemu", "Matemu" in out["result"]["title_matches"][0]["title"], True)
    out = tools.find_case("Zzyzx Mwangi")   # shares one common word with many held titles
    expect("one shared word: no titles, no rulings", (out["result"]["title_matches"], out["ids"]["event"]), ([], []))
    out = tools.find_case("Zzyzx Mwangi Kamau")   # 2 of 3 words: partial matches allowed, but carry no rulings
    expect("partial match: no rulings", out["ids"]["event"], [])
    expect("partial match: labelled", all(t["words_matched"] < t["words_total"] and not t["confirmed"]
                                          for t in out["result"]["title_matches"]), True)
    expect("partial match: not referenceable", out["ids"]["judgment"], [])
    out = tools.find_case("Zzyzx Quabble v Republic [2019] eKLR")
    expect("invented case not found", out["result"]["cases"][0]["result"] != "found", True)
    out = tools.find_case("Republic v Mwangi [2019] eKLR")   # vague: the matcher offers candidates only
    case = out["result"]["cases"][0]
    cand = {j["judgment_id"] for j in case["candidates"]}
    expect("possible match: returned", (case["result"], len(cand) > 0), ("possible_match", True))
    expect("possible match: no candidate id", cand & set(out["ids"]["judgment"]), set())
    expect("possible match: no candidate event", [e for e in out["result"]["events"] if e["judgment_id"] in cand], [])


def test_find_section():
    out = tools.find_section("Penal Code", "189")
    expect("found s.189", (out["result"]["found"], out["result"]["status"]), (True, "repealed"))
    expect("s.189 id", out["ids"]["section"], [out["result"]["provision_id"]])
    expect("cap number", tools.find_section("cap 63", "204")["result"]["provision_id"], S204)
    expect("s. prefix", tools.find_section("Cap. 63", "s.204")["result"]["provision_id"], S204)
    expect("lower case", tools.find_section("penal code", "194")["result"]["provision_id"], S194)
    expect("subsection", tools.find_section("Sexual Offences Act", "8(2)")["result"]["number"], "8")
    expect("article", tools.find_section("Constitution", "Article 50")["result"]["found"], True)
    expect("year after the name", tools.find_section("Constitution of Kenya 2010", "50")["result"]["found"], True)
    expect("cap in brackets", tools.find_section("Penal Code (Cap. 63)", "204")["result"].get("provision_id"), S204)
    out = tools.find_section("Penal Code", "999")
    expect("section not held", (out["result"]["found"], out["result"]["reason"], out["result"]["act_id"]),
           (False, "section_not_held", "ke/act/cap-63"))
    expect("section not held: no ids", out["ids"]["section"], [])
    out = tools.find_section("Land Registration Act", "26")["result"]
    expect("act not recognised", (out["found"], out["reason"], "Penal Code" in out["held_acts"]),
           (False, "act_not_recognised", True))
    for act, sec, slug in [("Cap 7", "34", "cap-7"), ("Elections Act, Cap 7", "34", "cap-7"),
                           ("Sexual Offences Act No. 3 of 2006", "8", "cap-63a"),
                           ("Elections Act No. 24 of 2011", "34", "cap-7"), ("The Penal Code Act", "204", "cap-63"),
                           ("KICA Act", "29", "cap-411a")]:
        out = tools.find_section(act, sec)["result"]
        expect(f"act named as {act!r}", (out["found"], (out.get("provision_id") or "").startswith(f"ke/act/{slug}/")),
               (True, True))
    # Law of Succession s.43 moved from Part V (to 2019) to Part VI (from 2021): versions don't overlap, a renumbering
    out = tools.find_section("Law of Succession Act", "43")["result"]
    expect("succession s.43: renumbered, current id", (out.get("ambiguous"), out.get("provision_id"),
           [x["provision_id"] for x in out.get("renumbered_from", [])]),
           (None, "ke/act/cap-160/part_VI__sec_43", ["ke/act/cap-160/part_V__sec_43"]))
    out = tools.find_section("Employment Act", "45")   # renumbered in 2022: rulings sit on the old ID
    expect("employment act s.45: current id with the old id's ruling",
           (out["result"].get("ambiguous"), out["ids"]["section"], out["result"].get("status")),
           (None, [S45], "limited by a court"))
    expect("employment act s.45: old id and versions", [(x["provision_id"], bool(x["versions"]))
                                                         for x in out["result"].get("renumbered_from", [])],
           [(S45_OLD, True)])
    expect("employment act s.1: current id", tools.find_section("Employment Act", "1")["result"].get("provision_id"),
           "ke/act/cap-226/part_1__sec_1")
    out = tools.get_section(S45)["result"]
    expect("get_section s.45: ruling on the old numbering", ([(e["event_id"], e["provision_id"])
           for e in out["summary_events"]], out["renumbered_from"]["provision_id"]), ([(925, S45_OLD)], S45_OLD))


def test_renumbered_pages():
    new, old = main.provision(S45), main.provision(S45_OLD)
    expect("s.45 status merged", (new.status, old.status), ("limited by a court", "limited by a court"))
    expect("s.45 Momanyi in summary", [e.event_id for e in new.summary_events], [925])
    expect("s.45 links", (new.renumbered_from.provision_id, new.renumbered_to, old.renumbered_to.provision_id,
                          old.renumbered_from), (S45_OLD, None, S45, None))
    expect("s.45 citations cover both ids", main.citations(S45, 1).total, new.cited_by)
    p = main.provision(S194)
    expect("no renumbering: unchanged", (p.renumbered_from, p.renumbered_to, p.status), (None, None, "limited by a court"))
    s45 = [x.provision_id for x in main.act_provisions("ke/act/cap-226") if x.number == "45"]
    expect("acts list: s.45 once, current id", s45, [S45])
    for sec in ("", "two hundred and four"):
        expect(f"no number {sec!r}", tools.find_section("Penal Code", sec)["result"]["reason"], "no_section_number")


def test_call():
    expect("dispatch", tools.call("list_acts", {})["result"][0].keys() >= {"act_id", "title"}, True)
    out = tools.citing_judgments(S204, 3)
    expect("citing capped", len(out["result"]["judgments"]) <= 3, True)
    expect("citing ids", len(out["ids"]["judgment"]), len(out["result"]["judgments"]))


def main_():
    with main.POOL:   # opens the pool and closes it on exit
        for t in (test_declarations, test_get_section, test_find_section, test_renumbered_pages, test_search_and_cases,
                  test_call):
            t()
    for f in fails:
        print("FAIL", *f)
    print(f"{len(fails)} failures")
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    main_()
