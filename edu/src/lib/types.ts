// Mirrors the API contract in api/main.py (ProvisionStatus). The export script adds a few teaching-only extras.

export type EventType =
  | 'declared_unconstitutional'
  | 'read_down'
  | 'severed'
  | 'upheld'
  | 'interpreted'
  | 'reversed_on_appeal'
  | 'repealed_by_statute'
  | 'amended_by_statute'

export interface CourtEvent {
  event_id: number
  event_key?: string
  event_type: EventType
  scope: 'total' | 'partial'
  scope_text: string | null
  subsection: string | null
  operative_quote: string
  source_paragraph: string | null
  effective_date: string | null
  court: string | null
  title: string | null
  neutral_citation: string | null
  source_url: string | null
  verified: boolean
  state: 'in effect' | 'reversed on appeal' | 'displaced by a later ruling'
  superseded_by: number | null
  affects_event_id?: number | null
  notes?: string
}

export interface Provision {
  provision_id: string
  act_id: string
  act_title: string
  number: string
  heading: string
  text: string
  version_date: string
  source_url: string
  versions: { date: string; same_text: boolean }[]
  remarks: string[]
}

export interface ProvisionStatus {
  provision: Provision
  status: string
  summary_events: CourtEvent[]
  history: CourtEvent[]
  disclaimer: string
}

export interface Judgment {
  judgment_id: string
  title: string
  court: string
  neutral_citation: string | null
  alt_citation: string | null
  decision_date: string
  source_url: string
  passages: string[]
}
