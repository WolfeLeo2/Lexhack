// A line-for-line port of api/status_ke.py, so the timeline can replay a section's history one event at a time.
// logic.check.ts confirms it gives the same answer as the Python rules for every section in provisions.json.
import type { CourtEvent } from './types.ts'

const RANK: Record<string, number> = { 'Supreme Court': 3, 'Court of Appeal': 2, 'High Court': 1 }
const LIMITING = new Set(['declared_unconstitutional', 'read_down', 'severed', 'repealed_by_statute'])
const VALIDATING = new Set(['upheld', 'reversed_on_appeal'])
// Parliament's changes never displace, and are never displaced by, a court ruling.
const STATUTORY = new Set(['repealed_by_statute', 'amended_by_statute'])

export const direction = (e: CourtEvent) =>
  LIMITING.has(e.event_type) ? 'limits' : VALIDATING.has(e.event_type) ? 'validates' : null

// Which way an event pushes for displacement: an interpretation can carry a stance.
const pull = (e: CourtEvent) => (e.event_type === 'interpreted' && e.stance ? e.stance : direction(e))
// Rulings displace each other only on the same legal point; unlabelled events count as the same point.
const samePoint = (a: CourtEvent, b: CourtEvent) => !a.issue || !b.issue || a.issue === b.issue

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
    if (out.get(e.event_id)!.state !== 'in effect' || !direction(e) || STATUTORY.has(e.event_type)) return
    const later = events
      .slice(i + 1)
      .find(
        (l) =>
          !STATUTORY.has(l.event_type) &&
          pull(l) &&
          pull(l) !== direction(e) &&
          samePoint(e, l) &&
          (RANK[l.court ?? ''] ?? 0) >= (RANK[e.court ?? ''] ?? 0) &&
          l.effective_date !== e.effective_date,
      )
    if (later)
      Object.assign(out.get(e.event_id)!, { state: 'displaced by a later ruling', superseded_by: later.event_id })
  })
  const live = events.map((e) => out.get(e.event_id)!).filter((e) => e.state === 'in effect')
  let limits = live.filter((e) => direction(e) === 'limits')
  const court = events.filter((e) => !STATUTORY.has(e.event_type))
  const reversals = live.filter((e) => e.event_type === 'reversed_on_appeal')
  // An unlinked reversal is assumed to have undone a limit; one linked to an upheld/interpreted ruling did not.
  const reversedALimit = (e: CourtEvent) => {
    const t = e.affects_event_id != null ? byId.get(e.affects_event_id) : undefined
    return !t || direction(t) === 'limits'
  }
  let status: string
  if (live.some((e) => e.event_type === 'repealed_by_statute' && e.scope === 'total')) status = 'repealed'
  else if (limits.some((e) => e.event_type === 'declared_unconstitutional' && e.scope === 'total'))
    status = 'declared unconstitutional'
  else if ((limits = limits.filter((e) => !STATUTORY.has(e.event_type))).length) status = 'limited by a court'
  else if (reversals.length)
    status = reversals.some(reversedALimit)
      ? 'in force; earlier court limits were reversed'
      : "in force; a lower court's ruling on it was set aside on appeal"
  else if (live.some((e) => e.event_type === 'upheld')) status = 'in force; its validity has been tested in court'
  else if (court.length) status = 'in force; interpreted by a court'
  else status = 'in force; no recorded court rulings'
  const repeal = live.filter((e) => e.event_type === 'repealed_by_statute' && e.scope === 'total')
  const liveCourt = live.filter((e) => !STATUTORY.has(e.event_type))
  const summary = repeal.length ? repeal : limits.length ? limits : liveCourt.filter((e) => direction(e)).length ? liveCourt.filter((e) => direction(e)) : liveCourt
  if (!repeal.length) summary.push(...live.filter((e) => e.event_type === 'interpreted' && !summary.includes(e)))
  return { status, summary_events: summary, history: events.map((e) => out.get(e.event_id)!) }
}
