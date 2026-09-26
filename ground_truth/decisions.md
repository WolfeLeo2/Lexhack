# Ground truth: final verification decisions (agent:opus, 2026-09-23)

Third independent check, made after the draft (events.csv) and the blind audit (audit.md). I read every judgment in the parsed JSON `text` field, looking around each quote and not only at the quote. Paragraph numbers are the source's own. Result: 17 of 18 rows are `verified=true`. E11 stays `false` (reason below). `uv run python -m ground_truth.check` prints `OK: 18 events (17 verified)`.

## Flag decisions

**E04, scope for non-invalidating events.** Decision: `scope` is required for every event type, and it always answers one question: how much of *this* section does the event bear on?
- declared_unconstitutional / read_down / severed: the part limited. `scope_text` is the court's "to the extent that" or reading-down clause.
- upheld / interpreted: the part the court adjudicated or construed. `scope_text` is the court's words naming that part.
- reversed_on_appeal: how much of the earlier judgment was set aside.

E04 stays `partial` / "sections 162 (a) and (c)". Para 1 says the petitions "challenge the constitutionality of sections 162(a) (c) and 165", and para 242(a) frames the issue as "Whether sections 162 (a) and (c) and 165 of the Penal Code are unconstitutional". Para 162(b) (animals) was never before the court.

Applied to the other rows:
- E05 (s.165, challenged whole) stays `total`.
- E16's scope_text becomes "sections 78(1), 78(2)" and E17's becomes "94(1) of the Penal Code". Both come from para 65(iii): "Whether sections 78(1), 78(2) and 94(1) of the Penal Code are unconstitutional". The old scope_text on both rows named the other section too.
- E08 changes from partial to `total` (see Corrections).

**E09, affects_event on Kilwake.** Decision: no row points at E09. `affects_event` means a later decision that acts directly on that judgment: an appeal from it, or the same court's further directions in the same proceedings (this is why E08→E07 stays). It never means precedent. "Kilwake" appears 0 times in kesc/2024/34, kesc/2025/16 and kesc/2025/20. SC Mwangi's orders act only on CA Mwangi. Para 71(a): "setting aside the Judgment of the Court of Appeal in Nyeri in Criminal Appeal No 84 of 2015". Kilwake is displaced only by precedent: Directions para 11, "did not invalidate mandatory sentences or minimum sentences in the Penal Code, the Sexual Offences Act or any other statute". I fixed E09's notes, which cited the dropped E10.

**E11, read_down vs declared_unconstitutional.** Decision: keep `read_down`, confidence 0.6. The CA made no declaration and named no section. Para 27 only says Muruatetu "can be applied mutatis mutandis to the mandatory nature of the sentences provided for in the SOA". The court's own framing keeps the sentences in force but makes them discretionary. Para 29 says "some accused persons are obviously deserving of no less than the minimum sentences as provided for in the SOA", and para 30 says "this is the leeway we are asserting that ought to be at the disposal of courts". Para 33 adopts Kilwake's read-down holding as "well articulated". SC kesc/2024/34 para 65 agrees: "did not declare any particular provision of the Sexual Offences Act unconstitutional". **Left verified=false**: the same SC judgment also calls it a "declaration of unconstitutionality" (para 64, and para 68 "in the manner the Court of Appeal did"). The appellate court describes it both ways, so a human should confirm the type. Every other field (quote, para 27, date, provision) checks out.

**E12, subsection level.** Decision: provision_id stays at `sec_8`, and a new `subsection` column records the sub-provision when the court's holding or order is limited to one. E12 gets `8(2)`. Para 5(c) is the ground of appeal: "the legal provision for mandatory life sentence under section 8(2) of the Sexual Offences Act". Para 26 is the finding: "having found the sentence of life imprisonment to be unconstitutional". The column is filled as follows:
- `8(2)`: E12, E14, E15, E19. These are all about life imprisonment, which s.8 provides only in 8(2). Ayako para 3: "life imprisonment, being the minimum statutorily imposed sentence under section 8(2)".
- `162(a),(c)`: E04.
- `78(1),(2)`: E16.
- `94(1)`: E17.

It is left empty for E09, E11 and E13, even though those convictions were under 8(3). Their holdings are not limited to a subsection. Kilwake para 39 covers "the provisions of section 8", and CA Mwangi para 27 covers "the sentences provided for in the SOA".

**E18, Mwaura.** Flag left in place. This is an open data gap, not an error. Muruatetu para 28 records that CA Mwaura (keca/2013/541) held "the decision in Godfrey Mutiso v R to be per incuriam in so far as it purports to grant discretion in sentencing with regard to capital offences". Mwaura is not in `parsed/judgment`, so no event can be added. Until a copy is saved by hand, the s.204 history reads Mutiso (2010) → Muruatetu (2017) with the 2013 reversal missing. E18 itself is verified.

## Corrections made to events.csv

- **E08**: scope changed from partial to `total`, and scope_text cleared. Para 18(i) reads "apply only in respect to sentences of murder under sections 203 and 204". That limits E07's reach across *other* provisions (para 15: ss.40(3), 296(2), 297(2)). It is not a part of s.204, which deals only with murder. The words stay in operative_quote.
- **E14**: operative_quote changed from 72(b) to para 70, "…the Judgement of the Court of Appeal delivered on July 7, 2023 is one for setting aside." Order 72(b), "The life imprisonment sentence … is hereby reinstated", only acts on the respondent's sentence. Para 70 holds the reversal itself. source_paragraph is now "70; orders 72(a)-(b)".
- **E16 / E17**: scope_text narrowed to each row's own section (see above).
- **E18**: source_paragraph changed from "36 (… patchy; verify)" to `36`. Numbering runs 1)–38) in order. The only glitch is a stray "9)" list marker between 20) and 21). Para 36 contains "We declare that section 204 shall, to the extent that it provides that the death penalty is the only sentence…".
- **E19**: event_type changed from interpreted to `read_down`, confidence 0.7. The CA first finds (para 11) "an indeterminate life sentence falls afoul the provisions of articles 27 and 28 of our Constitution". It notes (para 13) that life imprisonment "can be saved … where life imprisonment has been limited to a number of years". It then construes it that way (para 26): "life imprisonment translates to thirty years’ imprisonment". That is a constitutionally driven narrowing construction, which is a read-down and not a neutral interpretation. The operative quote (para 26) was already correct. source_paragraph is now "26; constitutional finding 11".
- **E09**: notes only (stale E10 reference).

## Rows checked and confirmed without change

- **E01**: para numbers absent; order (a) "I declare that section 29 … is unconstitutional". Total.
- **E02**: para 68(a).
- **E03**: para 62 order 1. Para 61's "in so far as" reasoning is noted in audit.md. The order is total.
- **E05**: para 406.
- **E06**: final declaration (i). Petition 397 of **2016** per the header.
- **E07**: para 112(a); scope_text from para 69.
- **E13**: para 71(a). The appeal is from CA 84 of 2015 = E11.
- **E15**: para 56, affects E19. The header reads "appeal from the Judgment of the Court of Appeal at Kisumu … dated 8th December 2023", which matches E19.
- **E16, E17**: para 107. Confidence 0.7 kept, because paras 105-106 mostly leave proof to the trial court. But the holding is explicit: "we find the allegations of unconstitutionality of the impugned sections to be without merit".

All effective_date values match the decision date in the judgment title. No missed events were found for the recorded sections.

## SCHEMA CHANGES PROPOSED

1. **`subsection TEXT NULL`** on `citation_events`, e.g. '8(2)' or '162(a),(c)'. Filled only when the holding or order is limited to part of the section. provision_id stays at section level because the parsed Acts have no subsection eids.
2. **Define `scope` per event family** in the schema comment, as set out under E04 above.
3. **Define `affects_event_id`**: a direct act on that judgment (an appeal from it, or further directions in the same proceedings). Never precedent. If precedent-based displacement (E09) has to be modelled, it should be a status-resolver rule or a new event type such as `superseded_by_precedent`. I did not add one to the CSV.
4. `verified_by TEXT` on `citation_events`, to record who verified a row.

## E20 Mwaura (verified 2026-09-25)

Source: `parsed/judgment/akn_ke_judgment_keca_2013_541_eng@2013-10-18.json` (hand-saved 2026-09-24). I read all 85 paragraphs. Numbering is clean and sequential. The only holdings on s.204 are in paras 57-79. The final order is para 85: "these appeals are devoid of merit, and it fails in its entirety". There is no separate order on s.204.

**event_type: `upheld`, not `interpreted`. Confidence 0.7.** Para 35 frames the last issue as "the constitutionality of the sentence imposed on the appellants". The appellants relied on Mutiso's s.204 declaration (para 67: "to support their submission that the death penalty is unconstitutional"). Para 68 quotes that declaration in full. The court rejected the challenge on constitutional grounds:
- para 57: "the death penalty is, contrary to the appellants’ arguments, grounded in the Constitution"
- para 64: "We do not think that the death sentence falls within these definitions" (cruel, inhuman and degrading)
- para 78: "to say that there are other alternative sentences to the mandatory imposition or application of the death sentence is a pedantic and preposterous interpretation"
- para 79: it held Mutiso "per incuriam in so far as it purports to grant discretion in sentencing" and ruled that murder under "section 203 as read with 204 … carry the mandatory sentence of death"

That is a constitutional challenge rejected, which matches the README 5.4 definition of `upheld`. `interpreted` is defined as "without changing its validity". Mwaura did change the validity picture: it undid E18's declaration. So under `interpreted`, a resolver would wrongly leave E18 standing. The Supreme Court reads Mwaura the same way. Muruatetu para 12 says the petitioners urged that the CA "grossly erred by failing to find that the mandatory nature of the death sentence set out in section 204 of the Penal Code is unconstitutional". Para 28 says "the Court of Appeal changed it holding that by the use of the word ‘shall’ section 204 … was couched in mandatory terms". Confidence is 0.7, not higher, because the appellants were convicted under s.296(2), not s.204 (paras 1, 7). The s.204 holding is reached only through the challenge to Mutiso.

**scope: `total`, scope_text empty.** s.204 has a single operative clause, the death sentence for murder, and para 79 rules on all of it. Subsection empty.

**affects_event: empty.** Mwaura is Criminal Appeal 5 of 2008, "an appeal from the judgment of the High Court … In H.C.Cr. A Nos. 129, 133 & 134 of 2006". Mutiso (E18) is Criminal Appeal 17 of 2008. Mwaura is not an appeal from Mutiso and gives no directions in it, so this is precedent (per E09 rule above). Likewise, E07 must not point at E20. Muruatetu is SC Petitions 15 & 16 of 2015, a different case, even though para 12 asks the court "to overturn" Mwaura.

**Other fields.** operative_quote is para 79 verbatim (check passes). effective_date 2013-10-18 matches the title. source_paragraph changed from `79` to "79; constitutional findings 57, 64; appeal dismissed 85". Notes claims checked: Muruatetu para 52 "We are in agreement and affirm the Court of Appeal decision in Mutiso". Para 28 records Mwaura's per incuriam holding verbatim. Notes extended with the s.296(2) point and the case numbers. Flag cleared, verified=true.
