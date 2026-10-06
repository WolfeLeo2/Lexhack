import { caseName, tidySpaces } from './text'

export const EVENT_LABEL: Record<string, string> = {
  declared_unconstitutional: 'Declared unconstitutional',
  read_down: 'Read down',
  severed: 'Severed',
  upheld: 'Upheld',
  interpreted: 'Interpreted',
  reversed_on_appeal: 'Reversed on appeal',
  repealed_by_statute: 'Repealed by Parliament',
  amended_by_statute: 'Amended by Parliament',
}

export const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

export const year = (d: string | null) => (d ?? '').slice(0, 4)

export function fmtDate(d: string | null) {
  if (!d) return 'Date unknown'
  return new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

/** 'Muruatetu & another v Republic; Katiba … (Petition 15 of 2015)' -> 'Muruatetu & another v Republic' */
export const shortCase = caseName

/** Court rank for the lineage chart; mirrors api/status_ke.py (anything else sits with the High Court). */
export function rank(court: string | null) {
  if (court === 'Supreme Court') return 3
  if (court === 'Court of Appeal') return 2
  return 1
}

/** A court has acted unless the status says no rulings are recorded. */
export const courtActed = (status: string) => !status.includes('no recorded') && status !== 'repealed'

/** Parliament's amendments and repeals (from Kenya Law's notes), as opposed to court rulings. */
export const isStatutory = (e: { event_type: string }) => e.event_type.endsWith('_by_statute')

export const sectionHref = (id: string) => `/p/${id}`
export const actHref = (id: string) => `/acts/${id}`

/** 'ke/act/cap-63' -> 'Cap. 63' */
export const capLabel = (a: { cap_number: string | null; title: string }) =>
  a.cap_number ? `Cap. ${a.cap_number}` : a.title.includes('Constitution') ? '2010' : ''

/** The stored text repeats the number and heading ('204. Punishment of murder Any person…'); pages show them above. */
export function stripHead(text: string, number: string | null, heading: string | null) {
  const t = tidySpaces(text)
  const head = tidySpaces(`${number ?? ''}. ${heading ?? ''}`)
  return t.startsWith(head) ? t.slice(head.length).trim() : t
}

export const plural = (n: number, one: string, many = one + 's') => `${n.toLocaleString('en-GB')} ${n === 1 ? one : many}`
