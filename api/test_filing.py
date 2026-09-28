"""Checks for the filing checker (api/filing.py). Pure checks first, then the three demo filings end to end
against Neon and local data.

  uv run python -m api.test_filing
"""
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


def main():
    test_cases()
    test_quotes()
    test_text()
    for f in fails:
        print("FAIL", *f)
    print("FAILED" if fails else "all passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
