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


def main():
    test_cases()
    for f in fails:
        print("FAIL", *f)
    print("FAILED" if fails else "all passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
