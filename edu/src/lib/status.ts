// A line-for-line port of api/status_ke.py, so the timeline can replay a section's history one event at a time.
// logic.check.ts confirms it gives the same answer as the Python rules for every section in provisions.json.
import type { CourtEvent } from './types.ts'

const RANK: Record<string, number> = { 'Supreme Court': 3, 'Court of Appeal': 2, 'High Court': 1 }
const LIMITING = new Set(['declared_unconstitutional', 'read_down', 'severed', 'repealed_by_statute'])
const VALIDATING = new Set(['upheld', 'reversed_on_appeal'])

export const direction = (e: CourtEvent) =>
  LIMITING.has(e.event_type) ? 'limits' : VALIDATING.has(e.event_type) ? 'validates' : null

export function resolve(input: CourtEvent[]) {
  const events = [...input].sort(
    (a, b) => (a.effective_date ?? '').localeCompare(b.effective_date ?? '') || a.event_id - b.event_id,
  )
  const byId = new Map(events.map((e) => [e.event_id, e]))
  const out = new Map<number, CourtEvent>(
    events.map((e) => [e.event_id, { ...e, state: 'in effect', superseded_by: null }]),
  )
  for (const e of events) {
    // 1. direct reversals
    const target = e.affects_event_id != null ? byId.get(e.affects_event_id) : undefined
    if (target && e.event_type === 'reversed_on_appeal')
      Object.assign(out.get(target.event_id)!, { state: 'reversed on appeal', superseded_by: e.event_id })
  }
  events.forEach((e, i) => {
    // 2. precedent: a later, equal-or-higher court pointing the other way
    if (out.get(e.event_id)!.state !== 'in effect' || !direction(e)) return
    const later = events
      .slice(i + 1)
      .find(
        (l) =>
          direction(l) &&
          direction(l) !== direction(e) &&
          (RANK[l.court ?? ''] ?? 0) >= (RANK[e.court ?? ''] ?? 0) &&
          l.effective_date !== e.effective_date,
      )
    if (later)
      Object.assign(out.get(e.event_id)!, { state: 'displaced by a later ruling', superseded_by: later.event_id })
  })
  const live = events.map((e) => out.get(e.event_id)!).filter((e) => e.state === 'in effect')
  const limits = live.filter((e) => direction(e) === 'limits')
  let status: string
  if (limits.some((e) => e.event_type === 'repealed_by_statute')) status = 'repealed'
  else if (limits.some((e) => e.event_type === 'declared_unconstitutional' && e.scope === 'total'))
    status = 'declared unconstitutional'
  else if (limits.length) status = 'limited by a court'
  else if (live.some((e) => e.event_type === 'upheld')) status = 'in force; its validity has been tested in court'
  else if (live.some((e) => e.event_type === 'reversed_on_appeal')) status = 'in force; earlier court limits were reversed'
  else if (events.length) status = 'in force; interpreted by a court'
  else status = 'in force; no recorded court rulings'
  const summary = limits.length ? limits : live.filter((e) => direction(e)).length ? live.filter((e) => direction(e)) : live
  summary.push(...live.filter((e) => e.event_type === 'interpreted' && !summary.includes(e)))
  return { status, summary_events: summary, history: events.map((e) => out.get(e.event_id)!) }
}
