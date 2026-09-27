# Auditor brief: does each section's status read correctly?

Hakiki shows, for each section of a Kenyan Act, a **status** worked out by rules from the section's court events,
plus the court's own words. Each event was already checked on its own. Your job is the whole picture: given the full
history, would a careful Kenyan lawyer agree with the status and with each event's state? You are checking the
*rules' output*, not re-reviewing each event from scratch.

## How the status is derived (api/status_ke.py)

- An event stops counting ("reversed on appeal") when a later `reversed_on_appeal` event names it directly.
- An event is "displaced by a later ruling" when a **later** event from a court of **equal or higher rank**
  (Supreme Court > Court of Appeal > High Court and courts of equal status) points the **other way**.
  Limiting events: `declared_unconstitutional`, `read_down`, `severed`. Validating: `upheld`, `reversed_on_appeal`.
- `interpreted` events never displace anything.
- Status from the events still in effect: any `declared_unconstitutional` with scope total → "declared
  unconstitutional"; any other limiting event → "limited by a court"; else any `upheld` → "in force; its validity
  has been tested in court"; else any `reversed_on_appeal` → "in force; earlier court limits were reversed"; else
  "in force; interpreted by a court".

Known weak spots to look for: a `reversed_on_appeal` event that is really an ordinary appeal and wrongly displaces
declarations; a High Court ruling that should not survive a later Court of Appeal / Supreme Court position on the
same point; a Supreme Court direction (e.g. *Muruatetu* 2021: the 2017 ruling applies to murder only) that should
narrow other courts' rulings but is only `interpreted`; the same ruling recorded twice.

## What you get

`batch_NN.json`: a list of sections. Each has the Act, section, heading, text, the derived `status`, the
`summary_event_ids` behind it, and the full `history` (each event with court, date, case, type, scope, quote,
paragraph, `state`, `superseded_by`, and `judgment_file`: the full judgment text on disk, if you need it).

Use web search (if available) for later appeals or higher-court rulings on the same point that are missing from the
history. new.kenyalaw.org refuses automated fetches; search results, news, law-firm notes and web.archive.org are fine.

## Answer per section

```json
{
  "provision_id": "...",
  "derived_status": "copied from the input",
  "verdict": "ok | wrong_status | wrong_state | unsure",
  "should_read": "if not ok: the status (from the list above) you think the rules should give, or a short phrase",
  "cause": "if not ok: event (an event is wrong: type, section, or not an event) | rule (the rules mis-combine correct events) | missing_event (a ruling we lack changes the answer)",
  "event_ids": [ids involved],
  "missing": "if cause is missing_event: case name, court, year, what it held, source URL",
  "reason": "two or three sentences, citing the events (and paragraphs) that decide it"
}
```

Mark `ok` when the status and states are defensible, even if you would phrase them differently. Be concrete when not.

## Output

Write a JSON array (one object per section, input order) to the findings path you are given. Rewrite the file after
EACH section with the Write tool (not Bash), so nothing is lost if you are interrupted; if it already exists, read
it and skip sections already answered. Do not open anything under `ground_truth/`. Do not modify other files.
When done, reply with one line per section: `provision_id verdict short reason`.
