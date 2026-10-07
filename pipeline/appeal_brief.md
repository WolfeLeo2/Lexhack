# Later-appeal check: reviewer brief

Hakiki records what Kenyan courts did to statute sections. Each case in your batch is a judgment whose ruling on a
section we treat as current. Your job: find out whether that judgment was **later appealed**, and if so, what the
appellate court did. A reversed ruling shown as current is the worst error a citator can make.

## For each case

1. Search the web for the case by name, case number, neutral citation and year, plus words like "appeal",
   "Court of Appeal", "Supreme Court", "set aside", "overturned", "upheld". Kenya Law (kenyalaw.org), news reports,
   law-firm notes and later judgments that mention the case are all useful. Two or three searches are usually enough;
   stop when you have an answer.
2. Only an appeal **in the same case** counts (the same parties, from this judgment). A later, different case that
   disagrees with this one is NOT an appeal; mention it in `note` if you see it, but `later_history` stays as it is.
3. Do not guess. If nothing shows an appeal, the answer is `none_found`, not `appeal_pending`.

## Answer (one object per case, JSON)

```json
{"judgment_id": "<copied from the case>",
 "later_history": "reversed | partly_reversed | upheld | appeal_pending | appeal_withdrawn | none_found",
 "appellate_case": "<name of the appellate case, or empty>",
 "appellate_citation": "<its neutral citation if shown, e.g. [2023] KECA 123 (KLR), else empty>",
 "appellate_court": "<Court of Appeal | Supreme Court | empty>",
 "appellate_date": "<YYYY-MM-DD or YYYY, or empty>",
 "outcome": "<one or two sentences: what the appellate court did to THIS ruling on the section, in plain words>",
 "source_url": "<the page that shows it>",
 "confidence": "high | medium | low",
 "note": "<anything else useful, e.g. a later case that disagreed>"}
```

- `reversed`: the appellate court set aside the ruling on the section. `partly_reversed`: some of it.
- `upheld`: the appeal was dismissed, or the ruling on the section was affirmed.
- `appeal_pending`: a source says an appeal was filed and no outcome is shown.
- `confidence`: high when a source names the appeal and its outcome; low when you are inferring.
