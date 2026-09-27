import { Braces, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { PROVISIONS, eventById } from '../lib/data.ts'
import { play } from '../lib/feedback.ts'
import type { ProvisionStatus } from '../lib/types.ts'
import { CourtWords, EVENT_LABEL, StateTag, StatusStamp, fmtDate, shortCase, year } from './ui.tsx'

// Everyday words people search with; the statute's own words are often different ("libel", "defilement").
const ALIASES: Record<string, string> = {
  '194': 'defamation libel posts reputation',
  '204': 'death penalty sentence killing',
  '203': 'murder killing',
  '8': 'defilement child minor minimum life sentence sex',
  '11': 'indecent act child',
  '29': 'phone internet message telecom offensive',
  '66': 'fake news false rumour alarming',
  '132': 'undermining public officer insult',
  '162': 'unnatural offences',
  '165': 'indecent practices',
  '78': 'unlawful assembly riot protest',
  '94': 'breach of the peace',
  '296': 'robbery violence',
}

const haystack = (p: ProvisionStatus) =>
  `${p.provision.act_title} s.${p.provision.number} section ${p.provision.number} ${p.provision.heading} ${p.provision.text} ${ALIASES[p.provision.number] ?? ''}`.toLowerCase()

export function Lookup({ focus }: { focus?: string | null }) {
  const [q, setQ] = useState('')
  const [id, setId] = useState(PROVISIONS.find((p) => p.provision.number === '194')!.provision.provision_id)
  const [json, setJson] = useState(false)
  useEffect(() => {
    if (focus) setId(focus)
  }, [focus])

  const hits = useMemo(() => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean)
    return PROVISIONS.filter((p) => terms.every((t) => haystack(p).includes(t)))
  }, [q])
  const acts = [...new Set(hits.map((p) => p.provision.act_title))]
  const cur = PROVISIONS.find((p) => p.provision.provision_id === id)!
  const pick = (pid: string) => {
    setId(pid)
    setJson(false)
    play('stamp')
  }

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <div>
        <label className="relative block">
          <span className="sr-only">Search sections</span>
          <Search size={18} className="absolute top-1/2 left-3 -translate-y-1/2 text-ink-2" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Try defamation, 204, life sentence"
            className="w-full rounded-md border border-rule bg-[#fbfcf9] py-2.5 pr-3 pl-10 placeholder:text-ink-2/60 focus:border-ink focus:outline-none"
          />
        </label>
        <nav className="mt-4 max-h-[28rem] overflow-y-auto pr-1" aria-label="Sections">
          {acts.map((a) => (
            <div key={a} className="mb-4">
              <p className="text-sm text-ink-2">{a}</p>
              <ul className="mt-1">
                {hits
                  .filter((p) => p.provision.act_title === a)
                  .map((p) => (
                    <li key={p.provision.provision_id}>
                      <button
                        type="button"
                        onClick={() => pick(p.provision.provision_id)}
                        aria-current={p.provision.provision_id === id}
                        className="flex w-full gap-2 rounded-md px-2 py-1.5 text-left hover:bg-panel aria-[current=true]:bg-ink aria-[current=true]:text-paper"
                      >
                        <span className="w-12 shrink-0 font-medium">s.{p.provision.number}</span>
                        <span className="truncate">{p.provision.heading}</span>
                      </button>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
          {!hits.length && (
            <p className="text-ink-2">
              No section in the demo matches "{q}". The demo holds 13 sections; the real search covers all 1,862.
            </p>
          )}
        </nav>
      </div>

      <ProvisionCard p={cur} json={json} setJson={setJson} />
    </div>
  )
}

function ProvisionCard({ p, json, setJson }: { p: ProvisionStatus; json: boolean; setJson: (b: boolean) => void }) {
  const v = p.provision.versions
  return (
    <article className="min-w-0 rounded-md border border-rule bg-[#fbfcf9] p-6 sm:p-8" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-ink-2">{p.provision.act_title}</p>
          <h3 className="statute text-3xl">
            s.{p.provision.number} {p.provision.heading}
          </h3>
        </div>
        <StatusStamp status={p.status} />
      </div>

      <p className="statute mt-6 max-h-44 overflow-y-auto text-[1.12rem]">{p.provision.text}</p>
      <p className="mt-3 text-sm text-ink-2">
        {v.every((x) => x.same_text)
          ? `Same words in all ${v.length} version${v.length > 1 ? 's' : ''} we hold (${v.map((x) => year(x.date)).join(', ')}).`
          : `Words changed across the ${v.length} versions we hold.`}{' '}
        Kenya Law's notes on this section:{' '}
        {p.provision.remarks.length ? p.provision.remarks.join(' ') : 'none'}.
      </p>

      <div className="mt-8 border-t border-rule pt-6">
        {p.summary_events.length ? (
          <>
            <h4 className="font-semibold">What the courts said</h4>
            <ul className="mt-4 space-y-6">
              {p.summary_events.map((e) => (
                <li key={e.event_id}>
                  <p className="text-sm text-seal">
                    {EVENT_LABEL[e.event_type]}
                    {e.scope === 'partial' ? ' (in part)' : ''}. {e.court}, {fmtDate(e.effective_date)}
                  </p>
                  <CourtWords quote={e.operative_quote} mark={e.scope_text} className="mt-1.5 text-[1.05rem]" />
                  <p className="mt-1.5 text-sm text-ink-2">
                    {e.title}
                    {e.source_paragraph && `, para ${e.source_paragraph}`}.{' '}
                    <a className="link" href={e.source_url ?? '#'} target="_blank" rel="noreferrer">
                      Judgment on Kenya Law
                    </a>
                    {e.verified && ' Checked by a person.'}
                  </p>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-ink-2">
            No court has ruled on this section in the events we hold. That's the usual case: most sections are only ever
            applied, never challenged.
          </p>
        )}

        {p.history.length > p.summary_events.length && (
          <details className="mt-6">
            <summary className="cursor-pointer font-medium">Full history ({p.history.length} rulings)</summary>
            <ol className="mt-3 space-y-2 text-[0.95rem]">
              {p.history.map((e) => {
                const by = eventById(e.superseded_by)
                return (
                  <li key={e.event_id}>
                    <span className="font-medium">{year(e.effective_date)}</span> {shortCase(e)} ({e.court}):{' '}
                    {EVENT_LABEL[e.event_type].toLowerCase()}. <StateTag state={e.state} />
                    {by && <span className="text-ink-2"> by {shortCase(by)} ({year(by.effective_date)})</span>}
                  </li>
                )
              })}
            </ol>
          </details>
        )}
      </div>

      <div className="mt-8 border-t border-rule pt-4">
        <button type="button" onClick={() => (setJson(!json), play('tick'))} className="flex items-center gap-2 text-sm font-medium text-gazette" aria-expanded={json}>
          <Braces size={16} aria-hidden /> {json ? 'Hide' : 'Show'} what the API sends for this
        </button>
        {json && (
          <pre className="mt-3 max-h-96 overflow-auto rounded-md bg-ink p-4 font-mono text-[0.78rem] leading-relaxed text-paper">
            <span className="text-mark">GET /api/provisions/{p.provision.provision_id}</span>
            {'\n\n'}
            {JSON.stringify(p, (k, val) => (['versions', 'remarks', 'notes', 'event_key', 'affects_event_id'].includes(k) ? undefined : val), 2)}
          </pre>
        )}
        <p className="mt-3 text-sm text-ink-2">{p.disclaimer}</p>
      </div>
    </article>
  )
}
