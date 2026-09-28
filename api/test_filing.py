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
        clean = filing.check(conn, (DEMO / "clean.txt").read_text(encoding="utf-8"))
        bad = filing.check(conn, (DEMO / "hallucinated.txt").read_text(encoding="utf-8"))
        stale = filing.check(conn, (DEMO / "stale_law.txt").read_text(encoding="utf-8"))
    expect("clean", summary(clean), [
        ("section", "section 107 of the Evidence Act", "linked", "in force; no recorded court rulings"),
        ("case", "[2021] KESC 31 (KLR)", "found", ["verbatim"]),
        ("section", "sections 203 and 204 of the Penal Code", "linked", "in force; no recorded court rulings"),
        ("section", "sections 203 and 204 of the Penal Code", "linked", "limited by a court"),
    ])
    quote = next(f for f in clean["findings"] if f["kind"] == "case")["quotes"][0]
    expect("clean quote paragraph", quote["paragraph"], "18")
    expect("hallucinated", [s[:4] for s in summary(bad) if s[0] == "case"], [
        ("case", "[2017] KESC 2 (KLR)", "name_mismatch", []),
        ("case", "[2017] KEHC 8382 (KLR)", "found", ["not_found"]),
        ("case", "[2017] KESC 2 (KLR)", "found", ["close"]),
        ("case", "[2019] KECA 99999 (KLR)", "not_in_collection", []),
    ])
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


def main():
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
