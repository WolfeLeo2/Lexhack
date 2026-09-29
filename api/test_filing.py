"""Checks for the filing checker (api/filing.py). Pure checks first, then the three demo filings end to end
against Neon and local data.

  uv run python -m api.test_filing
"""
from pathlib import Path

from . import filing

fails = []


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


MURUATETU = ("Muruatetu & another v Republic; Katiba Institute & 5 others (Amicus Curiae) (Petition 15 & 16 of 2015 "
             "(Consolidated)) [2017] KESC 2 (KLR) (14 December 2017) (Judgment)")


def test_cases():
    c = filing.find_cases("On sentence, the Supreme Court in Muruatetu & another v Republic [2017] KESC 2 (KLR) observed")
    expect("one case", len(c), 1)
    expect("citation", c[0]["citation"], "[2017] KESC 2 (KLR)")
    expect("cited name", c[0]["cited_name"], "Muruatetu & another v Republic")
    expect("raw text", c[0]["raw_text"], "[2017] KESC 2 (KLR)")
    c = filing.find_cases("as held in [2019]KECA 5.")
    expect("no space, no (KLR)", c[0]["citation"], "[2019] KECA 5 (KLR)")
    expect("no name", c[0]["cited_name"], None)
    expect("eKLR is slice 2", filing.find_cases("Okuta v AG [2017] eKLR"), [])
    expect("v. abbreviation", filing.find_cases("Republic v. Mwangi [2022] KECA 1106 (KLR)")[0]["cited_name"],
           "Republic v. Mwangi")
    expect("lead-in dropped", filing.find_cases("In Okuta v Attorney General [2017] KESC 2 (KLR) the")[0]["cited_name"],
           "Okuta v Attorney General")
    expect("wrong case", filing.names_agree("Okuta v Attorney General", MURUATETU), False)
    expect("right case", filing.names_agree("Muruatetu & another v Republic", MURUATETU), True)
    expect("only generic parties", filing.names_agree("Republic v Attorney General", MURUATETU), True)
    expect("no name given", filing.names_agree(None, MURUATETU), True)


JT = ("1. The appellant was convicted of murder.\n"
      "2. The mandatory nature of the death sentence as provided for under section 204 of the Penal Code is hereby "
      "declared unconstitutional.\n3. Costs to follow the event.")


def test_quotes():
    m = filing.match_quote("the mandatory nature of the death sentence as provided for under section 204", JT)
    expect("verbatim", m["result"], "verbatim")
    expect("verbatim offset", m["char_start"], JT.index("The mandatory"))
    expect("verbatim court text", m["court_text"],
           "The mandatory nature of the death sentence as provided for under section 204")
    m = filing.match_quote("The Mandatory nature of the death-sentence, as provided for under Section 204", JT)
    expect("case, dash, comma ignored", m["result"], "verbatim")
    m = filing.match_quote("The mandatory nature of the death sentence ... is hereby declared unconstitutional", JT)
    expect("ellipsis", m["result"], "verbatim")
    m = filing.match_quote("is hereby declared unconstitutional … The mandatory nature of the death sentence", JT)
    expect("ellipsis parts out of order", m["result"] == "verbatim", False)
    m = filing.match_quote("The mandatory nature of the death sentence as provided for under section 204 of the Penal "
                           "Code is declared unconstitutional", JT)
    expect("close", (m["result"], m["similarity"]), ("close", 0.95))
    m = filing.match_quote("we find the office of the court", "Then we \ufb01nd the o\ufb03ce of the court is vacant.")
    expect("ligatures in a judgment match plain letters", (m["result"], m["court_text"]),
           ("verbatim", "we \ufb01nd the o\ufb03ce of the court"))
    m = filing.match_quote("The death sentence is abolished for every offence in the Republic of Kenya", JT)
    expect("not found", (m["result"], m["court_text"]), ("not_found", None))

    text = ("1. In Okuta v AG [2017] KEHC 8382 (KLR) and Muruatetu v Republic [2017] KESC 2 (KLR) the court said "
            "\"the mandatory nature of the death sentence is unconstitutional\" and \"too short to check\".\n\n"
            "2. Elsewhere it was said that \"a quote with no case citation in its paragraph is skipped\".")
    q = filing.find_quotes(text, filing.find_cases(text))
    expect("quote to nearest citation", dict(q), {1: ["the mandatory nature of the death sentence is unconstitutional"]})


OKUTA = "parsed/judgment/akn_ke_judgment_kehc_2017_8382_eng@2017-02-06.json"


def test_text():
    expect("okuta text", "to the extent that it covers offences other than" in filing.judgment_text(OKUTA), True)


DEMO = Path(__file__).resolve().parent.parent / "web" / "public" / "demo"


def test_text_fallbacks():
    texts = {}
    pdf_only = ("[2017] KEHC 1 (KLR)", "j", "t", "c", None, None, "parsed/judgment/x.json", False)
    expect("pdf-only judgment", filing.case_text(pdf_only, texts), None)
    expect("not held", filing.case_text(None, texts), None)
    expect("no text, not checked", filing.quote_check("any quote at all", None)["result"], "not_checked")
    real, calls = filing.judgment_text, []
    def down(raw_path):
        calls.append(raw_path)
        raise OSError("R2 unreachable")
    filing.judgment_text = down
    try:
        held = ("[2017] KEHC 8382 (KLR)", "j", "t", "c", None, None, OKUTA, True)
        expect("text unreachable", filing.case_text(held, texts), None)
        filing.case_text(held, texts)
        expect("unreachable text fetched once per request", len(calls), 1)
    finally:
        filing.judgment_text = real


def test_limits():
    import time
    s = "[2017] KESC 2 (KLR) " + "“a " * 20000   # unclosed quote marks: must stay linear
    t = time.monotonic()
    filing.find_quotes(s, filing.find_cases(s))
    expect("unclosed quotes are fast", time.monotonic() - t < 1, True)
    filing.text_index.cache_clear()
    filing.match_quote("the mandatory nature of the death sentence as provided for", JT)
    filing.match_quote("the mandatory nature of the death sentence as provided for under", JT)
    expect("judgment indexed once", filing.text_index.cache_info().hits >= 1, True)


def summary(report):
    """[(kind, raw text, result, quote results or status)] for comparing a report in one line."""
    out = []
    for f in report["findings"]:
        if f["kind"] == "case":
            out.append(("case", f["raw_text"], f["case"]["result"], [q["result"] for q in f["quotes"]]))
        else:
            out.append(("section", f["raw_text"], f["section"]["result"], f["section"]["status"]))
    return out


def test_demos():
    from pipeline.db import connect
    with connect() as conn:
        idx = filing.title_index(conn)
    def real(year, name, number=None):
        r = filing.match_eklr(idx, year, name, number)
        return r["result"], sorted(row[1] for row in r["rows"])
    expect("real Muruatetu", real(2017, "Francis Karioko Muruatetu & another v Republic"),
           ("found", ["ke/judgment/kesc/2017/2"]))
    expect("real Okuta", real(2017, "Jacqueline Okuta & another v Attorney General & 2 others"),
           ("found", ["ke/judgment/kehc/2017/8382"]))
    expect("one common surname: no found", any(real(y, n)[0] == "found" for y, n in
           ((2014, "Kamau v Republic"), (2019, "Omondi v Republic"), (2014, "Otieno v Republic"),
            (2014, "Ochieng v Republic"), (2014, "Mutua v Republic"))), False)
    expect("real John Ward", real(2006, "John Ward v Standard Limited"),
           ("possible_match", ["ke/judgment/kehc/2006/2628", "ke/judgment/kehc/2006/2629"]))
    with connect() as conn:
        clean = filing.check(conn, (DEMO / "clean.txt").read_text(encoding="utf-8"))
        bad = filing.check(conn, (DEMO / "hallucinated.txt").read_text(encoding="utf-8"))
        stale = filing.check(conn, (DEMO / "stale_law.txt").read_text(encoding="utf-8"))
    expect("clean", summary(clean), [
        ("section", "section 107 of the Evidence Act", "linked", "in force; no recorded court rulings"),
        ("case", "[2021] KESC 31 (KLR)", "found", ["verbatim"]),
        ("section", "sections 203 and 204 of the Penal Code", "linked", "in force; no recorded court rulings"),
        ("section", "sections 203 and 204 of the Penal Code", "linked", "limited by a court"),
        ("case", "[2017] eKLR", "found", []),
    ])
    quote = next(f for f in clean["findings"] if f["kind"] == "case")["quotes"][0]
    expect("clean quote paragraph", quote["paragraph"], "18")
    expect("hallucinated", [s[:4] for s in summary(bad) if s[0] == "case"], [
        ("case", "[2017] KESC 2 (KLR)", "name_mismatch", []),
        ("case", "[2017] KEHC 8382 (KLR)", "found", ["not_found"]),
        ("case", "[2017] KESC 2 (KLR)", "found", ["close"]),
        ("case", "[2019] KECA 99999 (KLR)", "not_in_collection", []),
        ("case", "[2006] eKLR", "found", ["verbatim"]),
        ("case", "[2019] eKLR", "not_in_collection", []),
    ])
    ward = next(f for f in bad["findings"] if f["raw_text"] == "[2006] eKLR")["case"]
    expect("quote settles two same-name cases",
           (ward["match_basis"], ward["judgment"] and ward["judgment"]["judgment_id"], ward["candidates"]),
           ("quote", "ke/judgment/kehc/2006/2628", []))
    muru = next(f for f in clean["findings"] if f["raw_text"] == "[2017] eKLR")["case"]
    expect("eklr basis", (muru["form"], muru["match_basis"], muru["judgment"] and muru["judgment"]["judgment_id"]),
           ("eklr", "party names and year", "ke/judgment/kesc/2017/2"))
    with connect() as conn:
        same = filing.check(conn, "In John Ward v Standard Limited [2006] eKLR the court said \"the defendant's "
                                  "application is allowed in terms of the prayers\".")["findings"][0]["case"]
    expect("no settling quote stays possible", (same["result"], len(same["candidates"])), ("possible_match", 2))
    with connect() as conn:
        both = filing.check(conn, "In John Ward v Standard Limited [2006] eKLR the page read \"Skip to document content "
                                  "REPUBLIC OF KENYA IN THE HIGH COURT\".")["findings"][0]["case"]
    expect("a quote found in both candidates settles nothing", (both["result"], len(both["candidates"])),
           ("possible_match", 2))
    with connect() as conn:
        filing.title_index(conn)
        filing._INDEX["built"] -= filing.INDEX_TTL + 1
        built_before = filing._INDEX["built"]
        filing.title_index(conn)
    expect("title index rebuilt when stale", filing._INDEX["built"] > built_before, True)
    real_text, calls = filing.case_text, []
    filing.case_text = lambda row, texts: calls.append(row) or real_text(row, texts)
    try:
        with connect() as conn:
            filing.check(conn, "In John Ward v Standard Limited [2006] eKLR the court allowed the application.")
    finally:
        filing.case_text = real_text
    expect("no quotes, no judgment text fetched for the tie-break", len(calls), 0)
    expect("stale", summary(stale), [
        ("section", "Section 204 of the Penal Code", "linked", "limited by a court"),
        ("section", "section 194 of the Penal Code", "linked", "limited by a court"),
        ("section", "section 29 of the Kenya Information and Communications Act", "linked", "declared unconstitutional"),
    ])
    many = "Okuta v AG [2017] KEHC 8382 (KLR) " + " ".join(
        f'"quote number {i} with enough words to be checked"' for i in range(filing.MAX_QUOTES + 1))
    with connect() as conn:
        qs = filing.check(conn, many)["findings"][0]["quotes"]
    expect("quotes capped", (len(qs), qs[-1]["result"], qs[0]["result"] != "not_checked"),
           (filing.MAX_QUOTES + 1, "not_checked", True))
    s204 = next(f for f in stale["findings"] if f["raw_text"] == "Section 204 of the Penal Code")["section"]
    expect("court's words shown", any("mandatory nature of the death sentence" in e["operative_quote"]
                                      for e in s204["summary_events"]), True)


def test_eklr():
    t = ("the High Court in Jacqueline Okuta & another v Attorney General & 2 others (Petition No. 397 of 2016) "
         "[2017] eKLR held")
    e = filing.find_eklr(t)
    expect("eklr found", [(x["raw_text"], x["year"], x["form"]) for x in e], [("[2017] eKLR", 2017, "eklr")])
    expect("eklr name, number taken out", (e[0]["cited_name"], e[0]["case_number"]),
           ("Jacqueline Okuta & another v Attorney General & 2 others", "397 of 2016"))
    e = filing.find_eklr("relied on Gatirau Peter Munya vs Dickson Mwenda Kithinji & 3 Others [2014]eKLR relied upon")
    expect("no space, vs", (e[0]["year"], e[0]["cited_name"], e[0]["case_number"]),
           (2014, "Gatirau Peter Munya vs Dickson Mwenda Kithinji & 3 Others", None))
    e = filing.find_eklr("Civil Appeal No. 5 of 2019. In Salesio M’tonga v M’ithara & 3 others [2015] eKLR the")
    expect("earlier case number ignored", (e[0]["cited_name"], e[0]["case_number"]),
           ("Salesio M’tonga v M’ithara & 3 others", None))
    e = filing.find_eklr("the case of John Muiruri v. Republic [1983] KLR 445 cited in Ben Maina Mwangi v. Republic "
                         "[2006] eKLR held")
    expect("name stops at an earlier citation", e[0]["cited_name"], "Ben Maina Mwangi v. Republic")
    e = filing.find_eklr("Okuta v AG (Petition No. 397 of 2016) [2017] eKLR and later in Njoroge [2017] eKLR")
    expect("next citation takes nothing from the previous one", (e[1]["cited_name"], e[1]["case_number"]), (None, None))
    e = filing.find_eklr("In Okuta v AG (Petition No. 397 of 2016) the court held so. See Mwangi [2019] eKLR.")
    expect("nothing crosses a sentence break", (e[0]["cited_name"], e[0]["case_number"]), (None, None))
    for text, want in (
            ("in Hassan Ali Joho & Another v. Suleiman Said Shahbal & 2 Others S.C. Petition No. 10 of 2013; [2014] eKLR",
             ("Hassan Ali Joho & Another v. Suleiman Said Shahbal & 2 Others", "10 of 2013")),
            ("the court in Mall Developers Limited v Postal Corporation of Kenya ML Misc. No. 26 of 2013 [2014] eKLR",
             ("Mall Developers Limited v Postal Corporation of Kenya", "26 of 2013")),
            ("costs in Jasbir Singh Rai & 3 others vs. Tarlochan Singh Rai & 4 others , Pet. 4 of 2012 [2014] eKLR",
             ("Jasbir Singh Rai & 3 others vs. Tarlochan Singh Rai & 4 others", "4 of 2012"))):
        e = filing.find_eklr(text)
        expect(f"court abbreviations before the number: {want[0][:20]}", (e[0]["cited_name"], e[0]["case_number"]), want)
    expect("no leading 'of' or list marker", [filing.find_cases(t)[0]["cited_name"] for t in
           ("in the case of Kenfit Limited v Consolata Fathers [2010] KECA 1 (KLR)",
            "(v) Peter Oduor Ngoge v. Francis Ole Kaparo [2012] KESC 7 (KLR)")],
           ["Kenfit Limited v Consolata Fathers", "Peter Oduor Ngoge v. Francis Ole Kaparo"])
    expect("case number normalised", filing.case_number("Petition E009 of 2023"), "E009 of 2023")
    expect("no case number", filing.case_number("Petition"), None)
    expect("name tokens keep initials", filing.name_tokens("JAC vs PW"), {"jac", "pw"})
    expect("name tokens drop case words", filing.name_tokens("Okuta v AG (Petition"), {"okuta"})
    expect("party part", filing.party_part(MURUATETU), "Muruatetu & another v Republic")
    expect("neutral form", filing.find_cases("[2017] KESC 2 (KLR)")[0]["form"], "neutral")


def fake_index(rows):
    """rows: (judgment_id, title, case_number, year) -> an index shaped like title_index()."""
    return filing.build_index([(None, jid, title, None, None, None, None, True, cn, y) for jid, title, cn, y in rows])


def test_ranking():
    idx = fake_index([("A", MURUATETU, "Petition 15 of 2015", 2017),
                      ("B", "Francis Mwangi v Republic", "Criminal Appeal 3 of 2016", 2017),
                      ("C", "Jacqueline Okuta & another v Attorney General & 2 others", "Petition 397 of 2016", 2017),
                      ("D", "John Ward v Standard Limited", "Civil Case 1062 of 2005", 2006),
                      ("E", "John Ward v Standard Limited", "Civil Case 1062 of 2005", 2006),
                      ("F", "Peter Mwangi v Republic", "Criminal Appeal 9 of 2019", 2019),
                      ("G", "James Mwangi v Republic", "Criminal Appeal 12 of 2019", 2019)]
                     + [(f"X{i}", f"Kamau{i} v Otieno{i}", None, 2010) for i in range(40)])
    def got(year, name, number=None):
        r = filing.decide(filing.rank_eklr(idx, year, name, number, min_shared=1.0, single_min_idf=1.0))
        return r["result"], r["basis"], [row[1] for row in r["rows"]]
    expect("first names our title drops", got(2017, "Francis Karioko Muruatetu & another v Republic"),
           ("found", "party names and year", ["A"]))
    expect("case number", got(2017, "Jacqueline Okuta v AG", "397 of 2016"), ("found", "case number", ["C"]))
    expect("two same-name cases", got(2006, "John Ward v Standard Limited"), ("possible_match", None, ["D", "E"]))
    expect("unknown parties", got(2017, "Nobody Atall v Someone Else"), ("not_in_collection", None, []))
    ng = fake_index([("KESC7", "Ngoge v Kaparo & 5 others", "Petition 2 of 2012", 2012),
                     ("KECA6", "Peter O. Ngoge v Francis Ole Kaparo & 3 others", "Civil Appeal 1 of 2011", 2012)]
                    + [(f"X{i}", f"Kamau{i} v Otieno{i}", None, 2010) for i in range(40)])
    r = filing.decide(filing.rank_eklr(ng, 2012, "Peter Oduor Ngoge v. Francis Ole Kaparo & Five Others", "2 of 2012",
                                       min_shared=1.0, single_min_idf=1.0))
    expect("the one case with the cited number wins a name tie", (r["result"], r["basis"], [x[1] for x in r["rows"]]),
           ("found", "case number", ["KESC7"]))
    expect("year we hold nothing for", got(1950, "Francis Mwangi v Republic"), ("not_in_collection", None, []))
    expect("common surname alone is never found", got(2019, "Mwangi v Republic")[0] != "found", True)
    short = fake_index([("N", "Njoroge & 17 others v Attorney General", None, 2015),
                        ("K", "Kenyatta University v Humphrey Mbuthi", None, 2012)]   # the words exist elsewhere
                       + [(f"X{i}", f"Kamau{i} v Otieno{i}", None, 2015) for i in range(40)])
    cite = "Republic v Kenyatta University Ex Parte Njoroge Humphrey Mbuthi"
    expect("short title covered by one name", filing.rank_eklr(short, 2015, cite, None, min_shared=1.0, min_cited=0.0)[0][0], 1.0)
    expect("min_cited: most of the filing's names must be in the title",
           filing.rank_eklr(short, 2015, cite, None, min_shared=1.0, min_cited=0.5), [])


def main():
    test_eklr()
    test_ranking()
    test_cases()
    test_quotes()
    test_text()
    test_text_fallbacks()
    test_limits()
    test_demos()
    for f in fails:
        print("FAIL", *f)
    print("FAILED" if fails else "all passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
