// The API contract (api/main.py's Pydantic models). Server components call the FastAPI service directly, so no CORS.
import 'server-only'

export const API_URL = process.env.API_URL ?? 'http://127.0.0.1:8000'

export interface Act {
  act_id: string
  title: string
  cap_number: string | null
  versions: string[]
}

export interface ProvisionRef {
  provision_id: string
  act_id: string
  act_title: string
  number: string | null
  heading: string | null
}

export interface Counts {
  cited_by: number // distinct judgments we hold that cite the section
  lead_count: number // unverified leads, hidden unless asked for
}

export interface ActSection extends ProvisionRef, Counts {
  status: string
}

export interface SearchHit extends ProvisionRef, Counts {
  status: string
  snippet: string
}

export interface CitingJudgment {
  judgment_id: string
  title: string
  court: string | null
  neutral_citation: string | null
  decision_date: string | null
  source_url: string | null
  mentions: number
  raw_text: string
  paragraph: string | null
}

export interface Stats {
  acts: number
  sections: number
  judgments: number
  cited_sections: number
  verified_events: number
  verified_sections: number
  person_events: number
  agent_events: number
  leads: number
  lead_sections: number
}

export interface CourtEvent {
  event_id: number
  event_type: string
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
  verified_by: string | null // 'human:…' or 'agent:…'
  state: 'in effect' | 'reversed on appeal' | 'displaced by a later ruling'
  superseded_by: number | null
}

export interface ProvisionStatus extends Counts {
  provision: ProvisionRef & { text: string; version_date: string; source_url: string | null }
  status: string
  summary_events: CourtEvent[]
  history: CourtEvent[]
  disclaimer: string
}

export class ApiDown extends Error {}

async function get<T>(path: string): Promise<T | null> {
  let res: Response
  try {
    res = await fetch(API_URL + path, { next: { revalidate: 300 } })
  } catch {
    throw new ApiDown(API_URL)
  }
  if (res.status === 404) return null
  if (!res.ok) throw new ApiDown(`${API_URL} answered ${res.status}`)
  return res.json()
}

export const getActs = () => get<Act[]>('/api/acts').then((a) => a ?? [])
export const getSections = (actId: string) => get<ActSection[]>(`/api/acts/${actId}/provisions`)
export const getProvision = (id: string, leads: boolean) =>
  get<ProvisionStatus>(`/api/provisions/${id}${leads ? '?include_unverified=true' : ''}`)
export const search = (q: string) =>
  get<SearchHit[]>(`/api/search?q=${encodeURIComponent(q)}&limit=20`).then((h) => h ?? [])
export const getCitations = (id: string, limit: number) =>
  get<{ total: number; judgments: CitingJudgment[] }>(`/api/provisions/${id}/citations?limit=${limit}`)
export const getStats = () => get<Stats>('/api/stats').then((s) => s!)

export interface JudgmentRef {
  judgment_id: string
  title: string
  court: string | null
  decision_date: string | null
  neutral_citation: string | null
  source_url: string | null
}

export interface CaseCheck {
  result: 'found' | 'name_mismatch' | 'possible_match' | 'not_in_collection'
  form: 'neutral' | 'eklr'
  match_basis: 'neutral citation' | 'case number' | 'party names and year' | 'quote' | null
  cited_name: string | null
  judgment: JudgmentRef | null
  candidates: JudgmentRef[] // possible_match: up to three, best first
}

export interface QuoteCheck {
  quote: string
  result: 'verbatim' | 'close' | 'not_found' | 'not_checked'
  similarity: number | null
  court_text: string | null // the judgment's words at the match; for not_found, the nearest passage if any
  paragraph: string | null
}

export interface SectionCheck {
  result: 'linked' | 'not_covered'
  act_ref: string | null
  provision: ProvisionRef | null
  status: string | null
  summary_events: CourtEvent[]
}

export interface Finding {
  kind: 'case' | 'section'
  raw_text: string
  char_start: number // code points into the checked text
  char_end: number
  case: CaseCheck | null
  quotes: QuoteCheck[]
  section: SectionCheck | null
}

export interface CheckReport {
  findings: Finding[]
  disclaimer: string
}
