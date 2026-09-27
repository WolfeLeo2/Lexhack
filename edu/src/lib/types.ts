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
  method?: 'manual' | 'extracted'
  check_verdict?: 'pass' | 'fail' | 'unsure' | null   // second-pass checker, extracted events only
  check_reason?: string | null
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

export interface StatusView {
  status: string
  summary_events: CourtEvent[]
  history: CourtEvent[]
}

export interface ProvisionStatus extends StatusView {
  provision: Provision
  disclaimer: string
  // teaching extras: the API's ?include_unverified=true answer, and what the second-pass checker hid
  with_leads: StatusView
  rejected: {
    event_type: string
    operative_quote: string
    effective_date: string
    court: string
    title: string
    source_url: string
    check_reason: string | null
  }[]
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
