import filings from '../data/filings.json'
import glossary from '../data/glossary.json'
import judgments from '../data/judgments.json'
import pipeline from '../data/pipeline.json'
import provisions from '../data/provisions.json'
import tables from '../data/tables.json'
import type { CourtEvent, Judgment, ProvisionStatus } from './types.ts'

export const PROVISIONS = provisions as unknown as ProvisionStatus[]
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

const ALL_EVENTS = new Map<number, CourtEvent>(PROVISIONS.flatMap((p) => p.history.map((e) => [e.event_id, e])))
export const eventById = (id: number | null) => (id == null ? undefined : ALL_EVENTS.get(id))
