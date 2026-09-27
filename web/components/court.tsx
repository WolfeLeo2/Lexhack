import { ExternalLink } from 'lucide-react'
import type { CourtEvent } from '@/lib/api'
import { EVENT_LABEL, cap, fmtDate, shortCase } from '@/lib/format'
import { cleanUrl, locator, tidySpaces } from '@/lib/text'

/** The court's exact words, with the limiting clause marked where it appears inside the quote. */
export function CourtWords({ quote: raw, mark: rawMark, className = '' }: { quote: string; mark?: string | null; className?: string }) {
  // spaces only: the words themselves are the court's, verbatim
  const quote = tidySpaces(raw)
  const mark = rawMark && tidySpaces(rawMark)
  const i = mark ? quote.toLowerCase().indexOf(mark.toLowerCase()) : -1
  return (
    <blockquote className={`court ${className}`}>
      “
      {i < 0 || !mark ? (
        <span className="hl">{quote}</span>
      ) : (
        <>
          {quote.slice(0, i)}
          <span className="hl">{quote.slice(i, i + mark.length)}</span>
          {quote.slice(i + mark.length)}
        </>
      )}
      ”
    </blockquote>
  )
}

export function StateTag({ state }: { state: CourtEvent['state'] }) {
  if (state === 'in effect') return <span className="text-sm text-gazette">Still counts</span>
  return <span className="text-sm text-ink-2 line-through decoration-seal/60">{cap(state)}</span>
}

/** Who checked a ruling, from citation_events.verified_by. Unchecked rulings get UnverifiedTag instead. */
export function CheckedTag({ by }: { by: string | null }) {
  const agent = by?.startsWith('agent:')
  return (
    <span
      className="rounded-sm border border-rule px-1.5 py-px text-xs text-ink-2"
      title={agent ? 'Read against the judgment by an AI reviewer (see About)' : 'Read against the judgment by a person'}
    >
      {agent ? 'Checked by an AI reviewer' : 'Checked by a person'}
    </span>
  )
}

export function UnverifiedTag() {
  return (
    <span
      className="rounded-sm border border-dashed border-ink-2/60 px-1.5 py-px text-xs text-ink-2"
      title="Found by the pipeline, not yet checked by a person"
    >
      Unverified lead
    </span>
  )
}

/** Who said it, when, and where to read it. */
export function Attribution({ e }: { e: CourtEvent }) {
  const where = locator(e.source_paragraph)
  const url = cleanUrl(e.source_url)
  return (
    <p className="text-[0.95rem] text-ink-2">
      <span className="text-ink">{shortCase(e.title)}</span>
      {e.neutral_citation && <> {e.neutral_citation}</>}, {e.court ?? 'court unknown'}, {fmtDate(e.effective_date)}
      {where && <>, {where}</>}.{' '}
      {url && (
        <a href={url} className="link inline-flex items-center gap-1 whitespace-nowrap" target="_blank" rel="noreferrer">
          Read the judgment
          <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          <span className="sr-only">(opens Kenya Law in a new tab)</span>
        </a>
      )}
    </p>
  )
}

/** One entry in the section's history. `id` lets the lineage chart scroll to it. */
export function EventEntry({ e, all }: { e: CourtEvent; all: CourtEvent[] }) {
  const by = e.superseded_by == null ? undefined : all.find((x) => x.event_id === e.superseded_by)
  const live = e.state === 'in effect'
  return (
    <li
      id={`e-${e.event_id}`}
      className={`scroll-mt-24 border-l-2 py-1 pl-5 target:bg-mark/25 ${
        e.verified ? (live ? 'border-seal' : 'border-rule') : 'border-dashed border-ink-2/50'
      }`}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="statute text-xl font-medium">
          {EVENT_LABEL[e.event_type] ?? e.event_type}
          {e.subsection && <span className="text-ink-2"> (s.{e.subsection})</span>}
          {e.scope === 'partial' && e.event_type !== 'interpreted' && <span className="text-ink-2"> in part</span>}
        </h3>
        <StateTag state={e.state} />
        {e.verified ? <CheckedTag by={e.verified_by} /> : <UnverifiedTag />}
      </div>
      <CourtWords quote={e.operative_quote} mark={e.scope_text} className={`mt-3 text-lg ${live ? '' : 'opacity-75'}`} />
      <div className="mt-3">
        <Attribution e={e} />
      </div>
      {by && (
        <p className="mt-2 text-sm text-ink-2">
          {e.state === 'reversed on appeal' ? 'Reversed by ' : 'Displaced by '}
          <a href={`#e-${by.event_id}`} className="link">
            {shortCase(by.title)} ({by.court}, {by.effective_date?.slice(0, 4)})
          </a>
        </p>
      )}
    </li>
  )
}
