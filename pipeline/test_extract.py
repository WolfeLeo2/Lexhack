"""Offline self-check of the citation grammar. No database, no files.
    uv run python -m pipeline.test_extract
"""
from datetime import date

from .extract_citations import extract

# text -> [(section_ref, act_ref, act slug)] expected, in order
CASES = {
    "I declare that section 29 of the Kenya Information and Communication Act is unconstitutional":
        [("29", "Kenya Information and Communications Act", "cap-411a")],
    "sections 203 and 204 of the Penal Code":
        [("203", "Penal Code", "cap-63"), ("204", "Penal Code", "cap-63")],
    "Section 8(1) as read with section 8(2) of the Sexual Offences Act, 2006 provides":
        [("8(1)", "Sexual Offences Act", "cap-63a"), ("8(2)", "Sexual Offences Act", "cap-63a")],
    "Articles 10, 27 and 28 of the Constitution":
        [(n, "Constitution of Kenya", "constitution") for n in ("10", "27", "28")],
    "Article 50(2)(a) guarantees": [("50(2)(a)", "Constitution of Kenya", "constitution")],
    "section 84 of the former Constitution": [("84", "Constitution (repealed)", None)],
    "section 3 of the Constitution": [("3", "Constitution (repealed)", None)],
    "under section 107 of the Evidence Act, Cap 80": [("107", "Evidence Act", "cap-80")],
    "the Employment Act. Under section 45 of the Act the employer": [("45", "Employment Act", "cap-226")],
    "section 3 of the Act": [("3", "the Act", None)],
    "section 4 and 5 witnesses testified": [("4", None, None)],
    "sections 3 to 7 of the Civil Procedure Act": [(str(n), "Civil Procedure Act", "cap-21") for n in range(3, 8)],
    "section 45 of the Law of Succession Act": [("45", "Law of Succession Act", "cap-160")],
    "section 83 of the Elections Act": [("83", "Elections Act", "cap-7")],
    # whole-name only: these are different laws
    "section 23 of the National Assembly and Presidential Elections Act":
        [("23", "National Assembly and Presidential Elections Act", None)],
    "section 5 of the Indian Succession Act": [("5", "Indian Succession Act", None)],
    "section 8(1) of the SOA": [("8(1)", "Sexual Offences Act", "cap-63a")],
    "Section 204 of Cap 63": [("204", "Penal Code", "cap-63")],
    "sub-section 2 of section 8 of the Penal Code": [("8", "Penal Code", "cap-63")],
    "Mrs. 5 and s. 204 of the Penal Code": [("204", "Penal Code", "cap-63")],
    "section 159 (2) (d) of the Criminal Procedure Code": [("159(2)(d)", "Criminal Procedure Code", "cap-75")],
    "Article 6 of the International Covenant on Civil and Political Rights":
        [("6", "International Covenant on Civil and Political Rights", None)],
    "Elections Act (Cap 7), sections 34(6B) and 35;": [("34(6B)", "Elections Act", "cap-7"), ("35", "Elections Act", "cap-7")],
    "Constitution of Kenya, 2010 article 27; Penal Code (cap 63) section 204 - (Interpreted)":
        [("27", "Constitution of Kenya", "constitution"), ("204", "Penal Code", "cap-63")],
    "Statutes Penal Code (cap 63) section 194": [("194", "Penal Code", "cap-63")],
    "Constitution of Kenya articles 38(3)(c); 75; 87 — (Interpreted)":
        [(n, "Constitution of Kenya", "constitution") for n in ("38(3)(c)", "75", "87")],
    "Supreme Court Act, 2011 (Act No 7 of 2011) sections 24, 31 - (Interpreted)":
        [("24", "Supreme Court Act", None), ("31", "Supreme Court Act", None)],
    "Articles 25, 165 (6) & (7) and 169 (2) of the Constitution":
        [("25", "Constitution of Kenya", "constitution"), ("165(6)&(7)", "Constitution of Kenya", "constitution"),
         ("169(2)", "Constitution of Kenya", "constitution")],
    "pursuant to article 178(1) as read with section 21(1) of the Elections Act":
        [("178(1)", "Constitution of Kenya", "constitution"), ("21(1)", "Elections Act", "cap-7")],
    "In Article 768 of Section 9 of Halsbury's Laws of England": [("768", None, None), ("9", None, None)],
    "Ashwander v Tennessee Valley Authority, 297 U.S. 288, 347 (1936)": [],
}


def main():
    fails = 0
    for text, want in CASES.items():
        got = [(x["section_ref"], x["act_ref"], x["act_id"]) for x in extract(text, date(2020, 1, 1))]
        if got != want:
            fails += 1
            print(f"FAIL: {text!r}\n  want {want}\n  got  {got}")
    # before the 2010 Constitution, a bare "Article N" is not the Constitution of Kenya
    if [x["act_id"] for x in extract("Article 6 applies", date(2005, 1, 1))] != [None]:
        fails += 1
        print("FAIL: pre-2010 bare Article resolved to the 2010 Constitution")
    # paragraph numbers are taken only in sequence, so "section 204. The" is not paragraph 204
    x = next(extract("1. Facts. 2. The court considered section 204. The appeal fails", None))
    if x["paragraph"] != "2":
        fails += 1
        print(f"FAIL: paragraph {x['paragraph']!r}, want '2'")
    # "[n]" and "n)" numbering; a short "1) 2)" prayer list is not a paragraph scheme
    body = " The facts and the law are set out at length here. "   # real paragraphs are long
    for text, want in [("".join(f"[{i}]{body}" for i in range(1, 5)) + " [5] Section 204 of the Penal Code applies.", "5"),
                       ("35) Next. 36) We declare that section 204 of the Penal Code is void.", None),
                       ("".join(f"{i}){body}" for i in range(1, 5)) + " 5) Section 204 of the Penal Code applies.", "5"),
                       # a footnote list at the end is not a paragraph scheme
                       ("Section 204 of the Penal Code applies. " + "x " * 200 + "[1] Cap 63 [2] Ibid [3] Ibid [4] Supra [5] Ibid", None)]:
        got = next(extract(text, None))["paragraph"]
        if got != want:
            fails += 1
            print(f"FAIL: paragraph {got!r}, want {want!r} in {text!r}")
    print(f"{len(CASES) + 6 - fails}/{len(CASES) + 6} passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
