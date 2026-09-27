import filings from '../content/filings.json'
import glossary from '../content/glossary.json'
import judgments from '../data/judgments.json'
import pipeline from '../content/pipeline.json'
import provisions from '../data/provisions.json'
import tables from '../content/tables.json'
import type { CourtEvent, Judgment, ProvisionStatus } from './types.ts'

// Older exports have no leads view; fall back to the verified view so the site still works.
export const LEADS_EXPORTED = provisions.some((p) => 'with_leads' in p)
export const PROVISIONS = (provisions as unknown as ProvisionStatus[]).map((p) => ({
  ...p,
  with_leads: p.with_leads ?? { status: p.status, summary_events: p.summary_events, history: p.history },
  rejected: p.rejected ?? [],
}))
export const JUDGMENTS = judgments as Judgment[]
export const FILINGS = filings
export const GLOSSARY = glossary as { term: string; group: string; def: string; eg?: string }[]
export const PIPELINE = pipeline as { title: string; state: 'done' | 'running' | 'next'; plain: string; in: string; out: string; files: string }[]
export const TABLES = tables as {
  id: string
  kind: 'table' | 'csv'
  rows: string
  group: string
  what: string
  why: string
  madeBy: string
  columns: [string, string, string][]
  links: string[]
}[]

const ALL_EVENTS = new Map<number, CourtEvent>(
  PROVISIONS.flatMap((p) => p.with_leads.history.map((e) => [e.event_id, e])),
)
export const eventById = (id: number | null) => (id == null ? undefined : ALL_EVENTS.get(id))
