# Ground-truth audit: events.csv vs blind reading

I read all 13 judgments cited in events.csv in full, plus the 4 other judgments cited in negatives.csv, before I opened events.csv. My blind reading is in `audit_blind.csv` (keys B01–B16). Every quote below was copied from the parsed JSON `text` field. "No para" means the source has no paragraph numbers. In Okuta the bracketed numbers are footnote markers, not paragraph numbers.

Checker: `uv run python -m ground_truth.check` prints `OK: 15 events (0 verified), all quotes found in source`. I did not edit events.csv or negatives.csv.

## AGREE (same event_type, scope and operative quote)

| events.csv | blind | Note |
|---|---|---|
| E01 | B01 | Andare, KICA s.29, total. |
| E02 | B06 | Andama, PC s.66, total. |
| E03 | B05 | Alai, PC s.132, total. The order is total but the reasoning is qualified (see below). |
| E05 | B08 | EG, PC s.165, upheld, total. The two quotes overlap on the core sentence: "We find that the impugned sections are not unconstitutional." (para 406) |
| E06 | B02 | Okuta, PC s.194, partial. Identical order text. |
| E07 | B03 | Muruatetu, PC s.204, partial. E07 also quotes the avoidance-of-doubt sentence, which is better than my version. |
| E08 | B04 | Muruatetu Directions, s.204, interpreted, partial, affects E07. |
| E09 | B09 | Kilwake, SOA s.8, read_down, partial. |
| E13 | B11 | SC Mwangi reverses E11. |
| E14 | B13 | SC Manyeso reverses E12. |
| E15 | B14 | SC Ayako, partial reversal. |

Comments on the AGREE rows. None of these changes the verdict:

- **E03 (Alai)**: the order is total. Order 1 at para 62 reads "A declaration is hereby issued that Section 132 of the Penal Code is unconstitutional and invalid." The reasoning is narrower. Para 61 says the section is inconsistent "in so far as it suppresses freedom of expression, shifts burden to an accused, denies an accused the right to remain silent and derogates the right to fair hearing". Keep scope=total because it follows the order. Consider mentioning the reasoning in notes.
- **E06 (Okuta)**: the order is partial but the reasoning argues for total invalidity. Final declaration (i) (no para) reads "unconstitutional and invalid to the extent that it covers offences other than those contemplated under Article 33 (2) (a)- (d )". Yet the reasoning (no para) says "it is absolutely unnecessary to criminalize defamatory statements" and "criminal defamation is not reasonably justifiable in a democratic society". The row follows the order, which is correct. The status page should quote the order and nothing else.

## DISAGREE

### E04: EG, PC s.162, upheld. Scope: drafted `total`, mine `partial` (ambiguous)
- Drafted: scope=total, no scope_text.
- Mine (B07): scope=partial, scope_text="sections 162 (a) and (c)".
- Supporting text:
  - Para 1: "they both challenge the constitutionality of sections 162(a) (c) and 165 of the Penal Code."
  - Para 242(a): "Whether sections 162 (a) and (c) and 165 of the Penal Code are unconstitutional on grounds of vagueness and uncertainty."
  - The dispositive para 406 is wider: "the constitutional validity of sections 162 and 165 of the Penal Code is sustainable. We find that the impugned sections are not unconstitutional."
- Reason: nobody challenged s.162(b) (carnal knowledge of an animal), so the court did not adjudicate it. Ambiguous: the challenge was to (a) and (c), but the conclusion names "sections 162 and 165".

### E10: Muruatetu Directions, SOA s.8, interpreted. Drafted: an event. Mine: no event on s.8 (spurious)
- Drafted: interpreted, total, quoting para 11.
- Mine: no event on s.8. I recorded this content as a note on B04 (the s.204 event).
- Supporting text:
  - Para 10: "Reading this paragraph and the Judgment as a whole, at no point is reference made to any provision of any other statute."
  - Para 11: "this court’s decision in Muruatetu , did not invalidate mandatory sentences or minimum sentences in the Penal Code, the Sexual Offences Act or any other statute."
- Reason: the Directions describe how far E07 reaches. They never name or construe SOA s.8, so they are not an event on that section. See also SPURIOUS and FLAGS.

### E11: CA Mwangi 2022, SOA s.8, read_down. Event type agrees; operative quote and scope_text do not
- Drafted:
  - operative_quote: "For these reasons we allow this appeal and we set aside the 20- year sentence and substitute it with a 15-year sentence …" (para 35).
  - scope_text: "the court cannot be constrained by section 8 to impose the provided sentences if the circumstances do not demand it". This is from para 33, where the CA is **quoting Kilwake**.
- Mine (B10):
  - operative_quote (para 27): "we believe that the same, as applies to the unconstitutionality of mandatory sentences, can be applied mutatis mutandis to the mandatory nature of the sentences provided for in the SOA".
  - scope_text: "the mandatory nature of the sentences provided for in the SOA".
- Reasons:
  - Para 35 only changes one appellant's sentence and says nothing about s.8.
  - The drafted scope_text is Kilwake's holding (E09), not this court's own words.
  - Para 27 is where this court states what it holds about the statute. Para 32 adds: "the imposition of mandatory sentences by the Legislature conflicts with the principle of separation of powers".
- The event type is ambiguous (see FLAGS, E11).

### E12: CA Manyeso 2023, SOA s.8, declared_unconstitutional. Event type and scope agree; the quote fields are swapped
- Drafted:
  - operative_quote = the substitution order, para 27: "We accordingly set aside the sentence of life imprisonment imposed on the appellant and substitute therefor a sentence of 40 years in prison …"
  - scope_text = para 26: "having found the sentence of life imprisonment to be unconstitutional".
- Mine (B12):
  - operative_quote = para 26: "having found the sentence of life imprisonment to be unconstitutional, we have the discretion to interfere with the said sentence".
  - scope_text = para 21: "the imposition of a mandatory indeterminate life sentence".
- Reasons:
  - The para 27 order does not mention the statute.
  - The court's words about the provision are in para 26. They are the operative finding, not a "to the extent that" clause, so they belong in operative_quote.
- Also ambiguous: the finding sits in the reasoning, and the formal orders contain no declaration. The reasoning addresses "a mandatory indeterminate life sentence" (para 21) in general, not the wording of s.8(2). My confidence is 0.55.

## MISSED (events I found that events.csv lacks)

1. **B15: PC s.78 upheld, kesc/2019/93 (Khalid).**
   - Para 65(iii) frames the issue: "Whether sections 78(1), 78(2) and 94(1) of the Penal Code are unconstitutional for being vague, too broad and unclear therefore null and void."
   - Para 107 holds: "Consequently, we find the allegations of unconstitutionality of the impugned sections to be without merit."
   - This judgment is currently listed only as a negative, for KICA s.29.
   - Weakness: the merits reasoning is thin and mostly defers to the trial court. Para 105 says "a blanket condemnation of the statutory provisions is in our view overreaching". My confidence is 0.7.
2. **B16: PC s.94 upheld, kesc/2019/93.** Same paragraphs, s.94(1).
3. **Not found in stored files; noted for completeness.** These cannot be events because the judgments are not stored:
   - Kesc/2025/20 reverses CA *Ayako*, Criminal Appeal 22 of 2018 (8 December 2023). Para 18 reports that the CA "held that life imprisonment is cruel and degrading treatment since it is indefinite". E15 already notes this gap.
   - Kesc/2017/2 affirms CA *Mutiso* (para 52: "We are in agreement and affirm the Court of Appeal decision in Mutiso"). Mutiso had held (para 27, quoted) "section 204 shall, to the extent it provides that the death penalty is the only sentence in respect of the crime of murder is inconsistent with the letter and spirit of the Constitution". CA *Mwaura* later held Mutiso "per incuriam" (para 28). This is the multi-event history of s.204 before 2017. Neither judgment (keca/2010/487, keca/2013/541) is in `parsed/judgment`.
4. **Ambiguous, and I do not recommend adding it:** Directions kesc/2021/31 para 15 on ss.40(3), 296(2) and 297(2): "a challenge on the constitutional validity of the mandatory death penalty in such cases should be properly filed … Muruatetu as it now stands cannot directly be applicable to those cases." This is a statement about how far E07 reaches, not a ruling on those sections, for the same reason as E10.

## SPURIOUS

- **E10.** Kesc/2021/31 never construes SOA s.8.
  - Para 10: "at no point is reference made to any provision of any other statute".
  - Para 14: "Muruatetu cannot be the authority for stating that all provisions of the law prescribing mandatory or minimum sentences are inconsistent with the Constitution."
  - These statements limit precedent E07. They do not change the status of s.8.

No other row is unsupported. E11 and E12 are real events but quote the wrong passage (see DISAGREE).

## FLAGS (recommendations only; a human decides)

- **E04, "is scope required for non-invalidating events?"**
  - Recommendation: keep scope required, but define it for `upheld` as "which part of the section the court adjudicated". On that definition E04 would be partial, per para 242(a) "sections 162 (a) and (c)".
  - Reason: a status page that shows "upheld" for all of s.162 would suggest the court looked at s.162(b) (animals), which para 1 shows nobody challenged.
- **E09, "should E13 point affects_event at Kilwake?"**
  - Recommendation: no.
  - Reason: E13's orders set aside only the Mwangi judgment. Para 71(a): "setting aside the Judgment of the Court of Appeal in Nyeri in Criminal Appeal No 84 of 2015". Kilwake is not mentioned anywhere in kesc/2024/34, kesc/2025/16 or kesc/2025/20 (text search: 0 hits).
  - The undercutting comes through binding precedent. Para 53: "the Court of Appeal did offend the principle of stare decisis". Leave this to the status resolver as a precedent rule, or add a new event type such as `superseded_by_precedent`. Do not use `affects_event`, which should mean a direct appellate reversal.
- **E10, "is this an event on s.8?"**
  - Recommendation: drop E10. Put its para 11 quote in E08's notes, or in a context field on the s.8 status page.
  - Reason: para 10 says the judgment makes no "reference … to any provision of any other statute". Keeping E10 as `interpreted` would tell the extractor that a judgment which never names s.8 interpreted it.
- **E11, "read_down vs declared_unconstitutional".** The source is ambiguous in both directions:
  - For "declared": SC kesc/2024/34 para 64 says the CA "left its declaration of unconstitutionality ambiguous, vague and bereft of specificity".
  - For "read_down/no declaration": the next paragraph, 65, says "The Court of Appeal in the present appeal did not declare any particular provision of the Sexual Offences Act unconstitutional".
  - The CA text itself (paras 27, 32) contains no declaration and no section number in its holding.
  - Recommendation: keep read_down. Set confidence ≤0.6 and quote both SC passages in notes.
- **E12, "subsection-level provision_id?"**
  - The parsed Acts have eids only at section level (`sec_8`). There is no `sec_8__subsec_2`, so a subsection id would fail the checker.
  - Recommendation: keep `sec_8` for now. Add a nullable `subsection` column ("2") rather than putting it in scope_text, because scope_text must be the court's verbatim words.
  - The source supports 8(2). Para 5, ground (c): "the legal provision for mandatory life sentence under section 8(2) of the Sexual Offences Act denies the judicial officer …".
  - The same issue affects E09, E11 and E13 (8(3)), and E14 and E15 (8(2)).

## NEGATIVES (full text searched for orders)

| judgment | provision | Verdict | Evidence |
|---|---|---|---|
| kehc/2017/8027 | PC s.204 | Confirmed. No event. | Murder conviction only. Final para 15: "I accordingly find the accused guilty of murder … and convict him of murder contrary to Section 203 as read with Section 204 of the Penal Code". No sentence and no constitutional issue. |
| keca/2011/193 | PC s.204 | Confirmed. No event. | Appeal on identification only. Closing (no para): "The sentence meted out to the appellant is a lawful sentence. In the result, we dismiss the appellant’s appeal." This applies s.204 before Muruatetu; it does not rule on it. |
| kesc/2025/18 | PC s.204 | Confirmed. No event. | Para 23 only records the trial sentence: "sentenced to death as prescribed under section 204 of the Penal Code". Para 100: "it is not properly before us and as such the only proper recourse thereto is for the court to dismiss this appeal". Orders para 102 contain no statutory order. |
| kesc/2024/34 | PC s.204 | Confirmed. No event. | Para 51 only recites the 2017 orders. Para 58 says "this court solely considered the mandatory sentence of death under section 204". The orders (71) concern only CA Mwangi. The E13 event is correctly on SOA s.8. |
| kesc/2019/93 | KICA s.29 | Confirmed no event on s.29, but this judgment has two MISSED events (ss.78, 94). | Andare appears only in submissions (para 42) and the citation list. The editorial citation block reads "Kenya Information and Communication Act (cap 411A) - (Interpreted) section 29", but the judgment text never construes s.29. The "(Interpreted)" metadata tag is wrong and could mislead an extractor. |
| kehc/2017/6090 | PC s.194 | Confirmed. No event. | Okuta is only cited at para 58: "Mativo J, dealt with the issue of criminal defamation … under section 194". Orders (para 62) concern s.132 only. |

## Other things for the human

- **Okuta petition number.** The source header says "PETITION NO. 397 OF 2016", and E06's case_name already uses 2016. CLAUDE.md still says 397 of 2015.
- **Kilwake inconsistency** (not a ground-truth problem). Para 41 says "a sentence of imprisonment for 10 years would be adequate", but para 42 substitutes "a sentence of fifteen (15) years".
- **Kamande (kesc/2025/18).** A mandatory death sentence was imposed in May 2018, after Muruatetu. Para 23: "sentenced to death as prescribed under section 204 of the Penal Code". It is not an event, but it is useful for the pitch.
