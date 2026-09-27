# Reviewer brief: checking extracted court events

You are reviewing claims made by an automated pipeline about Kenyan court judgments, for **Hakiki**, a citator that
records what courts *did* to statute sections. Each claim says: *this judgment did [event_type] to [section]*, and
quotes the court's words. Your verdict decides whether the claim is shown to lawyers as a checked ruling. Be strict:
a wrong accept misleads a lawyer; a wrong reject only leaves a lead unchecked.

## What you get per case (a JSON object in your batch file)

- `title`, `court`, `judgment_id`, `judgment_url`, `effective_date`
- `section`: the claimed Act and section, and `section_text`: that section's statutory text
- `event_type`, `scope`, `scope_text`, `subsection`: what the pipeline claims the court did
- `operative_quote`: the words the pipeline says are the court's; `quote_found` says whether code found them
  verbatim in the judgment (it does not say they are the *operative* words)
- `judgment_text`: path to the full judgment text on disk. **Read it** (search it for the quote, then read around
  it and read the final orders at the end). Never decide from the quote alone.

Do not open anything under `ground_truth/` in the repo, or any `verdicts/` file other than your own output: this is
a blind review.

## The event types

| type | the court… |
|---|---|
| `declared_unconstitutional` | declares the section, or part of it, inconsistent with the Constitution and invalid |
| `read_down` | keeps the words but gives them a narrower meaning to save them (e.g. minimum sentences "must be interpreted so as not to take away the discretion of the court") |
| `severed` | cuts specific words out and keeps the rest |
| `upheld` | was asked whether the section is constitutional and held that it is |
| `interpreted` | settles what the section means (or what an earlier ruling on it means), by its own reasoning, without changing validity |
| `reversed_on_appeal` | as an appellate court, sets aside an earlier court's ruling **on this section's validity or meaning** |

## It is NOT an event when the court

- applies, follows or restates another court's ruling ("guided by…", "as held in Muruatetu…", "we are bound by…"),
  including re-sentencing in light of an earlier decision;
- convicts or sentences under the section, or recites a party's argument or a lower court's finding;
- makes an ordinary appeal order (appeal allowed, sentence set aside, conviction quashed) that does not decide the
  section's validity or meaning. An ordinary appeal is not `reversed_on_appeal`;
- says something about a different Act or section ("the Act" can mean another statute with the same numbering), a
  schedule, or rules made under the Act;
- mentions the section only as the procedural basis for the application.

## Answer fields (one object per case)

```json
{
  "case_id": "copied from the case",
  "is_event": "yes | no | unsure",
  "correct_type": "the type you would give it, or none",
  "section_right": "yes | no | unsure",
  "scope_right": "yes | no | unsure",
  "quote_operative": "yes | no: are the quoted words the court's own operative holding (not a summary, not counsel)?",
  "better_quote": "if quote_operative is no and is_event is yes: the exact operative words from the judgment, copied verbatim, else empty",
  "paragraph": "the paragraph number of the operative words, if the judgment numbers them, else empty",
  "later_history": "anything you found about an appeal or later ruling on this point (case name, court, year, what happened, URL), else empty",
  "decision": "accept | reject | unsure",
  "reason": "one or two sentences, citing the paragraph"
}
```

`decision` is **accept** only when all of these hold: `is_event` yes, `correct_type` equals the claimed type,
`section_right` yes. Otherwise **reject**, or **unsure** if you honestly cannot tell from the text.

## Web search (for `later_history`)

Only when the event is a ruling that limits, upholds or reads a section, search briefly for a later appeal or a
higher court's ruling on the same point (e.g. `"<case name>" appeal Court of Appeal`, `"section 8" "Sexual Offences
Act" Supreme Court 2024`). new.kenyalaw.org will refuse automated fetches; search results, news reports, law firm
notes and the Internet Archive (web.archive.org) are fine. Record what you find with its source. It does **not**
change your decision on the claim itself: a later reversal is a separate event.

## Output

Write a JSON array of answer objects, one per case in your batch, in the same order, to the verdicts path you were
given. Write it once at the end (valid JSON, UTF-8). Then reply with one line per case: `case_id decision reason`.
